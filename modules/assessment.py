# # modules/assessment.py

# from __future__ import annotations

# import json
# import re
# from typing import List, Dict, Any

# from langchain.chat_models import init_chat_model
# from langchain_core.messages import SystemMessage, HumanMessage

# from config.settings import GROQ_MODEL_NAME, logger
# from modules.scoring import score_factor_with_details


# def _parse_sdg_goal_from_factor(factor: str) -> str:
#     """Extract SDG number from keys like 'SDG_5_Gender_Equality'."""
#     try:
#         return factor.split("_")[1]
#     except Exception:
#         return "0"


# def _extract_json(raw_text: str) -> str:
#     """Recover a JSON object even if wrapped with ```json fences or surrounding text."""
#     raw = raw_text.strip()

#     # strip ```json fences
#     if raw.startswith("```"):
#         raw = re.sub(r"^```[a-zA-Z]*", "", raw)
#         raw = raw.replace("```", "").strip()

#     # already a JSON object
#     if raw.lstrip().startswith("{"):
#         return raw

#     # try to grab the first {...} block
#     m = re.search(r"\{.*\}", raw, flags=re.DOTALL)
#     return m.group(0).strip() if m else raw


# def _snippet(sentences: List[str], max_s: int = 15) -> str:
#     """Numbered snippet of evidence sentences to keep prompts small."""
#     if not sentences:
#         return "No raw evidence sentences were provided."
#     take = sentences[:max_s]
#     return "\n".join(f"{i+1}. {s}" for i, s in enumerate(take))


# def _as_list(val: Any) -> List[str]:
#     """Normalize optional list fields from the model."""
#     return val if isinstance(val, list) else []


# def _call_llm_json(llm, system_msg: str, user_prompt: str) -> Dict[str, Any]:
#     """
#     Generic helper:
#     - Calls the LLM with system + user messages.
#     - Extracts a JSON object from the response.
#     - Returns it as a Python dict, or raises on failure.
#     """
#     resp = llm.invoke([
#         SystemMessage(content=system_msg),
#         HumanMessage(content=user_prompt),
#     ])
#     raw = getattr(resp, "content", str(resp))
#     raw_json = _extract_json(raw)
#     data = json.loads(raw_json)
#     if not isinstance(data, dict):
#         raise ValueError("LLM did not return a JSON object.")
#     return data


# # ───────────────────────────── STAGE HELPERS ───────────────────────────── #


# def _stage_level_of_change(llm, factor: str, sentences: List[str]) -> Dict[str, Any]:
#     """
#     Stage 1: Decide the level_of_change and pick support sentences.
#     """
#     snippet = _snippet(sentences, max_s=20)
#     system = (
#         "You are an expert SDG co-benefit assessor. "
#         "Always respond with valid JSON only, no markdown."
#     )
#     user = f"""
# Factor: {factor}

# Cleaned evidence sentences (sample):
# {snippet}

# CLASSIFY level_of_change for this factor. Use ONLY these values:
# - "predicted_only"  (only forecasts or models, no observed changes yet)
# - "output"          (immediate deliverables: trainings held, stoves distributed, etc.)
# - "outcome"         (changes in behavior, access, practices, services)
# - "impact"          (changes in well-being, poverty, health, environment at scale)

# Choose the level based on the strongest evidence in the sentences.

# Also return up to 5 sentences from the evidence that best justify this choice.
# These should be copied exactly from the evidence text.

# Return STRICT JSON:

# {{
#   "level_of_change": "predicted_only" | "output" | "outcome" | "impact",
#   "level_support_sentences": ["...", "..."]
# }}
# """
#     return _call_llm_json(llm, system, user)


# def _stage_evidence_quality(llm, factor: str, sentences: List[str]) -> Dict[str, Any]:
#     """
#     Stage 2: Decide evidence_quality and pick support sentences.
#     """
#     snippet = _snippet(sentences, max_s=20)
#     system = (
#         "You are an expert SDG evidence assessor. "
#         "Always respond with valid JSON only, no markdown."
#     )
#     user = f"""
# Factor: {factor}

# Cleaned evidence sentences (sample):
# {snippet}

# CLASSIFY evidence_quality for this factor. Use ONLY:
# - "narrated"
# - "estimated"
# - "quantified"
# - "quantified_with_method"

# Guidance:
# - narrated: purely qualitative narrative; no explicit numbers.
# - estimated: rough numbers or ranges with no clear method (e.g. 'about 100 households').
# - quantified: specific numbers or statistics, but little or no method detail.
# - quantified_with_method: clear numbers AND explicit mention of surveys, sampling methods,
#   baselines, control groups, or similar methodological details.

