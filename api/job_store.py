# api/job_store.py
from __future__ import annotations

import uuid
import time
from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional


@dataclass
class JobState:
    job_id: str
    project_id: str

    # lifecycle
    state: str = "queued"  # queued | running | done | failed
    created_at: float = 0.0
    updated_at: float = 0.0

    # progress info (phase 1: basic; we'll enrich later)
    step: int = 0
    step_name: str = "Queued"
    progress: float = 0.0
    message: str = ""

    # outputs
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


# Simple in-memory store (good for dev; later swap to Redis/DB)
_JOBS: Dict[str, JobState] = {}


def create_job(project_id: str) -> JobState:
    job_id = uuid.uuid4().hex
    now = time.time()
    job = JobState(
        job_id=job_id,
        project_id=project_id,
        created_at=now,
        updated_at=now,
    )
    _JOBS[job_id] = job
    return job


def get_job(job_id: str) -> Optional[JobState]:
    return _JOBS.get(job_id)


def update_job(
    job_id: str,
    *,
    state: Optional[str] = None,
    step: Optional[int] = None,
    step_name: Optional[str] = None,
    progress: Optional[float] = None,
    message: Optional[str] = None,
    result: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
) -> None:
    job = _JOBS.get(job_id)
    if not job:
        return

    if state is not None:
        job.state = state
    if step is not None:
        job.step = step
    if step_name is not None:
        job.step_name = step_name
    if progress is not None:
        job.progress = float(progress)
    if message is not None:
        job.message = message
    if result is not None:
        job.result = result
    if error is not None:
        job.error = error

    job.updated_at = time.time()


def job_to_dict(job: JobState) -> Dict[str, Any]:
    return asdict(job)
