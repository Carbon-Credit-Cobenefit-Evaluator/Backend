# modules/assessment.py

from __future__ import annotations
import json, re
from typing import List, Dict, Any
from langchain.chat_models import init_chat_model
from langchain_core.messages import SystemMessage, HumanMessage

from config.settings import GROQ_MODEL_NAME, logger
from modules.scoring import score_factor


def _parse_sdg_goal_from_factor(factor: str) -> str:
    try:
        return factor.split("_")[1]
    except:
        return "0"


def _extract_json(raw_text: str) -> str:
    raw = raw_text.strip()

    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*", "", raw)
        raw = raw.replace("```", "").strip()

    if raw.lstrip().startswith("{"):
        return raw

    m = re.search(r"\{.*\}", raw, flags=re.DOTALL)
    return m.group(0).strip() if m else raw


def _snippet(sentences: List[str], max_s=15) -> str:
    if not sentences:
        return "No raw evidence sentences."
    take = sentences[:max_s]
    return "\n".join([f"{i+1}. {s}" for i, s in enumerate(take)])


def assess_factors(summaries: List[Dict[str, str]], evidence_map: Dict[str, List[str]]) -> List[Dict[str, Any]]:
    llm = init_chat_model(GROQ_MODEL_NAME, model_provider="groq")
    results = []

    for item in summaries:
        factor = item["factor"]
        summary = item["summary"]
        evidence = evidence_map.get(factor, [])

        logger.info(f"[ASSESS] Assessing {factor}")

        messages = [
            SystemMessage(content="You are an SDG co-benefit assessor. Return ONLY valid JSON."),
            HumanMessage(
                content=f"""
Factor: {factor}

Condensed Summary:
\"\"\"{summary}\"\"\"

Raw Evidence:
{_snippet(evidence)}

You must classify:
- sdg_target (string or null)
- level_of_change: "predicted_only" | "output" | "outcome" | "impact"
- evidence_quality: "narrated" | "estimated" | "quantified" | "quantified_with_method"
- durability_measures: true | false
- excluded_reason: string or null

Also return:
- level_support_sentences: up to 5 sentences from RAW evidence
- evidence_quality_support_sentences: up to 5 sentences from RAW evidence

Return ONLY JSON with these keys.
"""
            )
        ]

        try:
            resp = llm.invoke(messages)
            raw = getattr(resp, "content", str(resp))
            parsed = json.loads(_extract_json(raw))

            assessment = {
                "factor": factor,
                "sdg_goal": _parse_sdg_goal_from_factor(factor),
                "sdg_target": parsed.get("sdg_target"),
                "level_of_change": parsed.get("level_of_change"),
                "evidence_quality": parsed.get("evidence_quality"),
                "durability_measures": parsed.get("durability_measures"),
                "excluded_reason": parsed.get("excluded_reason"),
                "level_support_sentences": parsed.get("level_support_sentences") or [],
                "evidence_quality_support_sentences": parsed.get("evidence_quality_support_sentences") or [],
            }

            score, details = score_factor(assessment)
            assessment["score"] = score
            assessment["score_details"] = details

            results.append(assessment)

        except Exception as e:
            logger.warning(f"[ASSESS] ERROR for {factor}: {e}")
            results.append({
                "factor": factor,
                "sdg_goal": _parse_sdg_goal_from_factor(factor),
                "sdg_target": None,
                "level_of_change": "predicted_only",
                "evidence_quality": "narrated",
                "durability_measures": False,
                "excluded_reason": "insufficient_evidence",
                "level_support_sentences": [],
                "evidence_quality_support_sentences": [],
                "score": 0,
                "score_details": {
                    "level_base": 0,
                    "evidence_weight": 0.0,
                    "durability_bonus": 0,
                    "raw_score": 0.0,
                    "score": 0,
                }
            })

    return results
