# modules/evidence_refiner.py
from typing import Dict, List
from langchain.chat_models import init_chat_model
from langchain_core.messages import SystemMessage, HumanMessage
from config.settings import GROQ_MODEL_NAME, logger


def _chunk_sentences(sentences: List[str], max_per_chunk: int = 25) -> List[List[str]]:
    chunks = []
    for i in range(0, len(sentences), max_per_chunk):
        chunks.append(sentences[i:i + max_per_chunk])
    return chunks


def refine_evidence(evidence_map: Dict[str, List[str]]) -> Dict[str, List[str]]:
    """
    Input: { factor: [raw sentences...] }
    Output: { factor: [cleaned/refined sentences...] }
    """

    llm = init_chat_model(GROQ_MODEL_NAME, model_provider="groq", temperature=0.2)

    refined: Dict[str, List[str]] = {}

    for factor, sentences in evidence_map.items():
        logger.info(f"[REFINE] Refining evidence for {factor} ({len(sentences)} sentences)")
        if not sentences:
            refined[factor] = []
            continue

        chunks = _chunk_sentences(sentences, max_per_chunk=25)
        cleaned_sentences: List[str] = []

        for chunk in chunks:
            prompt = (
                "You are cleaning extracted sentences from noisy PDF documents.\n\n"
                "Task:\n"
                "- For EACH input sentence, output a cleaned version.\n"
                "- Fix grammar and remove OCR artifacts, but PRESERVE all numbers, units, "
                "dates, locations, and actors.\n"
                "- Do NOT merge different sentences.\n"
                "- Do NOT drop any sentence.\n"
                "- Do NOT invent any new facts.\n\n"
                "Return JSON ONLY in this form:\n"
                "{ \"cleaned\": [\"...\", \"...\", ...] }\n\n"
                "Original sentences:\n"
                + "\n".join(f"- {s}" for s in chunk)
            )

            resp = llm.invoke([
                SystemMessage(content="You rewrite sentences cleanly without changing their factual content."),
                HumanMessage(content=prompt),
            ])

            import json, re
            raw = getattr(resp, "content", str(resp)).strip()

            # basic recovery of JSON
            if raw.startswith("```"):
                raw = re.sub(r"^```[a-zA-Z]*", "", raw)
                raw = raw.replace("```", "").strip()
            data = json.loads(raw)
            cleaned_list = data.get("cleaned") or []

            # fallback: if something goes wrong, keep originals
            if not isinstance(cleaned_list, list) or not cleaned_list:
                cleaned_list = chunk

            cleaned_sentences.extend(cleaned_list)

        refined[factor] = cleaned_sentences

    return refined
