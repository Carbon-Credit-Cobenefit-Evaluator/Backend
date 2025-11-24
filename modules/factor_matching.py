# modules/factor_matching.py

from __future__ import annotations

from typing import List, Dict, Sequence, Optional
import numpy as np

from config.factor_queries import factor_queries
from config.settings import SIMILARITY_THRESHOLD, logger
from modules.embeddings import embed

# -----------------------------------------
# Precompute factor embeddings once
# -----------------------------------------
FACTOR_SENTENCES: List[str] = []
FACTOR_LABELS: List[str] = []

for factor, data in factor_queries.items():
    for s in data["example_sentences"]:
        FACTOR_SENTENCES.append(s)
        FACTOR_LABELS.append(factor)

logger.info(f"[MATCH] Prepared {len(FACTOR_SENTENCES)} factor prototype sentences "
            f"for {len(set(FACTOR_LABELS))} SDG factors.")

FACTOR_EMB: np.ndarray = embed(FACTOR_SENTENCES)
if FACTOR_EMB.size == 0:
    logger.error("[MATCH] Factor embeddings are empty! Check factor_queries or embedding model.")
else:
    # L2-normalize so dot product = cosine similarity
    FACTOR_EMB = FACTOR_EMB / (np.linalg.norm(FACTOR_EMB, axis=1, keepdims=True) + 1e-9)
    logger.info(f"[MATCH] Factor embedding matrix shape: {FACTOR_EMB.shape}")


# -----------------------------------------
# Main matching function
# -----------------------------------------
def match_factors(
    sentences: Sequence[Dict[str, str]],
    top_k: int = 1,
    min_similarity: Optional[float] = None,
) -> Dict[str, List[str]]:
    """
    Match project sentences to SDG factors using Jina embeddings.

    Args:
        sentences:
            List of dicts: { "pdf": str, "text": str }
        top_k:
            How many top factors to allow per sentence.
            - 1  => behaves like your original code (one best factor)
            - >1 => sentence can contribute to multiple SDGs if similarity is high
        min_similarity:
            Override global SIMILARITY_THRESHOLD if given.

    Returns:
        Dict[str, List[str]]:
            { "SDG_1_No_Poverty": ["sentence1", "sentence2", ...], ... }
    """
    if min_similarity is None:
        min_sim = SIMILARITY_THRESHOLD
    else:
        min_sim = float(min_similarity)

    if not sentences:
        logger.warning("[MATCH] No sentences passed into match_factors().")
        return {}

    texts = [s["text"] for s in sentences]
    sent_emb = embed(texts)

    if sent_emb.size == 0:
        logger.warning("[MATCH] Sentence embeddings are empty. Returning no matches.")
        return {}

    # Normalize sentence embeddings for cosine similarity
    sent_emb = sent_emb / (np.linalg.norm(sent_emb, axis=1, keepdims=True) + 1e-9)

    # Cosine similarity via dot product of normalized vectors
    # sim[i, j] = similarity between sentence i and factor example j
    sim: np.ndarray = sent_emb @ FACTOR_EMB.T   # shape: [num_sentences, num_factor_examples]

    results: Dict[str, List[str]] = {f: [] for f in factor_queries.keys()}

    num_assigned = 0

    for i, row in enumerate(sim):
        # If top_k == 1, fast path
        if top_k == 1:
            j = int(np.argmax(row))
            score = float(row[j])
            if score >= min_sim:
                factor = FACTOR_LABELS[j]
                results[factor].append(sentences[i]["text"])
                num_assigned += 1
        else:
            # Sort factor examples by similarity, descending
            idxs = np.argsort(-row)[:top_k]
            matched_any = False
            for j in idxs:
                score = float(row[j])
                if score < min_sim:
                    continue
                factor = FACTOR_LABELS[j]
                results[factor].append(sentences[i]["text"])
                matched_any = True
            if matched_any:
                num_assigned += 1

    # Drop empty factors
    results = {k: v for k, v in results.items() if v}

    logger.info(
        f"[MATCH] Processed {len(sentences)} sentences → "
        f"{num_assigned} sentences assigned to {len(results)} factors "
        f"(top_k={top_k}, min_sim={min_sim})."
    )

    return results