# Return STRICT JSON:

# {{
#   "evidence_quality": "narrated" | "estimated" | "quantified" | "quantified_with_method",
#   "evidence_quality_support_sentences": ["...", "..."]
# }}
# """
#     return _call_llm_json(llm, system, user)


# def _stage_durability(llm, factor: str, sentences: List[str]) -> Dict[str, Any]:
#     """
#     Stage 3: Decide durability_measures, support sentences, and a short reason.
#     """
#     snippet = _snippet(sentences, max_s=20)
#     system = (
#         "You are an expert on durability of development interventions. "
#         "Always respond with valid JSON only, no markdown."
#     )
#     user = f"""
# Factor: {factor}

# Cleaned evidence sentences (sample):
# {snippet}

# Decide whether this factor has long-term durability measures.

# durability_measures = true if there is clear evidence of ANY of:
# - long-term contracts or legal agreements
# - permanent or long-lived institutions taking responsibility
# - maintenance or monitoring plans beyond the project period
# - revenue mechanisms or business models that sustain the activity

# durability_measures = false if you see no convincing long-term mechanism.

# Return STRICT JSON:

# {{
#   "durability_measures": true or false,
#   "durability_support_sentences": ["...", "..."],
#   "durability_reason": "1-3 sentence explanation of why you chose true/false."
# }}
# """
#     return _call_llm_json(llm, system, user)


# def _stage_sdg_claim_type(llm, factor: str, sentences: List[str]) -> Dict[str, Any]:
#     """
#     Stage 4: Decide whether the SDG claim is explicit, implicit, or unclear.
#     """
#     snippet = _snippet(sentences, max_s=30)
#     system = (
#         "You are an SDG claims classifier. "
#         "Always respond with valid JSON only, no markdown."
#     )
#     user = f"""
# Factor: {factor}

# Cleaned evidence sentences (sample):
# {snippet}

# Classify sdg_claim_type for this factor:

# - "explicit":
#     The documentation directly names SDGs or SDG targets, e.g.
#     "SDG 2", "Sustainable Development Goal 5", "Goal 5.5",
#     or uses an official SDG name such as "No Poverty (SDG 1)"
#     clearly in the context of SDG claims.

# - "implicit":
#     The SDG is never named explicitly, but the actions and outcomes clearly
#     align with this SDG factor (e.g. gender equality, improved health,
#     clean energy, decent work).

# - "unclear":
#     Evidence is too weak or ambiguous to tell, or the SDG link is very weak.

# Return STRICT JSON:

# {{
#   "sdg_claim_type": "explicit" | "implicit" | "unclear",
#   "sdg_claim_support_sentences": ["...", "..."]
# }}
# """
#     return _call_llm_json(llm, system, user)


# def _stage_excluded_reason(
#     llm,
#     factor: str,
#     sentences: List[str],
#     level_of_change: str | None,
#     evidence_quality: str | None,
# ) -> Dict[str, Any]:
#     """
#     Stage 5 (optional): Suggest excluded_reason, to stay close to original behaviour.

#     allowed values:
#       - "insufficient_evidence"
#       - "rated_under_other_SDG"
#       - null
#     """
#     # If there is almost nothing, short-circuit to insufficient_evidence.
#     if not sentences or len(sentences) < 3:
#         return {"excluded_reason": "insufficient_evidence"}

#     snippet = _snippet(sentences, max_s=20)
#     system = (
#         "You are an SDG rating expert. "
#         "You decide if a factor should be excluded from scoring. "
#         "Always respond with valid JSON only, no markdown."
#     )
#     user = f"""
# Factor: {factor}

# Cleaned evidence sentences (sample):
# {snippet}

# Current classification (for context):
# - level_of_change: {level_of_change}
# - evidence_quality: {evidence_quality}

# Decide excluded_reason. Use ONLY:
# - "insufficient_evidence"
# - "rated_under_other_SDG"
# - null   (use JSON null, not a string)

# Guidance:
# - Choose "insufficient_evidence" only if the factor's evidence is too weak,
#   contradictory, or not really about a meaningful co-benefit.
# - Choose "rated_under_other_SDG" if the evidence clearly belongs under a
#   different SDG factor and should not be double-counted here.
# - Choose null if this factor has enough evidence to be rated on its own.

# Return STRICT JSON:

# {{
#   "excluded_reason": "insufficient_evidence" | "rated_under_other_SDG" | null
# }}
# """
#     return _call_llm_json(llm, system, user)


# # ─────────────────────────── MAIN ENTRYPOINT ─────────────────────────── #


