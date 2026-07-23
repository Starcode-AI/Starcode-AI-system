from datetime import UTC, datetime

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models import Role, User, UserSession
from .security import SESSION_COOKIE, require_csrf, token_hash, utc_aware


def get_session_and_user(request: Request, db: Session = Depends(get_db)) -> tuple[UserSession, User]:
    raw = request.cookies.get(SESSION_COOKIE)
    if not raw:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")
    session = db.scalar(select(UserSession).where(UserSession.token_hash == token_hash(raw)))
    if not session or utc_aware(session.expires_at) <= datetime.now(UTC):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")
    user = db.get(User, session.user_id)
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account is disabled")
    require_csrf(request, session)
    session.last_seen_at = datetime.now(UTC)
    db.commit()
    return session, user


def current_user(auth: tuple[UserSession, User] = Depends(get_session_and_user)) -> User:
    return auth[1]


def require_roles(*roles: Role):
    def dependency(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")
        return user

    return dependency


require_admin = require_roles(Role.administrator, Role.system_administrator)
require_moderator = require_roles(Role.moderator, Role.administrator, Role.system_administrator)
