# modules/embeddings.py

from __future__ import annotations

import numpy as np
import torch
from typing import List, Sequence
from transformers import AutoModel
import unicodedata
from tqdm import tqdm   # <-- added

from config.settings import JINA_MODEL_NAME, logger


# --------------------------------------
# DEVICE SELECTION (with logging)
# --------------------------------------
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
logger.info(f"[EMB] Using device: {device}")

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

    text = unicodedata.normalize("NFKC", text)
    text = text.lower().strip()
    return text


# --------------------------------------
# EMBEDDING (with batching + tqdm)
# --------------------------------------
def embed(
    texts: Sequence[str],
    batch_size: int = 16,
    normalize: bool = True,
    max_length: int = 128,
) -> np.ndarray:

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

        words = t.split()
        if len(words) > max_length:
            t = " ".join(words[:max_length])

        processed.append(t)

    all_embs = []

    # Disable autograd
    with torch.no_grad():

        # tqdm progress bar
        total_batches = range(0, len(processed), batch_size)
        for start in tqdm(
            total_batches,
            desc=f"Embedding batches (bs={batch_size}, device={device})",
            ncols=100
        ):
            batch = processed[start:start + batch_size]

            # Jina model encode
            batch_emb = model.encode(batch, show_progress_bar=False)

            # Convert to numpy
            batch_emb = np.asarray(batch_emb, dtype=np.float32)

            all_embs.append(batch_emb)

    # Stack results
    if len(all_embs) == 1:
        return all_embs[0]

    return np.vstack(all_embs)
