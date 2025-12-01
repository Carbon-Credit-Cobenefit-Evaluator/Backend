# modules/evidence_refiner.py

from typing import Dict, List
import json
import re

from langchain.chat_models import init_chat_model
from langchain_core.messages import SystemMessage, HumanMessage

from config.settings import GROQ_MODEL_NAME, logger


def _extract_json_block(raw: str) -> str:
    """Recover a JSON object even if wrapped with ``` fences or extra text."""
    raw = raw.strip()

    # strip ```json fences if present
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*", "", raw)
        raw = raw.replace("```", "").strip()

    # if it already starts with {, use as is
    if raw.lstrip().startswith("{"):
        return raw

    # otherwise, try to grab the first {...} block
    m = re.search(r"\{.*\}", raw, flags=re.DOTALL)
    return m.group(0).strip() if m else raw


def _chunk_sentences(sentences: List[str], max_per_chunk: int = 25) -> List[List[str]]:
    """Split a long list of sentences into smaller chunks."""
    chunks: List[List[str]] = []
    for i in range(0, len(sentences), max_per_chunk):
        chunks.append(sentences[i:i + max_per_chunk])
    return chunks


def _fallback_refine_chunk(llm, chunk: List[str]) -> List[str]:
    """
    Fallback cleaning if JSON mode fails:
    - First try: one cleaned sentence per line (approx 1:1).
    - If count > original: truncate to match.
    - If count < original: do per-sentence fallback for this chunk.
    """
    prompt = (
        "You are cleaning extracted sentences from noisy PDF documents.\n\n"
        "Task:\n"
        "- For EACH input sentence, output a cleaned version on its own line.\n"
        "- Preserve order: line 1 corresponds to sentence 1, etc.\n"
        "- Fix grammar and remove OCR artifacts, but PRESERVE all numbers, units, "
        "dates, locations, and actors.\n"
        "- Do NOT merge, drop, or add sentences.\n"
        "- Do NOT invent any new facts.\n\n"
        "Format:\n"
        "- Return ONLY the cleaned sentences, one per line.\n"
        "- Do NOT return JSON.\n"
        "- Do NOT include bullet points, numbering, or any extra commentary.\n\n"
        "Original sentences:\n"
        + "\n".join(f"- {s}" for s in chunk)
    )

    resp = llm.invoke([
        SystemMessage(
            content=(
                "You rewrite sentences cleanly without changing their factual content. "
                "Return ONLY the cleaned sentences, one per line, no extra text."
            )
        ),
        HumanMessage(content=prompt),
    ])

    raw = getattr(resp, "content", str(resp)).strip()
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]

    if len(lines) == len(chunk):
        return lines

    # If the model produced too many lines, keep the first N.
    if len(lines) > len(chunk):
        logger.warning(
            f"[REFINE] Fallback cleaner returned {len(lines)} lines for "
            f"{len(chunk)} sentences. Truncating to {len(chunk)}."
        )
        return lines[:len(chunk)]

    # If it produced fewer lines, do a per-sentence micro-fallback.
    logger.warning(
        f"[REFINE] Fallback cleaner returned {len(lines)} lines for "
        f"{len(chunk)} sentences. Falling back to per-sentence cleaning."
    )

    cleaned: List[str] = []
    for s in chunk:
        single_prompt = (
            "Clean the following sentence from a noisy PDF.\n"
            "- Fix grammar and remove OCR artifacts.\n"
            "- PRESERVE all numbers, units, dates, locations, and actors.\n"
            "- Do NOT invent new facts.\n"
            "- Return ONLY the cleaned sentence, no explanations.\n\n"
            f"Sentence:\n{s}"
        )

        single_resp = llm.invoke([
            SystemMessage(
                content=(
                    "You rewrite sentences cleanly without changing their factual content. "
                    "Return ONLY the cleaned sentence."
                )
            ),
            HumanMessage(content=single_prompt),
        ])

        single_raw = getattr(single_resp, "content", str(single_resp)).strip()
        # Take first non-empty line as cleaned version
        first_line = ""
        for ln in single_raw.splitlines():
            ln = ln.strip()
            if ln:
                first_line = ln
                break
        cleaned.append(first_line or s)  # fallback to original only if model sends nothing

    return cleaned


def refine_evidence(evidence_map: Dict[str, List[str]]) -> Dict[str, List[str]]:
    """
    Input:  { factor: [raw sentences...] }
    Output: { factor: [cleaned/refined sentences...] }

    Every sentence is cleaned via Groq:
      - First attempt: JSON mode ({ "cleaned": [...] }).
      - If JSON parsing/structure fails: chunk-level 'one sentence per line' fallback.
      - If that returns fewer lines than inputs: per-sentence fallback.
    We never silently skip Groq; each sentence passes through the model at least once.
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
                SystemMessage(
                    content=(
                        "You rewrite sentences cleanly without changing their factual content. "
                        "Return ONLY valid JSON in the requested format."
                    )
                ),
                HumanMessage(content=prompt),
            ])

            raw = getattr(resp, "content", str(resp)).strip()
            raw_json = _extract_json_block(raw)

            try:
                data = json.loads(raw_json)
                cleaned_list = data.get("cleaned") or []
                if not isinstance(cleaned_list, list) or len(cleaned_list) != len(chunk):
                    raise ValueError(
                        f"JSON cleaner returned invalid structure or length "
                        f"(got {len(cleaned_list)} for {len(chunk)} sentences)."
                    )
            except Exception as e:
                logger.warning(
                    f"[REFINE] JSON parse or structure failed for factor {factor}: {e}. "
                    f"Falling back to line-by-line cleaner."
                )
                cleaned_list = _fallback_refine_chunk(llm, chunk)

            cleaned_sentences.extend(cleaned_list)

        refined[factor] = cleaned_sentences

    return refined
