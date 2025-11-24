# modules/scoring.py

from typing import Dict, List, Any
import statistics

# --------- FACTOR-LEVEL SCORE (Calyx-style) ---------

def score_factor(assessment: Dict[str, Any]) -> int:
    """
    assessment keys expected:
      - level_of_change: one of "predicted_only", "output", "outcome", "impact"
      - evidence_quality: "narrated" | "estimated" | "quantified" | "quantified_with_method"
      - durability_measures: bool
      - excluded_reason: str or None
    Returns 0 if excluded, else 1–15.
    """

    if assessment.get("excluded_reason"):
        # Calyx would treat this as 'excluded' – you can ignore in aggregation
        return 0

    level = assessment.get("level_of_change", "")
    evid = assessment.get("evidence_quality", "")
    durability = bool(assessment.get("durability_measures", False))

    # Level of change – outcomes get highest weight (Calyx logic)
    level_base = {
        "predicted_only": 0,   # only planned, no real change yet
        "output": 4,
        "outcome": 7,          # highest weight
        "impact": 9,           # slightly below max because attribution is hard
    }.get(level, 0)

    # Evidence quality – stronger evidence boosts score
    evidence_weight = {
        "narrated": 0.6,
        "estimated": 0.8,
        "quantified": 1.0,
        "quantified_with_method": 1.2,
    }.get(evid, 0.6)

    durability_bonus = 2 if durability else 0

    raw = level_base * evidence_weight + durability_bonus

    if raw <= 0:
        return 0

    score = int(round(raw))
    # Clamp to 1–15 (Calyx mentions contribution scores up to ~15)
    return max(1, min(15, score))


# --------- MAP NUMERIC SCORE TO 1+..5+ BAND ---------

def map_score_to_rating(avg_score: float) -> str:
    """
    Map an average contribution score (1–15) to a Calyx-style 1+–5+ band.
    You can tune these thresholds later.
    """
    if avg_score >= 12:
        return "5+"
    if avg_score >= 9:
        return "4+"
    if avg_score >= 6:
        return "3+"
    if avg_score >= 3:
        return "2+"
    return "1+"


# --------- AGGREGATION HELPERS ---------

def aggregate_by_sdg(assessments: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Input: list of factor-level assessments, each with:
      - factor (e.g. 'SDG_5_Gender_Equality')
      - sdg_goal (e.g. '5')
      - sdg_target (e.g. '5.5' or None)
      - score (0–15)
    Output: {
      "overall": {...},
      "by_sdg": {
         "5": {...},
         "13": {...},
         ...
      }
    }
    """

    # Filter out excluded (score = 0)
    valid = [a for a in assessments if a.get("score", 0) > 0]

    if not valid:
        return {
            "overall": {
                "average_score": 0.0,
                "rating": "1+",
                "num_contributions": 0,
            },
            "by_sdg": {}
        }

    # --- overall ---
    overall_scores = [a["score"] for a in valid]
    overall_avg = statistics.mean(overall_scores)
    overall_rating = map_score_to_rating(overall_avg)

    # --- per SDG goal ---
    sdg_groups: Dict[str, List[int]] = {}
    sdg_targets: Dict[str, Dict[str, List[int]]] = {}

    for a in valid:
        goal = str(a.get("sdg_goal"))  # "1", "5", etc.
        target = a.get("sdg_target")   # "5.5" or None
        score = a["score"]

        sdg_groups.setdefault(goal, []).append(score)

        if target:
            sdg_targets.setdefault(goal, {}).setdefault(target, []).append(score)

    by_sdg: Dict[str, Any] = {}
    for goal, scores in sdg_groups.items():
        avg = statistics.mean(scores)
        rating = map_score_to_rating(avg)

        # per-target stats (optional but nice for dashboard)
        per_target_stats = {}
        for t, tscores in sdg_targets.get(goal, {}).items():
            t_avg = statistics.mean(tscores)
            t_rating = map_score_to_rating(t_avg)
            per_target_stats[t] = {
                "average_score": t_avg,
                "rating": t_rating,
                "num_contributions": len(tscores),
            }

        by_sdg[goal] = {
            "average_score": avg,
            "rating": rating,
            "num_contributions": len(scores),
            "targets": per_target_stats,
        }

    return {
        "overall": {
            "average_score": overall_avg,
            "rating": overall_rating,
            "num_contributions": len(valid),
        },
        "by_sdg": by_sdg,
    }
