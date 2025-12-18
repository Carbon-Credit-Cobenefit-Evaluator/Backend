import warnings
import logging

from cryptography.utils import CryptographyDeprecationWarning

from modules.pdf_extraction import list_projects
from pipeline.run_pipeline import run_pipeline

# -----------------------------
# WARNING & LOGGING SETTINGS
# -----------------------------

# Hide Cryptography deprecation warning (ARC4 etc.)
warnings.filterwarnings("ignore", category=CryptographyDeprecationWarning)

# Optional: hide all warnings
warnings.filterwarnings("ignore")

# Silence pdfminer log spam
logging.getLogger("pdfminer").setLevel(logging.ERROR)
logging.getLogger("pdfminer.pdfinterp").setLevel(logging.ERROR)

# -----------------------------
# MAIN
# -----------------------------
if __name__ == "__main__":

    # ============================================================
    # OPTION 1 — FULL PIPELINE for ALL PROJECTS (default batch run)
    # Steps 1..9 for every project
    # ============================================================
    """
    projects = list_projects()

    for p in projects:
        print(f"\n======================")
        print(f"RUNNING PROJECT {p} (FULL)")
        print(f"======================")
        run_pipeline(p, mode="full")
    """

    # ============================================================
    # OPTION 2 — INFERENCE + ASSESSMENT ONLY for ALL PROJECTS
    # Steps 8..9 only (fast, deterministic)
    # ============================================================
    """
    projects = list_projects()

    for p in projects:
        print(f"\n======================")
        print(f"RUNNING PROJECT {p} (INFERENCE ONLY)")
        print(f"======================")
        run_pipeline(p, mode="inference_only")
    """

    # ============================================================
    # OPTION 3 — FULL PIPELINE for ONE PROJECT
    # ============================================================
    """
    project_id = "605"
    print(f"\n======================")
    print(f"RUNNING PROJECT {project_id} (FULL)")
    print(f"======================")
    run_pipeline(project_id, mode="full")
    """

    # ============================================================
    # OPTION 4 — INFERENCE + ASSESSMENT ONLY for ONE PROJECT
    # ============================================================
    project_id = "605"
    print(f"\n======================")
    print(f"RUNNING PROJECT {project_id} (INFERENCE ONLY)")
    print(f"======================")
    run_pipeline(project_id, mode="inference_only")
