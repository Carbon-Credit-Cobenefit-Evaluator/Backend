import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from config.factor_queries import factor_queries
from config.settings import SIMILARITY_THRESHOLD
from modules.embeddings import embed

def match_factors(sentences):
    factor_sents = []
    factor_labels = []

    for factor, data in factor_queries.items():
        for s in data["example_sentences"]:
            factor_sents.append(s)
            factor_labels.append(factor)

    factor_emb = embed(factor_sents)
    sent_emb = embed([s["text"] for s in sentences])

    sim = cosine_similarity(sent_emb, factor_emb)

    results = {f: [] for f in factor_queries.keys()}

    max_idx = np.argmax(sim, axis=1)
    max_val = np.max(sim, axis=1)

    for i, score in enumerate(max_val):
        if score >= SIMILARITY_THRESHOLD:
            results[factor_labels[max_idx[i]]].append(sentences[i]["text"])

    return {k: v for k, v in results.items() if v}
