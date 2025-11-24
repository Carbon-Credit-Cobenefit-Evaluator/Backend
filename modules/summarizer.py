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
def chunk_text(text: str, max_words: int = 250) -> List[str]:
    """
    Splits the evidence text into safe, LLM-friendly chunks.
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
    messages = [
        SystemMessage(
            content=(
                "You are an expert analyst summarizing SDG co-benefit evidence in carbon "
                "project documents. Be precise, cautious, and avoid unsupported claims."
            )
        ),
        HumanMessage(
            content=(
                f"Factor: {factor}\n\n"
                f"Evidence excerpt:\n{chunk}\n\n"
                "Task:\n"
                "- Write a concise 2–4 sentence summary of ONLY the concrete actions, outputs, "
                "outcomes, and impacts.\n"
                "- Do NOT include generic SDG descriptions.\n"
                "- Do NOT infer benefits not explicitly supported.\n"
                "- Avoid exaggeration and normative language.\n"
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
    """
    text = " ".join(chunks)

    # Final compression step by LLM
    llm = init_chat_model(GROQ_MODEL_NAME, model_provider="groq")
    messages = [
        SystemMessage(
            content="You merge several partial summaries into a single coherent paragraph."
        ),
        HumanMessage(
            content=(
                f"SDG Factor: {factor}\n\n"
                f"Partial Summaries:\n{text}\n\n"
                "Task: Produce a single 3–5 sentence coherent summary capturing all main points, "
                "removing repetition and focusing only on concrete evidence."
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

    llm = init_chat_model(
        GROQ_MODEL_NAME,
        model_provider="groq",
        temperature=0.2,        # more deterministic
        max_tokens=450,         # prevent hallucination
    )

    summaries = []

    for factor, sentences in matches.items():
        logger.info(f"[SUM] Summarizing factor: {factor} ({len(sentences)} evidence sentences)")

        if not sentences:
            summaries.append({
                "factor": factor,
                "summary": "No evidence found in project documents."
            })
            continue

        evidence_text = " ".join(sentences)

        # 👇 split into safe chunks
        chunks = chunk_text(evidence_text, max_words=250)

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

        # If even chunk-level failed
        if not partial_summaries:
            summaries.append({
                "factor": factor,
                "summary": "Summary generation failed due to insufficient or unclear evidence."
            })
            continue

        # Merge partial summaries
        final_summary = merge_summaries(partial_summaries, factor)

        summaries.append({
            "factor": factor,
            "summary": final_summary,
        })

    return summaries
