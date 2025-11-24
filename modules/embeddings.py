import numpy as np
import torch
from transformers import AutoModel
from config.settings import JINA_MODEL_NAME

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model = AutoModel.from_pretrained(JINA_MODEL_NAME, trust_remote_code=True).to(device)

def embed(texts):
    return np.array(model.encode(texts, task="text-matching"))
# modules/embeddings.py

import numpy as np
import torch
from transformers import AutoModel
from config.settings import JINA_MODEL_NAME

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

print(f"[INFO] Loading Jina embedding model: {JINA_MODEL_NAME} on {device}...")
model = AutoModel.from_pretrained(JINA_MODEL_NAME, trust_remote_code=True).to(device)
print("[INFO] Jina model loaded.")

def embed(texts):
    """
    texts: list[str] or str
    returns: np.ndarray of shape (n, dim)
    """
    if isinstance(texts, str):
        texts = [texts]

    # Jina v2 models use encode(texts) WITHOUT 'task' parameter
    with torch.no_grad():
        embs = model.encode(texts)

    return np.array(embs)
