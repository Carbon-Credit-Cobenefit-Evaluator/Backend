# modules/assessment.py

import json
from typing import List, Dict, Any
from langchain.chat_models import init_chat_model
from langchain_core.messages import SystemMessage, HumanMessage
from config.settings import GROQ_MODEL_NAME
from modules.scoring import score_factor

def _parse_sdg_goal_from_factor(factor: str) -> str:
    # e.g. "SDG_5_Gender_Equality" -> "5"
    try:
        parts = factor.split("_")
        return parts[1]
    except Exception:
        return "0"

def assess_factors(summaries: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """
    summaries: [{ 'factor': str, 'summary': str }]
    returns: list of assessments with score and sdg info.
    """

    llm = init_chat_model(GROQ_MODEL_NAME, model_provider="groq")
    assessments: List[Dict[str, Any]] = []

    for item in summaries:
        factor = item["factor"]
        summary = item["summary"]
        print(f"[INFO] Assessing factor: {factor}")

        messages = [
            SystemMessage(
                content=(
                    "You are rating SDG co-benefit contributions for a carbon project using a "
                    "Calyx-style methodology. Respond with valid JSON only."
                )
            ),
            HumanMessage(
                content=f"""
Factor name: {factor}
Evidence summary: {summary}

1. Infer sdg_target as a string like "1.4", "5.5", "15.3" if you can, otherwise null.
2. Classify level_of_change as exactly one of:
   "predicted_only", "output", "outcome", "impact".
3. Classify evidence_quality as exactly one of:
   "narrated", "estimated", "quantified", "quantified_with_method".
4. Set durability_measures = true if there are signs of long-term mechanisms
   (maintenance plans, legal agreements, ongoing training, institutionalization),
   otherwise false.
5. If benefits are only planned or evidence is insufficient to show real change,
   set excluded_reason = "insufficient_evidence".
   If this contribution actually belongs under another SDG, set
   excluded_reason = "rated_under_other_SDG".
   Otherwise, excluded_reason = null.

Return ONLY a JSON object with keys:
  "sdg_target", "level_of_change", "evidence_quality",
  "durability_measures", "excluded_reason".
"""
            ),
        ]

        try:
            resp = llm.invoke(messages)
            raw_text = getattr(resp, "content", str(resp))
            data = json.loads(raw_text)

            assessment: Dict[str, Any] = {
                "factor": factor,
                "sdg_goal": _parse_sdg_goal_from_factor(factor),
                "sdg_target": data.get("sdg_target"),
                "level_of_change": data.get("level_of_change"),
                "evidence_quality": data.get("evidence_quality"),
                "durability_measures": data.get("durability_measures"),
                "excluded_reason": data.get("excluded_reason"),
            }

            assessment["score"] = score_factor(assessment)
            assessments.append(assessment)

        except Exception as e:
            print(f"[WARN] Failed to assess {factor}: {e}")
            assessments.append({
                "factor": factor,
                "sdg_goal": _parse_sdg_goal_from_factor(factor),
                "sdg_target": None,
                "level_of_change": "predicted_only",
                "evidence_quality": "narrated",
                "durability_measures": False,
                "excluded_reason": "insufficient_evidence",
                "score": 0,
            })

    return assessments
