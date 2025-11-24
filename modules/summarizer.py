# modules/summarizer.py

from __future__ import annotations

import re
import time
from typing import Dict, List

from langchain.chat_models import init_chat_model
from langchain_core.messages import SystemMessage, HumanMessage
from config.settings import GROQ_MODEL_NAME, logger


# -----------------------------------------------------------
# Helper: split very long evidence into multiple chunks
# -----------------------------------------------------------
def chunk_text(text: str, max_words: int = 400) -> List[str]:
    """
    Splits the evidence text into LLM-friendly chunks.

    We use a relatively high max_words to keep context rich, so that
    each chunk summary can retain more detail.
    """
    words = text.split()
    if len(words) <= max_words:
        return [text]

    chunks = []
    for i in range(0, len(words), max_words):
        chunks.append(" ".join(words[i:i + max_words]))
    return chunks


# -----------------------------------------------------------
# Helper: sanitize LLM output (remove markdown, weird chars)
# -----------------------------------------------------------
def clean_summary(text: str) -> str:
    """
    Post-processing cleanup to remove markdown artifacts, hallucinated tags,
    repeated phrases, and formatting noise.
    """
    text = text.strip()

    # Remove Markdown artifacts
    text = re.sub(r"[*_`#>]+", " ", text)

    # Remove hallucinated labels
    text = re.sub(r"(SUMMARY|FINAL SUMMARY|ABSTRACT)[:\- ]*", "", text, flags=re.I)

    # Normalize whitespace
    text = " ".join(text.split())
    return text


# -----------------------------------------------------------
# Helper: ask LLM to summarize a single chunk
# -----------------------------------------------------------
def summarize_chunk(llm, factor: str, chunk: str) -> str:
    """
    Produce a fairly detailed chunk-level summary.
    """
    messages = [
        SystemMessage(
            content=(
                "You are an expert analyst summarizing SDG co-benefit evidence in carbon "
                "project documents. Be precise and evidence-based."
            )
        ),
        HumanMessage(
            content=(
                f"SDG factor: {factor}\n\n"
                f"Evidence excerpt (from one or more project documents):\n{chunk}\n\n"
                "Task:\n"
                "- Write a DETAILED summary of about 4–7 sentences.\n"
                "- Focus ONLY on concrete actions, outputs, outcomes, impacts and mechanisms.\n"
                "- Preserve specific details: numbers, years, locations, project actors, "
                "types of infrastructure, training topics, methodologies, and monitoring evidence.\n"
                "- Avoid generic SDG theory (e.g., do NOT explain what SDG 5 is in general).\n"
                "- Do NOT invent benefits that are not clearly supported by the text.\n"
            )
        ),
    ]

    response = llm.invoke(messages)
    summary = getattr(response, "content", str(response))
    return clean_summary(summary)


# -----------------------------------------------------------
# Helper: merge multiple chunk summaries into one final summary
# -----------------------------------------------------------
def merge_summaries(chunks: List[str], factor: str) -> str:
    """
    Compress multiple chunk summaries into a polished final summary.

    Here we still keep things quite detailed: think 1–2 rich paragraphs.
    """
    text = " ".join(chunks)

    llm = init_chat_model(GROQ_MODEL_NAME, model_provider="groq")
    messages = [
        SystemMessage(
            content=(
                "You merge several partial summaries about the SAME SDG co-benefit into a "
                "single coherent narrative. Do NOT drop important concrete details."
            )
        ),
        HumanMessage(
            content=(
                f"SDG Factor: {factor}\n\n"
                f"Partial summaries (from different evidence chunks):\n{text}\n\n"
                "Task:\n"
                "- Produce a single, detailed summary (roughly 6–10 sentences, or 2 short paragraphs).\n"
                "- Merge overlapping points but KEEP important details: specific locations, dates, "
                "numbers, infrastructure types, livelihood changes, monitoring evidence, etc.\n"
                "- Make the story readable and logically ordered (from activities → outputs → outcomes/impacts where possible).\n"
                "- Do NOT add generic SDG explanations or speculative benefits that are not clearly supported.\n"
            )
        ),
    ]

    out = llm.invoke(messages)
    final_text = getattr(out, "content", str(out))
    return clean_summary(final_text)


# -----------------------------------------------------------
# MAIN FUNCTION
# -----------------------------------------------------------
def summarize_factors(matches: Dict[str, List[str]]) -> List[Dict]:
    """
    matches: { factor_name: [sentence1, sentence2, ...] }
    returns: [ { "factor": ..., "summary": ... }, ... ]
    """

    # Allow more tokens so the model can write longer summaries.
    llm = init_chat_model(
        GROQ_MODEL_NAME,
        model_provider="groq",
        temperature=0.2,      # keep it fairly deterministic
        max_tokens=800,       # more room for detailed summaries
    )

    summaries = []

    for factor, sentences in matches.items():
        logger.info(f"[SUM] Summarizing factor: {factor} ({len(sentences)} evidence sentences)")

        if not sentences:
            summaries.append({
                "factor": factor,
                "summary": "No evidence found in project documents for this SDG factor."
            })
            continue

        evidence_text = " ".join(sentences)

        # Split into fairly large chunks to keep context but stay under LLM limits
        chunks = chunk_text(evidence_text, max_words=400)

        partial_summaries = []

        # Multiple retries for robustness
        for chunk in chunks:
            retry = 0
            while retry < 3:
                try:
                    partial = summarize_chunk(llm, factor, chunk)
                    partial_summaries.append(partial)
                    break
                except Exception as e:
                    logger.warning(f"[SUM] Retry {retry+1}/3 for factor {factor}: {e}")
                    retry += 1
                    time.sleep(1)

        if not partial_summaries:
            summaries.append({
                "factor": factor,
                "summary": "Summary generation failed due to insufficient or unclear evidence."
            })
            continue

        # Merge partial summaries into a detailed final narrative
        final_summary = merge_summaries(partial_summaries, factor)

        summaries.append({
            "factor": factor,
            "summary": final_summary,
        })

    return summaries
