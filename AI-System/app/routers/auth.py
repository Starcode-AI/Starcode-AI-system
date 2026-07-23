from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..dependencies import current_user, get_session_and_user
from ..models import User, UserSession
from ..schemas import ApiMessage, LoginIn, PasswordChangeIn, UserOut
from ..security import (
    audit,
    clear_session_cookies,
    create_session,
    enforce_rate_limit,
    hash_password,
    password_needs_rehash,
    security_event,
    set_session_cookies,
    utc_aware,
    verify_password,
)


router = APIRouter(prefix="/api/auth", tags=["auth"])
settings = get_settings()


@router.post("/login", response_model=UserOut)
def login(payload: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    enforce_rate_limit(request, "login", 12)
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if not user:
        security_event(db, "login_failed", "Unknown email", severity="medium")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    if user.locked_until and utc_aware(user.locked_until) > datetime.now(UTC):
        raise HTTPException(status.HTTP_423_LOCKED, "Account is temporarily locked")
    if not verify_password(payload.password, user.password_hash):
        user.failed_logins += 1
        if user.failed_logins >= settings.max_login_attempts:
            user.locked_until = datetime.now(UTC) + timedelta(minutes=settings.login_lock_minutes)
            user.failed_logins = 0
        db.commit()
        security_event(db, "login_failed", "Incorrect password", user.id, "medium")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account is disabled")
    user.failed_logins = 0
    user.locked_until = None
    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(payload.password)
    db.commit()
    session, raw = create_session(db, user, request)
    set_session_cookies(response, session, raw)
    audit(db, request, "login", user.id)
    return user


@router.post("/logout", response_model=ApiMessage)
def logout(
    request: Request,
    response: Response,
    auth: tuple[UserSession, User] = Depends(get_session_and_user),
    db: Session = Depends(get_db),
):
    session, user = auth
    db.delete(session)
    db.commit()
    clear_session_cookies(response)
    audit(db, request, "logout", user.id)
    return ApiMessage(message="Signed out")


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user


@router.post("/password", response_model=ApiMessage)
def change_password(
    payload: PasswordChangeIn,
    request: Request,
    auth: tuple[UserSession, User] = Depends(get_session_and_user),
    db: Session = Depends(get_db),
):
    current_session, user = auth
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    user.password_hash = hash_password(payload.new_password)
    db.execute(
        UserSession.__table__.delete().where(
            UserSession.user_id == user.id, UserSession.id != current_session.id
        )
    )
    db.commit()
    audit(db, request, "password_changed", user.id)
    return ApiMessage(message="Password changed; other sessions were ended")


@router.get("/sessions")
def sessions(
    auth: tuple[UserSession, User] = Depends(get_session_and_user),
    db: Session = Depends(get_db),
):
    current, user = auth
    rows = db.scalars(select(UserSession).where(UserSession.user_id == user.id)).all()
    return [
        {
            "id": item.id,
            "user_agent": item.user_agent,
            "ip_address": item.ip_address,
            "created_at": item.created_at,
            "last_seen_at": item.last_seen_at,
            "expires_at": item.expires_at,
            "current": item.id == current.id,
        }
        for item in rows
    ]


@router.delete("/sessions/{session_id}", response_model=ApiMessage)
def end_session(
    session_id: str,
    request: Request,
    auth: tuple[UserSession, User] = Depends(get_session_and_user),
    db: Session = Depends(get_db),
):
    current, user = auth
    item = db.get(UserSession, session_id)
    if not item or item.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    if item.id == current.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Use sign out to end the current session")
    db.delete(item)
    db.commit()
    audit(db, request, "session_ended", user.id, "session", session_id)
    return ApiMessage(message="Session ended")


@router.get("/export")
def export_data(user: User = Depends(current_user), db: Session = Depends(get_db)):
    from ..models import Conversation, Feedback, KnowledgeEntry, Message

    conversations = db.scalars(select(Conversation).where(Conversation.user_id == user.id)).all()
    messages = []
    for conversation in conversations:
        messages.extend(db.scalars(select(Message).where(Message.conversation_id == conversation.id)).all())
    feedback = db.scalars(select(Feedback).where(Feedback.user_id == user.id)).all()
    notes = db.scalars(select(KnowledgeEntry).where(KnowledgeEntry.created_by == user.id)).all()
    return {
        "exported_at": datetime.now(UTC).isoformat(),
        "user": UserOut.model_validate(user).model_dump(mode="json"),
        "conversations": [
            {"id": item.id, "title": item.title, "archived": item.archived, "created_at": item.created_at}
            for item in conversations
        ],
        "messages": [
            {"id": item.id, "conversation_id": item.conversation_id, "role": item.role, "content": item.content, "created_at": item.created_at}
            for item in messages
        ],
        "feedback": [{"message_id": item.message_id, "rating": item.rating, "category": item.category, "comment": item.comment} for item in feedback],
        "knowledge": [{"title": item.title, "content": item.content, "category": item.category, "source": item.source} for item in notes],
    }


@router.delete("/account", response_model=ApiMessage)
def delete_account(
    payload: LoginIn,
    request: Request,
    response: Response,
    auth: tuple[UserSession, User] = Depends(get_session_and_user),
    db: Session = Depends(get_db),
):
    _, user = auth
    if payload.email.lower() != user.email or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Account confirmation failed")
    from ..models import KnowledgeEntry

    user_id = user.id
    db.execute(KnowledgeEntry.__table__.delete().where(KnowledgeEntry.created_by == user.id))
    db.delete(user)
    db.commit()
    clear_session_cookies(response)
    audit(db, request, "account_deleted", None, "user", user_id)
    return ApiMessage(message="Account and associated data deleted")
