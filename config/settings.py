import os

# ------ API KEY ------
os.environ["GROQ_API_KEY"] = "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"

# ------ PATHS ------
PROJECTS_ROOT = r"D:\DATAFYP\All projects"
BASE_OUTPUT_DIR = r"D:\DATAFYP\outputs"
os.makedirs(BASE_OUTPUT_DIR, exist_ok=True)

# ------ MODELS ------
SIMILARITY_THRESHOLD = 0.65
JINA_MODEL_NAME = "jinaai/jina-embeddings-v2-base-en"
GROQ_MODEL_NAME = "openai/gpt-oss-20b"

# ------ NLP ------
SPACY_MODEL = "en_core_web_sm"
