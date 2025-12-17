# config/settings.py

from __future__ import annotations
import os
from pathlib import Path
import logging

# ----------------------------
# API KEYS (no .env required)
# ----------------------------
# NOTE: It's okay for development, but do NOT commit your key to GitHub.
GROQ_API_KEY = "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"
os.environ["GROQ_API_KEY"] = GROQ_API_KEY


# ----------------------------
# ----------------------------
# PATHS (relative to project folder)
# ----------------------------
BASE_DIR = Path(__file__).resolve().parent.parent

# Folder where PDFs will be downloaded
PROJECTS_ROOT = BASE_DIR / "data" / "pdfs"
PROJECTS_ROOT.mkdir(parents=True, exist_ok=True)

# Folder where extracted outputs, logs, etc. are stored
BASE_OUTPUT_DIR = BASE_DIR / "data" / "outputs"
BASE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)



# ----------------------------
# MODEL CONFIGURATION
# ----------------------------
SIMILARITY_THRESHOLD = 0.5

# Embeddings (good stable version for Windows)
EMBEDDING_MODEL_NAME = "sentence-transformers/all-distilroberta-v1"


# Groq LLM (OSS-20B is correct for Groq)
GROQ_MODEL_NAME = "openai/gpt-oss-20b"

# spaCy model
SPACY_MODEL = "en_core_web_sm"


# ----------------------------
# LOGGING (recommended)
# ----------------------------
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(name)s - %(message)s",
)

logger = logging.getLogger("fyp_sdg")
