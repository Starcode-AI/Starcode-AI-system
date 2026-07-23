import hashlib
import hmac
import json
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from .config import get_settings
from .models import AuditLog, SecurityEvent, User, UserSession


settings = get_settings()
password_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
SESSION_COOKIE = "localai_session"
CSRF_COOKIE = "localai_csrf"


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    try:
        return password_hasher.verify(encoded, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def password_needs_rehash(encoded: str) -> bool:
    try:
        return password_hasher.check_needs_rehash(encoded)
    except InvalidHashError:
        return True


def token_hash(token: str) -> str:
    return hmac.new(settings.secret_key.encode(), token.encode(), hashlib.sha256).hexdigest()


def create_session(db: Session, user: User, request: Request) -> tuple[UserSession, str]:
    raw_token = secrets.token_urlsafe(48)
    session = UserSession(
        user_id=user.id,
        token_hash=token_hash(raw_token),
        csrf_token=secrets.token_urlsafe(32),
        user_agent=request.headers.get("user-agent", "")[:512],
        ip_address=client_ip(request),
        expires_at=datetime.now(UTC) + timedelta(hours=settings.session_hours),
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session, raw_token


def set_session_cookies(response: Response, session: UserSession, raw_token: str) -> None:
    max_age = settings.session_hours * 3600
    response.set_cookie(
        SESSION_COOKIE,
        raw_token,
        max_age=max_age,
        httponly=True,
        secure=settings.force_https,
        samesite="strict",
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        session.csrf_token,
        max_age=max_age,
        httponly=False,
        secure=settings.force_https,
        samesite="strict",
        path="/",
    )


def clear_session_cookies(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


def client_ip(request: Request) -> str:
    return request.client.host[:64] if request.client else ""


def utc_aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def audit(
    db: Session,
    request: Request | None,
    action: str,
    actor_user_id: str | None = None,
    target_type: str = "",
    target_id: str = "",
    detail: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditLog(
            actor_user_id=actor_user_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            detail_json=json.dumps(detail or {}, ensure_ascii=False),
            ip_address=client_ip(request) if request else "",
        )
    )
    db.commit()


def security_event(
    db: Session,
    event_type: str,
    summary: str,
    user_id: str | None = None,
    severity: str = "medium",
    detail: dict[str, Any] | None = None,
) -> None:
    db.add(
        SecurityEvent(
            user_id=user_id,
            event_type=event_type,
            severity=severity,
            summary=summary[:500],
            detail_json=json.dumps(detail or {}, ensure_ascii=False),
        )
    )
    db.commit()


def require_csrf(request: Request, session: UserSession) -> None:
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    header = request.headers.get("x-csrf-token", "")
    cookie = request.cookies.get(CSRF_COOKIE, "")
    if not header or not cookie or not secrets.compare_digest(header, cookie):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "CSRF validation failed")
    if not secrets.compare_digest(header, session.csrf_token):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "CSRF validation failed")


class RateLimiter:
    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, window_seconds: int = 60) -> tuple[bool, int]:
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            bucket = self._events[key]
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                retry = max(1, int(window_seconds - (now - bucket[0])))
                return False, retry
            bucket.append(now)
            return True, 0


rate_limiter = RateLimiter()


def enforce_rate_limit(request: Request, bucket: str = "global", limit: int | None = None) -> None:
    allowed, retry = rate_limiter.check(
        f"{bucket}:{client_ip(request)}", limit or settings.request_rate_per_minute
    )
    if not allowed:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many requests",
            headers={"Retry-After": str(retry)},
        )
