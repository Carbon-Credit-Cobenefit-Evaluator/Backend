# api/app.py
from __future__ import annotations

import warnings
from cryptography.utils import CryptographyDeprecationWarning

warnings.filterwarnings("ignore", category=CryptographyDeprecationWarning)
warnings.filterwarnings("ignore")

import json
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Literal, Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from pipeline.run_pipeline import run_pipeline
from pipeline.registry_ingestion import run_project_from_url

app = FastAPI(title="SDG Co-Benefit API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Registry = Literal["verra", "gs"]
PipelineMode = Literal["full", "inference_only"]


# ============================================================
# Request / Response models
# ============================================================

class RunRequest(BaseModel):
    registry: Registry
    id: str


class RunResponse(BaseModel):
    job_id: str
    project_id: str


class JobResponse(BaseModel):
    job_id: str
    project_id: str
    status: Literal["queued", "running", "completed", "failed"]
    mode_used: Optional[PipelineMode] = None

    step: Optional[str] = None
    message: Optional[str] = None
    stats: Optional[Dict[str, Any]] = None

    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    error: Optional[str] = None

    # Only present when completed
    assessments: Optional[Dict[str, Any]] = None


# ============================================================
# In-memory job store (Phase 1)
# ============================================================

@dataclass
class JobState:
    job_id: str
    project_id: str
    status: str = "queued"  # queued|running|completed|failed
    mode_used: Optional[str] = None

    step: Optional[str] = None
    message: Optional[str] = None
    stats: Optional[Dict[str, Any]] = None

    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    error: Optional[str] = None
    assessments: Optional[Dict[str, Any]] = None

    updated_at: float = field(default_factory=lambda: time.time())


JOB_STORE: Dict[str, JobState] = {}
JOB_LOCK = threading.Lock()


def _job_update(job_id: str, **kwargs):
    with JOB_LOCK:
        job = JOB_STORE.get(job_id)
        if not job:
            return
        for k, v in kwargs.items():
            setattr(job, k, v)
        job.updated_at = time.time()


# ============================================================
# Helpers
# ============================================================

def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _build_project_folder(registry: Registry, project_id: str) -> str:
    return f"VCS_{project_id}" if registry == "verra" else f"GS_{project_id}"


def _build_project_url(registry: Registry, project_id: str) -> str:
    if registry == "verra":
        return f"https://registry.verra.org/app/projectDetail/VCS/{project_id}"
    if registry == "gs":
        return f"https://registry.goldstandard.org/projects/details/{project_id}"
    raise ValueError(f"Unsupported registry: {registry}")


def _pdfs_exist(project_folder: str) -> bool:
    root = _project_root()
    pdf_dir = root / "data" / "pdfs" / project_folder
    return pdf_dir.exists() and any(pdf_dir.glob("*.pdf"))


def _refined_exists(project_folder: str) -> bool:
    root = _project_root()
    refined_path = root / "data" / "outputs" / project_folder / "refined_sentences.json"
    return refined_path.exists()


def _read_assessments(project_folder: str) -> Dict[str, Any]:
    root = _project_root()
    assess_dir = root / "data" / "outputs" / project_folder / "SDG_assessment"
    if not assess_dir.exists():
        return {}

    out: Dict[str, Any] = {}
    for fp in assess_dir.glob("*_score.json"):
        try:
            out[fp.stem] = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
    return out


# ============================================================
# Background worker
# ============================================================

def _run_job(job_id: str, registry: Registry, raw_id: str):
    project_folder = _build_project_folder(registry, raw_id)

    def progress_cb(step: str, message: str, stats: Optional[Dict[str, Any]] = None) -> None:
        # this callback is called from pipeline.run_pipeline at each step
        _job_update(job_id, step=step, message=message, stats=stats)

    try:
        _job_update(
            job_id,
            status="running",
            started_at=datetime.utcnow().isoformat() + "Z",
            step="decide_mode",
            message="Checking existing outputs and PDFs...",
            stats=None,
        )

        # 1) If refined exists -> inference_only
        if _refined_exists(project_folder):
            mode_used: PipelineMode = "inference_only"
            _job_update(
                job_id,
                mode_used=mode_used,
                step="decide_mode",
                message="refined_sentences.json found → running inference_only (steps 8–9).",
                stats=None,
            )
            run_pipeline(project_folder, mode=mode_used, progress_cb=progress_cb)

        # 2) Else if PDFs exist -> full
        elif _pdfs_exist(project_folder):
            mode_used = "full"
            _job_update(
                job_id,
                mode_used=mode_used,
                step="decide_mode",
                message="PDFs found → running full pipeline (steps 1–9).",
                stats=None,
            )
            run_pipeline(project_folder, mode=mode_used, progress_cb=progress_cb)

        # 3) Else download -> full
        else:
            mode_used = "full"
            url = _build_project_url(registry, raw_id)

            _job_update(
                job_id,
                mode_used=mode_used,
                step="ingest",
                message="PDFs missing → downloading from registry...",
                stats={"url": url},
            )

            # ✅ best: run_project_from_url forwards progress_cb into run_pipeline
            # (requires the small registry_ingestion.py update shown below)
            run_project_from_url(project_url=url, mode=mode_used, progress_cb=progress_cb)

        # After pipeline completes:
        _job_update(job_id, step="read_results", message="Reading assessment outputs...", stats=None)
        assessments = _read_assessments(project_folder)

        _job_update(
            job_id,
            status="completed",
            finished_at=datetime.utcnow().isoformat() + "Z",
            step="done",
            message="Completed.",
            stats=None,
            assessments=assessments,
        )

    except Exception as e:
        _job_update(
            job_id,
            status="failed",
            finished_at=datetime.utcnow().isoformat() + "Z",
            step="error",
            message="Failed.",
            error=str(e),
        )


# ============================================================
# Routes
# ============================================================

@app.get("/health")
def health():
    return {"ok": True}


@app.post("/run", response_model=RunResponse)
def run(req: RunRequest):
    """
    Starts an async job and returns job_id immediately.

    Body:
    {
      "registry": "verra",
      "id": "1566"
    }
    """
    project_folder = _build_project_folder(req.registry, req.id)
    job_id = uuid4().hex

    with JOB_LOCK:
        JOB_STORE[job_id] = JobState(
            job_id=job_id,
            project_id=project_folder,
            status="queued",
            step="queued",
            message="Queued.",
            stats=None,
        )

    t = threading.Thread(target=_run_job, args=(job_id, req.registry, req.id), daemon=True)
    t.start()

    return {"job_id": job_id, "project_id": project_folder}


@app.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str):
    """
    Poll this from frontend to get progress + results.
    """
    with JOB_LOCK:
        job = JOB_STORE.get(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="job_id not found")

    resp: Dict[str, Any] = {
        "job_id": job.job_id,
        "project_id": job.project_id,
        "status": job.status,
        "mode_used": job.mode_used,
        "step": job.step,
        "message": job.message,
        "stats": job.stats,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "error": job.error,
    }

    if job.status == "completed":
        resp["assessments"] = job.assessments or {}

    return resp


@app.delete("/jobs/{job_id}")
def delete_job(job_id: str):
    """
    Optional utility: remove a job from memory.
    (Does NOT cancel a running thread.)
    """
    with JOB_LOCK:
        existed = job_id in JOB_STORE
        if existed:
            del JOB_STORE[job_id]
    if not existed:
        raise HTTPException(status_code=404, detail="job_id not found")
    return {"deleted": True}
