import warnings
import logging
from cryptography.utils import CryptographyDeprecationWarning

from modules.pdf_extraction import list_projects
from pipeline.run_pipeline import run_pipeline
from pipeline.registry_ingestion import run_project_from_url

warnings.filterwarnings("ignore", category=CryptographyDeprecationWarning)
warnings.filterwarnings("ignore")

logging.getLogger("pdfminer").setLevel(logging.ERROR)
logging.getLogger("pdfminer.pdfinterp").setLevel(logging.ERROR)

if __name__ == "__main__":

    # ============================================================
    # OPTION A — Run pipeline from an existing local project folder
    # ============================================================

    project_id = "VCS_1566"
    run_pipeline(project_id, mode="inference_only")
    

    # ============================================================
    # OPTION B — From Verra URL -> download PDFs -> pipeline full
    # ============================================================
    """
    url = "https://registry.verra.org/app/projectDetail/VCS/514"
    run_project_from_url(url, max_docs=10, mode="full")
    """

    # ============================================================
    # OPTION C — From GS URL -> download PDFs -> pipeline full
    # ============================================================
    """
    url = "https://registry.goldstandard.org/projects/details/2913"
    run_project_from_url(url, max_docs=10, mode="full")
    """

    # ============================================================
    # OPTION D — Batch run existing local folders (full)
    # ============================================================
    """
    for p in list_projects():
        run_pipeline(p, mode="full")
    """

    # ============================================================
    # OPTION E — Batch run existing local folders (inference only)
    # ============================================================
    """
    for p in list_projects():
        run_pipeline(p, mode="inference_only")
    """

    # Default (pick one)
    # url = "https://registry.verra.org/app/projectDetail/VCS/1566"
    # run_project_from_url(url, max_docs=10, mode="full")
