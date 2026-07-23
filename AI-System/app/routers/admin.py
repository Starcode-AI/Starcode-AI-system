import asyncio
import json
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..dependencies import require_admin
from ..models import AuditLog, Feedback, Job, ModelProfile, SecurityEvent, SystemSetting, User
from ..schemas import AdminUserUpdate, ApiMessage, ModelCreate, UserOut
from ..security import audit
from ..services.backups import create_backup, restore_backup
from ..services.ollama import ollama
from ..services.system import system_status


router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.post("/maintenance", response_model=ApiMessage)
def maintenance_mode(
    payload: dict,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    enabled = payload.get("enabled")
    if not isinstance(enabled, bool):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "enabled must be true or false")
    item = db.get(SystemSetting, "maintenance_mode") or SystemSetting(key="maintenance_mode")
    item.value_json = json.dumps(enabled)
    db.add(item)
    db.commit()
    audit(db, request, "maintenance_changed", admin.id, "system", "maintenance", {"enabled": enabled})
    return ApiMessage(message="Maintenance mode updated")


@router.get("/status")
async def status_page(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    state = system_status()
    state["model_service"] = await ollama.health()
    state["counts"] = {
        "users": db.scalar(select(func.count(User.id))) or 0,
        "jobs": db.scalar(select(func.count(Job.id))) or 0,
        "feedback": db.scalar(select(func.count(Feedback.id))) or 0,
        "security_events": db.scalar(select(func.count(SecurityEvent.id))) or 0,
    }
    return state


@router.get("/users", response_model=list[UserOut])
def users(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    return list(db.scalars(select(User).order_by(User.created_at.desc()).limit(500)).all())


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: str,
    payload: AdminUserUpdate,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if target.id == admin.id and payload.is_active is False:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot disable your current account")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(target, key, value)
    db.commit()
    db.refresh(target)
    audit(db, request, "user_updated", admin.id, "user", target.id, payload.model_dump(exclude_unset=True, mode="json"))
    return target


@router.get("/security-events")
def security_events(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.scalars(select(SecurityEvent).order_by(SecurityEvent.created_at.desc()).limit(500)).all()
    return [
        {"id": item.id, "type": item.event_type, "severity": item.severity, "summary": item.summary, "detail": json.loads(item.detail_json), "created_at": item.created_at}
        for item in rows
    ]


@router.get("/audit-logs")
def audit_logs(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(500)).all()
    return [
        {"id": item.id, "actor": item.actor_user_id, "action": item.action, "target_type": item.target_type, "target_id": item.target_id, "detail": json.loads(item.detail_json), "created_at": item.created_at}
        for item in rows
    ]


@router.get("/feedback")
def feedback(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.scalars(select(Feedback).order_by(Feedback.created_at.desc()).limit(500)).all()
    return [
        {"id": item.id, "user_id": item.user_id, "message_id": item.message_id, "rating": item.rating, "category": item.category, "comment": item.comment, "reviewed": item.reviewed, "created_at": item.created_at}
        for item in rows
    ]


@router.get("/models")
async def models(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    profiles = db.scalars(select(ModelProfile).order_by(ModelProfile.created_at)).all()
    installed = await ollama.list_models()
    return {
        "profiles": [
            {"id": item.id, "name": item.name, "model_name": item.model_name, "context_length": item.context_length, "temperature": item.temperature, "max_tokens": item.max_tokens, "is_active": item.is_active}
            for item in profiles
        ],
        "installed": installed,
    }


@router.post("/models", response_model=ApiMessage)
def add_model_profile(
    payload: ModelCreate,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if db.scalar(select(ModelProfile).where(ModelProfile.name == payload.name)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Profile name already exists")
    profile = ModelProfile(**payload.model_dump())
    db.add(profile)
    db.commit()
    audit(db, request, "model_profile_created", admin.id, "model_profile", profile.id)
    return ApiMessage(message="Model profile created")


@router.post("/models/{profile_id}/activate", response_model=ApiMessage)
def activate_model(
    profile_id: str,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    profile = db.get(ModelProfile, profile_id)
    if not profile:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Model profile not found")
    for item in db.scalars(select(ModelProfile)).all():
        item.is_active = item.id == profile.id
    db.commit()
    audit(db, request, "model_activated", admin.id, "model_profile", profile.id, {"model": profile.model_name})
    return ApiMessage(message="Model activated")


@router.post("/models/pull", response_model=ApiMessage)
async def pull_model(
    payload: dict,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    name = str(payload.get("name", "")).strip()
    if not name or len(name) > 160 or not all(c.isalnum() or c in "._:/-" for c in name):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid model name")
    async for _ in ollama.pull(name):
        await asyncio.sleep(0)
    audit(db, request, "model_pulled", admin.id, "model", name)
    return ApiMessage(message="Model installed")


@router.delete("/models/{name:path}", response_model=ApiMessage)
async def delete_model(
    name: str,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if db.scalar(select(ModelProfile).where(ModelProfile.model_name == name, ModelProfile.is_active.is_(True))):
        raise HTTPException(status.HTTP_409_CONFLICT, "Active model cannot be removed")
    await ollama.delete(name)
    audit(db, request, "model_deleted", admin.id, "model", name)
    return ApiMessage(message="Model removed")


@router.post("/backups")
def backup(request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    path = create_backup()
    audit(db, request, "backup_created", admin.id, "backup", path.name)
    return FileResponse(path, filename=path.name, media_type="application/octet-stream")


@router.post("/backups/restore", response_model=ApiMessage)
async def restore(
    request: Request,
    file: UploadFile = File(...),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if not (file.filename or "").endswith(".backup.enc"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Expected an encrypted .backup.enc file")
    data = await file.read(1024 * 1024 * 1024)
    await file.close()
    with tempfile.NamedTemporaryFile(delete=False, suffix=".backup.enc") as handle:
        handle.write(data)
        path = Path(handle.name)
    try:
        restore_backup(path)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    finally:
        path.unlink(missing_ok=True)
    return ApiMessage(message="Backup restored. Restart the application before continuing.")
