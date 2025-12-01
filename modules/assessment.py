# modules/assessment.py

from __future__ import annotations
import json, re
from typing import List, Dict, Any
from langchain.chat_models import init_chat_model
from langchain_core.messages import SystemMessage, HumanMessage

from config.settings import GROQ_MODEL_NAME, logger
from modules.scoring import score_factor_with_details


def _parse_sdg_goal_from_factor(factor: str) -> str:
    """Extract SDG number from keys like 'SDG_5_Gender_Equality'."""
    try:
        return factor.split("_")[1]
    except Exception:
        return "0"


def _extract_json(raw_text: str) -> str:
    """Recover a JSON object even if wrapped with ```json fences."""
    raw = raw_text.strip()

    # strip ```json fences
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*", "", raw)
        raw = raw.replace("```", "").strip()

    # already a JSON object
    if raw.lstrip().startswith("{"):
        return raw

    # try to grab the first {...} block
    m = re.search(r"\{.*\}", raw, flags=re.DOTALL)
    return m.group(0).strip() if m else raw


def _snippet(sentences: List[str], max_s: int = 15) -> str:
    """Numbered snippet of raw evidence sentences."""
    if not sentences:
        return "No raw evidence sentences were provided."
    take = sentences[:max_s]
    return "\n".join(f"{i+1}. {s}" for i, s in enumerate(take))


def assess_factors(
    summaries: List[Dict[str, str]],
    evidence_map: Dict[str, List[str]],
) -> List[Dict[str, Any]]:
    """
    summaries: [{ "factor": str, "summary": str }]
    evidence_map: { factor_name: [sentence1, sentence2, ...] }

    Returns a list of assessments with:
      - sdg_goal, sdg_target
      - level_of_change, evidence_quality, durability_measures, excluded_reason
      - sdg_claim_type (explicit / implicit / unclear)
      - support sentences for level, evidence quality, durability, claim type
      - durability_reason (short explanation)
      - summary + raw_evidence_sentences (for UI)
      - score + score_details
    """

    llm = init_chat_model(GROQ_MODEL_NAME, model_provider="groq")
    results: List[Dict[str, Any]] = []

    for item in summaries:
        factor = item["factor"]
        summary = item["summary"]
        raw_evidence = evidence_map.get(factor, [])

        logger.info(f"[ASSESS] Assessing {factor}")

        prompt = f"""
Factor: {factor}

Condensed Evidence Summary:
\"\"\"{summary}\"\"\"

Raw Evidence Sentences (sample):
{_snippet(raw_evidence)}

────────────────────────────────────────────────────────────
CLASSIFY:

1) level_of_change → EXACTLY one:
   - "predicted_only"
   - "output"
   - "outcome"
   - "impact"

2) evidence_quality → EXACTLY one:
   - "narrated"
   - "estimated"
   - "quantified"
   - "quantified_with_method"

3) sdg_target → string like "1.4", "5.5", "15.3" or null

4) durability_measures:
   true  = long-term mechanisms (contracts, permanent institutions,
                                 maintenance plans, monitoring plans)
   false = no long-term mechanism

5) excluded_reason:
   - "insufficient_evidence"
   - "rated_under_other_SDG"
   - null

──────────────────────── EXPLICIT vs IMPLICIT SDG CLAIM ────────────────────────
Classify sdg_claim_type as:

- "explicit":
    The project documentation explicitly mentions SDGs or SDG targets
    for this contribution (e.g. “contributes to SDG 5”, “Goal 5.5”, SDG icons).

- "implicit":
    The documents never name SDGs for this contribution, but the actions
    and outcomes clearly align with this SDG factor.

- "unclear":
    Not enough information to tell if the SDG is claimed explicitly
    or the mapping is very weak / ambiguous.

Also return:
- sdg_claim_support_sentences:
    1–5 raw sentences that best show WHY you chose explicit / implicit / unclear.

────────────────────────────────────────────────────────────
JUSTIFY WITH RAW EVIDENCE:

- level_support_sentences:
    Up to 5 raw sentences that justify the level_of_change.

- evidence_quality_support_sentences:
    Up to 5 sentences showing the type of evidence
    (narrated / estimated / quantified / method).

- durability_support_sentences:
    Up to 5 raw sentences showing why durability_measures is TRUE or FALSE.

- durability_reason:
    A short 1–3 sentence explanation of durability classification.

────────────────────────────────────────────────────────────
RETURN STRICT JSON ONLY:

{{
  "sdg_target": ...,
  "level_of_change": ...,
  "evidence_quality": ...,
  "durability_measures": ...,
  "excluded_reason": ...,
  "sdg_claim_type": ...,
  "level_support_sentences": [...],
  "evidence_quality_support_sentences": [...],
  "durability_support_sentences": [...],
  "sdg_claim_support_sentences": [...],
  "durability_reason": "..."
}}
"""

        try:
            resp = llm.invoke([
                SystemMessage(
                    content="You are an expert SDG co-benefit assessor. Return ONLY valid JSON."
                ),
                HumanMessage(content=prompt)
            ])

            raw = getattr(resp, "content", str(resp))
            parsed = json.loads(_extract_json(raw))

            # Normalize list fields
            def _as_list(val):
                return val if isinstance(val, list) else []

            lvl_sup = _as_list(parsed.get("level_support_sentences") or [])
            eq_sup = _as_list(parsed.get("evidence_quality_support_sentences") or [])
            dur_sup = _as_list(parsed.get("durability_support_sentences") or [])
            claim_sup = _as_list(parsed.get("sdg_claim_support_sentences") or [])

            dur_reason = parsed.get("durability_reason")
            if not isinstance(dur_reason, str):
                dur_reason = None

            sdg_claim_type = parsed.get("sdg_claim_type")
            if sdg_claim_type not in ("explicit", "implicit", "unclear"):
                sdg_claim_type = "unclear"

            assessment: Dict[str, Any] = {
                "factor": factor,
                "sdg_goal": _parse_sdg_goal_from_factor(factor),
                "sdg_target": parsed.get("sdg_target"),
                "level_of_change": parsed.get("level_of_change"),
                "evidence_quality": parsed.get("evidence_quality"),
                "durability_measures": parsed.get("durability_measures"),
                "excluded_reason": parsed.get("excluded_reason"),

                # NEW: SDG claim type
                "sdg_claim_type": sdg_claim_type,

                # For UI & traceability
                "summary": summary,
                "raw_evidence_sentences": raw_evidence,
                "durability_reason": dur_reason,

                "level_support_sentences": lvl_sup,
                "evidence_quality_support_sentences": eq_sup,
                "durability_support_sentences": dur_sup,
                "sdg_claim_support_sentences": claim_sup,
            }

            # Score calculation + breakdown
            details = score_factor_with_details(assessment)
            assessment["score"] = details["score"]
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

                "sdg_claim_type": "unclear",

                "summary": summary,
                "raw_evidence_sentences": raw_evidence,
                "durability_reason": "Fallback: insufficient evidence or model failure.",

                "level_support_sentences": [],
                "evidence_quality_support_sentences": [],
                "durability_support_sentences": [],
                "sdg_claim_support_sentences": [],

                "score": 0,
                "score_details": {
                    "score": 0,
                    "level_base": 0,
                    "evidence_weight": 0.0,
                    "durability_bonus": 0,
                    "raw_score": 0.0,
                    "excluded_by_reason": "insufficient_evidence",
                },
            })

    return results
