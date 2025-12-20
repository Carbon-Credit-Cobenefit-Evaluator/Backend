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

# ============================================================
# App
# ============================================================

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


# ============================================================
# In-memory job store
# ============================================================

@dataclass
class JobState:
    job_id: str
    project_id: str

    status: str = "queued"
    mode_used: Optional[str] = None

    step: Optional[str] = None
    message: Optional[str] = None
    stats: Optional[Dict[str, Any]] = None

    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    error: Optional[str] = None

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
    pdf_dir = _project_root() / "data" / "pdfs" / project_folder
    return pdf_dir.exists() and any(pdf_dir.glob("*.pdf"))


def _refined_exists(project_folder: str) -> bool:
    return (
        _project_root()
        / "data"
        / "outputs"
        / project_folder
        / "refined_sentences.json"
    ).exists()


# ============================================================
# Background worker
# ============================================================

def _run_job(job_id: str, registry: Registry, raw_id: str):
    project_folder = _build_project_folder(registry, raw_id)

    def progress_cb(step: str, message: str, stats: Optional[Dict[str, Any]] = None):
        _job_update(job_id, step=step, message=message, stats=stats)

    try:
        _job_update(
            job_id,
            status="running",
            started_at=datetime.utcnow().isoformat() + "Z",
            step="decide_mode",
            message="Checking existing outputs and PDFs...",
        )

        if _refined_exists(project_folder):
            mode_used: PipelineMode = "inference_only"
            _job_update(
                job_id,
                mode_used=mode_used,
                message="Using existing refined evidence (inference_only).",
            )
            run_pipeline(project_folder, mode=mode_used, progress_cb=progress_cb)

        # elif _pdfs_exist(project_folder):
        #     mode_used = "full"
        #     _job_update(
        #         job_id,
        #         mode_used=mode_used,
        #         message="PDFs found → running full pipeline.",
        #     )
        #     run_pipeline(project_folder, mode=mode_used, progress_cb=progress_cb)

        else:
            mode_used = "full"
            url = _build_project_url(registry, raw_id)

            _job_update(
                job_id,
                mode_used=mode_used,
                step="ingest",
                message="Downloading PDFs from registry...",
                stats={"url": url},
            )

            run_project_from_url(
                project_url=url,
                mode=mode_used,
                progress_cb=progress_cb,
            )

        _job_update(
            job_id,
            status="completed",
            finished_at=datetime.utcnow().isoformat() + "Z",
            message="SDG scoring / assessment completed.",
        )

    except Exception as e:
        _job_update(
            job_id,
            status="failed",
            finished_at=datetime.utcnow().isoformat() + "Z",
            error=str(e),
            message="Pipeline failed.",
        )


# ============================================================
# Routes — Jobs
# ============================================================

@app.get("/health")
def health():
    return {"ok": True}


@app.post("/run", response_model=RunResponse)
def run(req: RunRequest):
    project_folder = _build_project_folder(req.registry, req.id)
    job_id = uuid4().hex

    with JOB_LOCK:
        JOB_STORE[job_id] = JobState(
            job_id=job_id,
            project_id=project_folder,
            status="queued",
            step="queued",
            message="Queued.",
        )

    threading.Thread(
        target=_run_job,
        args=(job_id, req.registry, req.id),
        daemon=True,
    ).start()

    return {"job_id": job_id, "project_id": project_folder}


@app.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str):
    with JOB_LOCK:
        job = JOB_STORE.get(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="job_id not found")

    return job.__dict__


@app.delete("/jobs/{job_id}")
def delete_job(job_id: str):
    with JOB_LOCK:
        existed = job_id in JOB_STORE
        if existed:
            del JOB_STORE[job_id]

    if not existed:
        raise HTTPException(status_code=404, detail="job_id not found")

    return {"deleted": True}


# ============================================================
# 🔥 NEW: Project data endpoints
# ============================================================

# ============================================================
# 🔥 Generic SDG assessment endpoint (ALL SDGs)
# ============================================================

@app.get("/projects/verra/{project_id}/sdg/{sdg_key}")
def get_verra_sdg(project_id: str, sdg_key: str):
    """
    Returns SDG assessment JSON for any SDG

    Example:
    GET /projects/verra/VCS_1566/sdg/SDG_1_No_Poverty
    -> data/outputs/VCS_1566/SDG_assessment/SDG_1_No_Poverty_score.json
    """

    # Safety: only allow expected naming pattern
    if not sdg_key.startswith("SDG_"):
        raise HTTPException(status_code=400, detail="Invalid SDG key")

    filename = f"{sdg_key}_score.json"

    path = (
        _project_root()
        / "data"
        / "outputs"
        / project_id
        / "SDG_assessment"
        / filename
    )

    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"{sdg_key} assessment not found"
        )

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to read SDG file: {str(e)}"
        )



@app.get("/projects/verra/{project_id}/metadata")
def get_verra_project_metadata(project_id: str):
    """
    Returns project metadata from data/verra/projects.json

    projects.json structure:
    {
      "projects": [
        {"VCS_1566": {...}},
        {"VCS_1567": {...}}
      ]
    }
    """
    projects_file = _project_root() / "data" / "verra" / "projects.json"

    if not projects_file.exists():
        raise HTTPException(status_code=404, detail="projects.json not found")

    data = json.loads(projects_file.read_text(encoding="utf-8"))

    projects_list = data.get("projects")
    if not isinstance(projects_list, list):
        raise HTTPException(status_code=500, detail="Invalid projects.json format: missing 'projects' list")

    # Find by key (VCS_1566)
    for item in projects_list:
        if isinstance(item, dict) and project_id in item:
            return item[project_id]

    raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")


    
