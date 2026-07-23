import json
import os
import uuid
import asyncio
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..dependencies import current_user
from ..models import User
from ..schemas import ApiMessage
from ..security import audit, enforce_rate_limit, security_event
from ..services.files import DANGEROUS_EXTENSIONS, analyze_file, sanitize_filename, scan_with_clamav


router = APIRouter(prefix="/api/files", tags=["files"])
settings = get_settings()


def user_root(user_id: str) -> Path:
    root = (settings.upload_dir / user_id).resolve()
    if settings.upload_dir.resolve() not in root.parents:
        raise RuntimeError("Invalid upload directory")
    root.mkdir(parents=True, exist_ok=True)
    return root


@router.post("/analyze")
async def upload_and_analyze(
    request: Request,
    file: UploadFile = File(...),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    enforce_rate_limit(request, "upload", 20)
    original_name = sanitize_filename(file.filename or "upload.bin")
    item_id = str(uuid.uuid4())
    root = user_root(user.id)
    suffix = Path(original_name).suffix.lower()
    stored_suffix = ".quarantine" if suffix in DANGEROUS_EXTENSIONS else suffix[:12]
    path = root / f"{item_id}{stored_suffix}"
    size = 0
    try:
        with path.open("xb") as handle:
            os.chmod(path, 0o600)
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > settings.max_upload_bytes:
                    raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File exceeds the configured limit")
                handle.write(chunk)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    finally:
        await file.close()
    result = await asyncio.to_thread(
        analyze_file,
        path,
        original_name,
        settings.archive_max_files,
        settings.archive_max_expanded_bytes,
    )
    result["malware_scan"] = await asyncio.to_thread(
        scan_with_clamav, path, settings.clamav_host, settings.clamav_port
    )
    result["id"] = item_id
    result["uploaded_at"] = __import__("datetime").datetime.now(__import__("datetime").UTC).isoformat()
    metadata_path = root / f"{item_id}.json"
    metadata_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if result.get("executable"):
        security_event(db, "executable_upload", f"Executable quarantined: {original_name}", user.id, "medium", {"sha256": result["sha256"]})
    if result["malware_scan"].get("status") == "infected":
        security_event(db, "malware_detected", f"Malware scanner flagged {original_name}", user.id, "critical", {"sha256": result["sha256"]})
    analysis = result.get("analysis", {})
    if analysis.get("prompt_injection_detected"):
        security_event(db, "document_prompt_injection", f"Potential injection removed from {original_name}", user.id, "high")
    audit(db, request, "file_uploaded", user.id, "file", item_id, {"name": original_name, "size": size})
    return result


@router.get("")
def list_files(user: User = Depends(current_user)):
    root = user_root(user.id)
    results = []
    for path in sorted(root.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)[:200]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            results.append({key: data.get(key) for key in ("id", "filename", "size", "sha256", "mime", "uploaded_at", "executable")})
        except (OSError, json.JSONDecodeError):
            continue
    return results


@router.get("/{item_id}")
def get_file_analysis(item_id: str, user: User = Depends(current_user)):
    try:
        uuid.UUID(item_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found") from exc
    metadata = user_root(user.id) / f"{item_id}.json"
    if not metadata.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")
    return json.loads(metadata.read_text(encoding="utf-8"))


@router.delete("/{item_id}", response_model=ApiMessage)
def delete_file(
    item_id: str,
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    try:
        uuid.UUID(item_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found") from exc
    root = user_root(user.id)
    metadata = root / f"{item_id}.json"
    if not metadata.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")
    for path in root.glob(f"{item_id}.*"):
        path.unlink(missing_ok=True)
    audit(db, request, "file_deleted", user.id, "file", item_id)
    return ApiMessage(message="File and analysis deleted")
