import os
from pdfminer.high_level import extract_text
from config.settings import PROJECTS_ROOT

def list_projects():
    """Return a list of project folder names inside PROJECTS_ROOT."""
    return [
        d for d in os.listdir(PROJECTS_ROOT)
        if os.path.isdir(os.path.join(PROJECTS_ROOT, d))
    ]

def load_pdfs(project_name: str):
    """
    Load all PDFs for a single project.
    project_name: folder name inside PROJECTS_ROOT.
    Returns: list of { 'filename': str, 'text': str }
    """
    project_path = os.path.join(PROJECTS_ROOT, project_name)
    pdfs = []

    for f in os.listdir(project_path):
        if f.lower().endswith(".pdf"):
            path = os.path.join(project_path, f)
            try:
                text = extract_text(path)
                pdfs.append({"filename": f, "text": text})
            except Exception as e:
                print(f"[ERROR] Failed to read {path}: {e}")

    print(f"[INFO] Loaded {len(pdfs)} PDFs for project '{project_name}'.")
    return pdfs
