import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import SessionLocal, get_db
from ..dependencies import current_user
from ..models import Job, JobStatus, User
from ..schemas import ApiMessage, JobOut, ProjectGenerateIn
from ..security import audit, enforce_rate_limit, security_event
from ..services.projects import generate_project
from ..services.safety import BLOCK_MESSAGE, check_user_request


router = APIRouter(prefix="/api/projects", tags=["projects"])
settings = get_settings()
running_tasks: dict[str, asyncio.Task] = {}


async def generation_worker(job_id: str, payload: ProjectGenerateIn, user_id: str) -> None:
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if not job:
            return
        job.status = JobStatus.running
        job.progress = 10
        job.started_at = datetime.now(UTC)
        db.commit()
    try:
        result = await generate_project(
            settings.project_dir,
            user_id,
            payload.name,
            payload.description,
            payload.language,
        )
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if not job:
                return
            if job.cancel_requested:
                Path(result["archive"]).unlink(missing_ok=True)
                job.status = JobStatus.cancelled
                job.progress = 0
            else:
                job.status = JobStatus.reviewing
                job.progress = 90
                db.commit()
                job.status = JobStatus.completed
                job.progress = 100
                job.result_json = json.dumps(result, ensure_ascii=False)
            job.ended_at = datetime.now(UTC)
            db.commit()
    except asyncio.CancelledError:
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if job:
                job.status = JobStatus.cancelled
                job.ended_at = datetime.now(UTC)
                db.commit()
        raise
    except Exception as exc:
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if job:
                job.status = JobStatus.failed
                job.error_message = str(exc)[:1000]
                job.ended_at = datetime.now(UTC)
                db.commit()
    finally:
        running_tasks.pop(job_id, None)


@router.post("/generate", response_model=JobOut)
async def create_project_job(
    payload: ProjectGenerateIn,
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    enforce_rate_limit(request, "project", 5)
    decision = check_user_request(payload.description)
    if not decision.allowed:
        security_event(db, decision.category, decision.reason, user.id, decision.severity)
        raise HTTPException(status.HTTP_403_FORBIDDEN, BLOCK_MESSAGE)
    active = db.scalar(
        select(Job).where(
            Job.user_id == user.id,
            Job.kind == "project_generation",
            Job.status.in_([JobStatus.queued, JobStatus.running, JobStatus.reviewing]),
        )
    )
    if active:
        raise HTTPException(status.HTTP_409_CONFLICT, "A project generation is already running")
    job = Job(user_id=user.id, kind="project_generation")
    db.add(job)
    db.commit()
    db.refresh(job)
    task = asyncio.create_task(generation_worker(job.id, payload, user.id))
    running_tasks[job.id] = task
    audit(db, request, "project_generation_started", user.id, "job", job.id, {"name": payload.name})
    return job


@router.get("/jobs", response_model=list[JobOut])
def list_jobs(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return list(db.scalars(select(Job).where(Job.user_id == user.id).order_by(Job.created_at.desc()).limit(100)).all())


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job or job.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    return job


@router.post("/jobs/{job_id}/cancel", response_model=ApiMessage)
def cancel_job(job_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job or job.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    if job.status not in {JobStatus.queued, JobStatus.running, JobStatus.reviewing}:
        raise HTTPException(status.HTTP_409_CONFLICT, "Job is no longer running")
    job.cancel_requested = True
    db.commit()
    task = running_tasks.get(job.id)
    if task:
        task.cancel()
    return ApiMessage(message="Cancellation requested")


@router.get("/jobs/{job_id}/download")
def download_project(job_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job or job.user_id != user.id or job.status != JobStatus.completed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Completed project not found")
    data = json.loads(job.result_json)
    path = Path(data.get("archive", "")).resolve()
    user_dir = (settings.project_dir / user.id).resolve()
    if user_dir not in path.parents or not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project archive not found")
    return FileResponse(path, filename=path.name, media_type="application/zip")
