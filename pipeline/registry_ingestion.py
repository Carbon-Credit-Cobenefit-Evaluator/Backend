# pipeline/registry_ingestion.py

from __future__ import annotations

import asyncio
import re
import sys
import importlib.util
from pathlib import Path
from typing import Callable, Literal, Optional, Tuple

Registry = Literal["verra", "goldstandard"]

# progress callback signature: step, message, stats
ProgressCB = Callable[[str, str, dict], None]


def _emit(progress_cb: Optional[ProgressCB], step: str, message: str, stats: Optional[dict] = None) -> None:
    if progress_cb:
        progress_cb(step, message, stats or {})


def _detect_registry(project_url: str) -> Registry:
    u = project_url.lower()
    if "registry.verra.org" in u and "/vcs/" in u:
        return "verra"
    if "registry.goldstandard.org" in u and "/projects/details/" in u:
        return "goldstandard"
    raise ValueError(f"Unknown registry URL format: {project_url}")


def _extract_project_folder_name(project_url: str, registry: Registry) -> str:
    if registry == "verra":
        m = re.search(r"/vcs/(\d+)", project_url.lower())
        if not m:
            raise ValueError(f"Could not parse Verra project ID from URL: {project_url}")
        return f"VCS_{m.group(1)}"

    if registry == "goldstandard":
        m = re.search(r"/projects/details/(\d+)", project_url.lower())
        if not m:
            raise ValueError(f"Could not parse Gold Standard project ID from URL: {project_url}")
        return f"GS_{m.group(1)}"

    raise ValueError(f"Unsupported registry: {registry}")


def _import_module_from_file(module_name: str, file_path: Path):
    """
    Import a .py file as a module WITHOUT needing packages/__init__.py.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"Module file not found: {file_path}")

    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load spec for module '{module_name}' from {file_path}")

    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    return mod


def _run_runner_by_path(
    runner_file: Path,
    project_url: str,
    max_docs: int,
    progress_cb: Optional[ProgressCB] = None,
):
    """
    Runs runner.run_all(...) from a given runner.py path.
    Adds the runner folder to sys.path temporarily so imports like:
      from Scraping import ...
    work without __init__.py.
    """
    runner_dir = runner_file.parent.resolve()
    module_name = f"runner_{runner_dir.name.lower()}"  # unique-ish

    # Temporarily add runner_dir to sys.path so sibling imports work
    added = False
    if str(runner_dir) not in sys.path:
        sys.path.insert(0, str(runner_dir))
        added = True

    try:
        _emit(progress_cb, "ingest", "Loading registry runner module...", {"runner_file": str(runner_file)})

        runner_mod = _import_module_from_file(module_name, runner_file)
        if not hasattr(runner_mod, "run_all"):
            raise AttributeError(f"{runner_file} does not define async function run_all(...)")

        _emit(progress_cb, "ingest", "Running registry runner (downloading PDFs)...", {"max_docs": max_docs})

        # run_all is async in your runners
        asyncio.run(runner_mod.run_all(project_url, max_docs=max_docs))

        _emit(progress_cb, "ingest", "Runner finished downloading PDFs.", {})

    finally:
        # remove inserted path to avoid polluting global interpreter state
        if added and sys.path and sys.path[0] == str(runner_dir):
            sys.path.pop(0)


def ingest_project_pdfs_from_registry(
    project_url: str,
    max_docs: int = 10,
    progress_cb: Optional[ProgressCB] = None,
) -> Tuple[str, Registry]:
    """
    Runs the correct runner script (by file path) to:
      - fetch project JSON
      - filter/prioritize docs
      - download PDFs into: data/pdfs/{project_folder}/

    Returns:
      (project_folder_name, registry)
    """
    _emit(progress_cb, "ingest", "Detecting registry + extracting project folder...", {"url": project_url})

    registry = _detect_registry(project_url)
    project_folder = _extract_project_folder_name(project_url, registry)

    _emit(
        progress_cb,
        "ingest",
        f"Detected registry={registry}. Target folder={project_folder}.",
        {"registry": registry, "project_folder": project_folder},
    )

    # Project root = parent of /pipeline
    project_root = Path(__file__).resolve().parent.parent

    if registry == "verra":
        runner_file = project_root / "data" / "verra" / "runner.py"
        _run_runner_by_path(runner_file, project_url, max_docs, progress_cb=progress_cb)

    elif registry == "goldstandard":
        runner_file = project_root / "data" / "GS" / "runner.py"
        _run_runner_by_path(runner_file, project_url, max_docs, progress_cb=progress_cb)

    return project_folder, registry


def run_project_from_url(
    project_url: str,
    max_docs: int = 2,
    mode: str = "full",
    progress_cb: Optional[ProgressCB] = None,
) -> None:
    """
    One-call orchestration:
      URL -> download PDFs -> run pipeline
    """
    from pipeline.run_pipeline import run_pipeline

    _emit(progress_cb, "ingest", "Starting ingestion from registry URL...", {"url": project_url})

    project_id, registry = ingest_project_pdfs_from_registry(
        project_url,
        max_docs=max_docs,
        progress_cb=progress_cb,
    )

    print(f"[INGEST] {registry.upper()} -> PDFs downloaded to data/pdfs/{project_id}/")
    _emit(progress_cb, "ingest", "PDF download completed.", {"project_id": project_id, "registry": registry})

    _emit(progress_cb, "pipeline", f"Starting pipeline mode={mode}...", {"project_id": project_id})
    run_pipeline(project_id, mode=mode, progress_cb=progress_cb)
