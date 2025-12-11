
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

# Optionally hide all warnings (you can comment this out if you want some warnings)
warnings.filterwarnings("ignore")

# Silence pdfminer log spam (those "Cannot set gray non-stroke color..." messages)
logging.getLogger("pdfminer").setLevel(logging.ERROR)
logging.getLogger("pdfminer.pdfinterp").setLevel(logging.ERROR)

# -----------------------------
# MAIN LOOP
# -----------------------------
if __name__ == "__main__":
    projects = list_projects()

    for p in projects:
        print(f"\n======================")
        print(f"RUNNING PROJECT {p}")
        print(f"======================")

        run_pipeline(p)