# def assess_factors_from_refined(
#     evidence_map: Dict[str, List[str]],
# ) -> List[Dict[str, Any]]:
#     """
#     evidence_map: { factor_name: [cleaned_sentence1, cleaned_sentence2, ...] }

#     For each factor, run multiple LLM stages to derive:

#       - sdg_goal (parsed from factor name)
#       - level_of_change
#       - evidence_quality
#       - durability_measures
#       - excluded_reason
#       - sdg_claim_type (explicit / implicit / unclear)

#     Plus support sentences & durability_reason for UI/traceability, and
#     a numeric score with breakdown via score_factor_with_details().
#     """

#     llm = init_chat_model(GROQ_MODEL_NAME, model_provider="groq")
#     results: List[Dict[str, Any]] = []

#     for factor, raw_evidence in evidence_map.items():
#         logger.info(f"[ASSESS] Assessing {factor}")

#         try:
#             # ── Stage 1: level_of_change ──
#             lvl_data = _stage_level_of_change(llm, factor, raw_evidence)
#             level_of_change = lvl_data.get("level_of_change")
#             lvl_sup = _as_list(lvl_data.get("level_support_sentences") or [])

#             # ── Stage 2: evidence_quality ──
#             eq_data = _stage_evidence_quality(llm, factor, raw_evidence)
#             evidence_quality = eq_data.get("evidence_quality")
#             eq_sup = _as_list(eq_data.get("evidence_quality_support_sentences") or [])

#             # ── Stage 3: durability ──
#             dur_data = _stage_durability(llm, factor, raw_evidence)
#             durability_measures = dur_data.get("durability_measures")
#             dur_sup = _as_list(dur_data.get("durability_support_sentences") or [])
#             dur_reason = dur_data.get("durability_reason")
#             if not isinstance(dur_reason, str):
#                 dur_reason = None

#             # ── Stage 4: sdg_claim_type ──
#             claim_data = _stage_sdg_claim_type(llm, factor, raw_evidence)
#             sdg_claim_type = claim_data.get("sdg_claim_type")
#             if sdg_claim_type not in ("explicit", "implicit", "unclear"):
#                 sdg_claim_type = "unclear"
#             claim_sup = _as_list(claim_data.get("sdg_claim_support_sentences") or [])

#             # ── Stage 5: excluded_reason ──
#             excl_data = _stage_excluded_reason(
#                 llm, factor, raw_evidence, level_of_change, evidence_quality
#             )
#             excluded_reason = excl_data.get("excluded_reason")
#             # Normalize excluded_reason
#             if excluded_reason not in ("insufficient_evidence", "rated_under_other_SDG"):
#                 excluded_reason = None

#             # ── Build assessment object ──
#             assessment: Dict[str, Any] = {
#                 "factor": factor,
#                 "sdg_goal": _parse_sdg_goal_from_factor(factor),

#                 "level_of_change": level_of_change,
#                 "evidence_quality": evidence_quality,
#                 "durability_measures": durability_measures,
#                 "excluded_reason": excluded_reason,

#                 "sdg_claim_type": sdg_claim_type,

#                 # For UI & traceability
#                 "durability_reason": dur_reason,

#                 "level_support_sentences": lvl_sup,
#                 "evidence_quality_support_sentences": eq_sup,
#                 "durability_support_sentences": dur_sup,
#                 "sdg_claim_support_sentences": claim_sup,
#             }

#             # ── Score calculation + breakdown ──
#             details = score_factor_with_details(assessment)
#             assessment["score"] = details["score"]
#             assessment["score_details"] = details

#             results.append(assessment)

#         except Exception as e:
#             logger.warning(f"[ASSESS] ERROR for {factor}: {e}")

#             # Conservative fallback when the LLM or parsing fails
#             results.append({
#                 "factor": factor,
#                 "sdg_goal": _parse_sdg_goal_from_factor(factor),

#                 "level_of_change": "predicted_only",
#                 "evidence_quality": "narrated",
#                 "durability_measures": False,
#                 "excluded_reason": "insufficient_evidence",

#                 "sdg_claim_type": "unclear",

                
#                 "durability_reason": "Fallback: insufficient evidence or model failure.",

#                 "level_support_sentences": [],
#                 "evidence_quality_support_sentences": [],
#                 "durability_support_sentences": [],
#                 "sdg_claim_support_sentences": [],

#                 "score": 0,
#                 "score_details": {
#                     "score": 0,
#                     "level_base": 0,
#                     "evidence_weight": 0.0,
#                     "durability_bonus": 0,
#                     "raw_score": 0.0,
#                     "excluded_by_reason": "insufficient_evidence",
#                 },
#             })

#     return results
