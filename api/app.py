# api/app.py
from __future__ import annotations

import warnings
from cryptography.utils import CryptographyDeprecationWarning

warnings.filterwarnings("ignore", category=CryptographyDeprecationWarning)
warnings.filterwarnings("ignore")

import json
from pathlib import Path
from typing import Any, Dict, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from pipeline.run_pipeline import run_pipeline
from pipeline.registry_ingestion import run_project_from_url

app = FastAPI(title="SDG Co-Benefit API", version="1.0")

Registry = Literal["verra", "gs"]


# ------------------------------------------------------------
# Request / Response models
# ------------------------------------------------------------

class RunRequest(BaseModel):
    registry: Registry
    id: str


class RunResponse(BaseModel):
    project_id: str
    mode_used: Literal["full", "inference_only"]
    assessments: Dict[str, Any]


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

def _project_root() -> Path:
    # project root = parent of /api
    return Path(__file__).resolve().parent.parent


def _build_project_folder(registry: Registry, project_id: str) -> str:
    # MUST match ingestion + pipeline naming
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
    """
    Checks if refined_sentences.json already exists:
      data/outputs/{project_folder}/refined_sentences.json
    If yes → we can safely run inference_only.
    """
    root = _project_root()
    refined_path = root / "data" / "outputs" / project_folder / "refined_sentences.json"
    return refined_path.exists()


def _read_assessments(project_folder: str) -> Dict[str, Any]:
    """
    Reads:
      data/outputs/{project_folder}/SDG_assessment/*_score.json
    Returns:
      { "<filename_stem>": <json>, ... }
    """
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


# ------------------------------------------------------------
# Routes
# ------------------------------------------------------------

@app.get("/health")
def health():
    return {"ok": True}


@app.post("/run", response_model=RunResponse)
def run(req: RunRequest):
    """
    POST body example:
    {
      "registry": "verra",
      "id": "1566"
    }

    Behavior (auto mode):
      1) If outputs/{project}/refined_sentences.json exists:
           → run_pipeline(project, mode="inference_only")
      2) Else if PDFs exist in data/pdfs/{project}/:
           → run_pipeline(project, mode="full")
      3) Else:
           → download PDFs from registry (run_project_from_url)
           → run full pipeline
      4) Return SDG assessments
    """
    project_folder = _build_project_folder(req.registry, req.id)

    # --------------------------------------------------------
    # Case 1: refined_sentences.json already exists → inference only
    # --------------------------------------------------------
    if _refined_exists(project_folder):
        try:
            run_pipeline(project_folder, mode="inference_only")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Inference-only pipeline failed: {e}")

        return {
            "project_id": project_folder,
            "mode_used": "inference_only",
            "assessments": _read_assessments(project_folder),
        }

    # --------------------------------------------------------
    # Case 2: PDFs exist → full pipeline
    # --------------------------------------------------------
    if _pdfs_exist(project_folder):
        try:
            run_pipeline(project_folder, mode="full")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Full pipeline failed: {e}")

        return {
            "project_id": project_folder,
            "mode_used": "full",
            "assessments": _read_assessments(project_folder),
        }

    # --------------------------------------------------------
    # Case 3: PDFs missing → ingest from registry → full pipeline
    # --------------------------------------------------------
    url = _build_project_url(req.registry, req.id)

    try:
        # Your helper already does: download PDFs -> run_pipeline(project, mode="full"/passed mode)
        # We force full here because refined doesn't exist and PDFs don't exist.
        run_project_from_url(project_url=url, mode="full")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {e}")

    return {
        "project_id": project_folder,
        "mode_used": "full",
        "assessments": _read_assessments(project_folder),
    }
