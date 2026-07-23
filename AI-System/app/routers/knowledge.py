from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..dependencies import current_user
from ..models import KnowledgeEntry, Role, User
from ..schemas import ApiMessage, KnowledgeCreate, KnowledgeOut
from ..security import audit


router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])
ADMIN_ROLES = {Role.administrator, Role.system_administrator}


@router.get("", response_model=list[KnowledgeOut])
def list_knowledge(
    q: str = Query(default="", max_length=200),
    category: str = Query(default="", max_length=60),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    statement = select(KnowledgeEntry).order_by(KnowledgeEntry.updated_at.desc()).limit(200)
    if q:
        statement = statement.where(or_(KnowledgeEntry.title.ilike(f"%{q}%"), KnowledgeEntry.content.ilike(f"%{q}%")))
    if category:
        statement = statement.where(KnowledgeEntry.category == category)
    return list(db.scalars(statement).all())


@router.post("", response_model=KnowledgeOut)
def create_knowledge(
    payload: KnowledgeCreate,
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    values = payload.model_dump()
    if values["category"] in {"confirmed", "internal"} and user.role not in ADMIN_ROLES:
        values["category"] = "unconfirmed"
        values["confidence"] = min(values["confidence"], 0.5)
    entry = KnowledgeEntry(created_by=user.id, **values)
    if values["category"] == "confirmed" and user.role in ADMIN_ROLES:
        entry.approved_by = user.id
    db.add(entry)
    db.commit()
    db.refresh(entry)
    audit(db, request, "knowledge_created", user.id, "knowledge", entry.id, {"category": entry.category})
    return entry


@router.patch("/{entry_id}/approve", response_model=KnowledgeOut)
def approve_knowledge(
    entry_id: str,
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    if user.role not in ADMIN_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administrator role required")
    entry = db.get(KnowledgeEntry, entry_id)
    if not entry:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Knowledge entry not found")
    entry.category = "confirmed"
    entry.approved_by = user.id
    entry.confidence = max(entry.confidence, 0.8)
    entry.version += 1
    entry.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(entry)
    audit(db, request, "knowledge_approved", user.id, "knowledge", entry.id)
    return entry


@router.delete("/{entry_id}", response_model=ApiMessage)
def delete_knowledge(
    entry_id: str,
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    entry = db.get(KnowledgeEntry, entry_id)
    if not entry:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Knowledge entry not found")
    if entry.created_by != user.id and user.role not in ADMIN_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")
    db.delete(entry)
    db.commit()
    audit(db, request, "knowledge_deleted", user.id, "knowledge", entry_id)
    return ApiMessage(message="Knowledge entry deleted")
