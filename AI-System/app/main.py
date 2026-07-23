import json
import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import __version__
from .config import get_settings
from .db import SessionLocal, init_db
from .models import Job, JobStatus, ModelProfile, Role, SystemSetting, User, UserSession
from .routers import admin, auth, chat, feedback, files, knowledge, projects, research
from .security import hash_password, utc_aware


settings = get_settings()
logger = logging.getLogger("localai")
STATIC_DIR = Path(__file__).resolve().parent / "static"


def initialize_records() -> None:
    with SessionLocal() as db:
        if not db.scalar(select(ModelProfile).limit(1)):
            db.add(
                ModelProfile(
                    name="Standard",
                    model_name=settings.ollama_model,
                    context_length=settings.model_context_length,
                    temperature=settings.model_temperature,
                    max_tokens=settings.model_max_tokens,
                    is_active=True,
                )
            )
        if not db.get(SystemSetting, "maintenance_mode"):
            db.add(SystemSetting(key="maintenance_mode", value_json="false"))
        if settings.bootstrap_admin_email and settings.bootstrap_admin_password:
            email = settings.bootstrap_admin_email.lower()
            if not db.scalar(select(User).where(User.email == email)):
                if len(settings.bootstrap_admin_password) < 12:
                    raise RuntimeError("BOOTSTRAP_ADMIN_PASSWORD must contain at least 12 characters")
                db.add(
                    User(
                        email=email,
                        display_name="Administrator",
                        password_hash=hash_password(settings.bootstrap_admin_password),
                        role=Role.system_administrator,
                    )
                )
        now = datetime.now(UTC)
        for session in db.scalars(select(UserSession)).all():
            if utc_aware(session.expires_at) <= now:
                db.delete(session)
        for job in db.scalars(
            select(Job).where(Job.status.in_([JobStatus.running, JobStatus.reviewing]))
        ).all():
            job.status = JobStatus.failed
            job.error_message = "Task was interrupted by an application restart"
            job.ended_at = now
        db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    initialize_records()
    yield


app = FastAPI(
    title=settings.app_name,
    version=__version__,
    docs_url="/api/docs" if settings.app_env == "development" else None,
    redoc_url=None,
    lifespan=lifespan,
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.hosts)


@app.middleware("http")
async def secure_headers(request: Request, call_next):
    if settings.force_https and request.url.scheme != "https":
        forwarded = request.headers.get("x-forwarded-proto", "")
        if forwarded != "https" and request.url.path != "/api/health":
            return JSONResponse({"detail": "HTTPS is required"}, status_code=400)
    if request.url.path.startswith("/api/") and request.url.path not in {
        "/api/health",
        "/api/setup/status",
        "/api/auth/login",
    }:
        with SessionLocal() as db:
            value = db.get(SystemSetting, "maintenance_mode")
            maintenance = bool(value and json.loads(value.value_json))
        if maintenance and not request.url.path.startswith("/api/admin/"):
            return JSONResponse({"detail": "System is currently in maintenance mode"}, status_code=503)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; "
        "frame-ancestors 'none'; form-action 'self'"
    )
    response.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/api/") else "no-cache"
    if settings.force_https:
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return response


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    return JSONResponse(
        {"detail": "The submitted data is invalid", "errors": exc.errors()},
        status_code=422,
    )


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers)
    logger.exception("Unhandled request error", exc_info=exc)
    return JSONResponse(
        {"detail": "The request could not be completed. Technical details were recorded."},
        status_code=500,
    )


@app.get("/api/health")
def health():
    return {"status": "ok", "version": __version__, "mode": "local"}


@app.get("/api/setup/status")
def setup_status():
    with SessionLocal() as db:
        has_users = db.scalar(select(User.id).limit(1)) is not None
    return {"configured": has_users, "model": settings.ollama_model}


for router in (auth.router, chat.router, research.router, files.router, knowledge.router, feedback.router, projects.router, admin.router):
    app.include_router(router)


app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")


@app.get("/{path:path}", include_in_schema=False)
def frontend(path: str):
    if path.startswith("api/"):
        raise HTTPException(404, "API endpoint not found")
    return FileResponse(STATIC_DIR / "index.html")
