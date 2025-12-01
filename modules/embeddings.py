# modules/embeddings.py

from __future__ import annotations

import numpy as np
import torch
from typing import List, Sequence
from transformers import AutoModel
import unicodedata

from config.settings import JINA_MODEL_NAME, logger


# --------------------------------------
# DEVICE SELECTION (with logging)
# --------------------------------------
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
logger.info(f"[EMB] Using device: {device}")

# Optional improvement: FP16 on GPU
use_fp16 = torch.cuda.is_available()

# --------------------------------------
# LOAD MODEL
# --------------------------------------
logger.info(f"[EMB] Loading Jina model: {JINA_MODEL_NAME} ...")
model = AutoModel.from_pretrained(
    JINA_MODEL_NAME,
    trust_remote_code=True,
)
if use_fp16:
    model = model.half()

model = model.to(device)
model.eval()
logger.info("[EMB] Model loaded successfully.")


# --------------------------------------
# NORMALIZATION HELPERS
# --------------------------------------
def _normalize_text(text: str) -> str:
    """Normalize unicode, remove weird spaces, lowercase."""
    if not text:
        return ""

    # Unicode normalization
    text = unicodedata.normalize("NFKC", text)

    # Lowercase for embedding stability
    text = text.lower().strip()

    return text


# --------------------------------------
# EMBEDDING (with batching)
# --------------------------------------
def embed(
    texts: Sequence[str],
    batch_size: int = 64,
    normalize: bool = True,
    max_length: int = 500,
) -> np.ndarray:
    """
    Advanced embedding function.

    Args:
        texts: list of strings
        batch_size: batch size for memory control
        normalize: normalize text before embedding
        max_length: truncate extremely long sentences (words, not tokens)

    Returns:
        np.ndarray of shape (N, D)
    """

    if isinstance(texts, str):
        texts = [texts]

    texts = list(texts)
    if not texts:
        return np.zeros((0, 0), dtype=np.float32)

    # Normalize & truncate
    processed = []
    for t in texts:
        if not t or not t.strip():
            processed.append("")
            continue

        if normalize:
            t = _normalize_text(t)

        # Prevent extremely large input (pdfminer sometimes extracts entire paragraphs)
        words = t.split()
        if len(words) > max_length:
            t = " ".join(words[:max_length])

        processed.append(t)

    all_embs = []

    # Disable gradient computation
    with torch.no_grad():
        for start in range(0, len(processed), batch_size):
            batch = processed[start:start+batch_size]

            # Jina model supports model.encode(list_of_strings)
            batch_emb = model.encode(batch, show_progress_bar=False)

            # Convert to numpy
            batch_emb = np.asarray(batch_emb, dtype=np.float32)

            all_embs.append(batch_emb)

    if len(all_embs) == 1:
        return all_embs[0]

    return np.vstack(all_embs)
