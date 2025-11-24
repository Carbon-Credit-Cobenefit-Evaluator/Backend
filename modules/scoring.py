# modules/scoring.py

from typing import Dict, List, Any
import statistics


# ---------------------------------------------------------------------
# FULL BREAKDOWN SCORING (used by assessment.py)
# ---------------------------------------------------------------------
def score_factor_with_details(assessment: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transparent scoring function.
    Returns:
      {
        "score": int,
        "level_base": int,
        "evidence_weight": float,
        "durability_bonus": int,
        "raw_score": float,
        "excluded_by_reason": str | None
      }
    """

    excluded_reason = assessment.get("excluded_reason")
    if excluded_reason:
        return {
            "score": 0,
            "level_base": 0,
            "evidence_weight": 0.0,
            "durability_bonus": 0,
            "raw_score": 0.0,
            "excluded_by_reason": excluded_reason,
        }

    # ---------------------- Level of Change ----------------------
    level = assessment.get("level_of_change", "")
    level_map = {
        "predicted_only": 0,
        "output": 4,
        "outcome": 7,
        "impact": 9,
    }
    level_base = level_map.get(level, 0)

    # ---------------------- Evidence Quality ----------------------
    evid = assessment.get("evidence_quality", "")
    evidence_map = {
        "narrated": 0.6,
        "estimated": 0.8,
        "quantified": 1.0,
        "quantified_with_method": 1.2,
    }
    evidence_weight = evidence_map.get(evid, 0.6)

    # ------------------------- Durability -------------------------
    durability = bool(assessment.get("durability_measures", False))
    durability_bonus = 2 if durability else 0

    # ------------------------- Raw score --------------------------
    raw_score = level_base * evidence_weight + durability_bonus

    # ---------------------- Final 1–15 score ----------------------
    if raw_score <= 0:
        final_score = 0
    else:
        final_score = int(round(raw_score))
        final_score = max(1, min(15, final_score))

    return {
        "score": final_score,
        "level_base": level_base,
        "evidence_weight": evidence_weight,
        "durability_bonus": durability_bonus,
        "raw_score": raw_score,
        "excluded_by_reason": None,
    }


# ---------------------------------------------------------------------
# BACKWARD COMPATIBLE ENTRYPOINT
#   assessment.py currently calls: score, details = score_factor(assessment)
# ---------------------------------------------------------------------
def score_factor(assessment: Dict[str, Any]) -> tuple[int, Dict[str, Any]]:
    details = score_factor_with_details(assessment)
    return details["score"], details


# ---------------------------------------------------------------------
# MAP SCORE TO SDG 1+…5+ RATING
# ---------------------------------------------------------------------
def map_score_to_rating(avg_score: float) -> str:
    if avg_score >= 12:
        return "5+"
    if avg_score >= 9:
        return "4+"
    if avg_score >= 6:
        return "3+"
    if avg_score >= 3:
        return "2+"
    return "1+"


# ---------------------------------------------------------------------
# AGGREGATION OF ALL FACTOR SCORES
# ---------------------------------------------------------------------
def aggregate_by_sdg(assessments: List[Dict[str, Any]]) -> Dict[str, Any]:

    valid = [a for a in assessments if a.get("score", 0) > 0]

    if not valid:
        return {
            "overall": {
                "average_score": 0.0,
                "rating": "1+",
                "num_contributions": 0,
            },
            "by_sdg": {},
        }

    overall_scores = [a["score"] for a in valid]
    overall_avg = statistics.mean(overall_scores)
    overall_rating = map_score_to_rating(overall_avg)

    sdg_groups: Dict[str, List[int]] = {}
    sdg_targets: Dict[str, Dict[str, List[int]]] = {}

    # Group by SDG goal and SDG targets
    for a in valid:
        goal = str(a["sdg_goal"])
        target = a.get("sdg_target")
        score = a["score"]

        sdg_groups.setdefault(goal, []).append(score)

        if target:
            sdg_targets.setdefault(goal, {}).setdefault(target, []).append(score)

    # Build output structure
    by_sdg = {}
    for goal, scores in sdg_groups.items():
        avg = statistics.mean(scores)
        rating = map_score_to_rating(avg)

        target_stats = {}
        for t, tscores in sdg_targets.get(goal, {}).items():
            t_avg = statistics.mean(tscores)
            t_rating = map_score_to_rating(t_avg)
            target_stats[t] = {
                "average_score": t_avg,
                "rating": t_rating,
                "num_contributions": len(tscores),
            }

        by_sdg[goal] = {
            "average_score": avg,
            "rating": rating,
            "num_contributions": len(scores),
            "targets": target_stats,
        }

    return {
        "overall": {
            "average_score": overall_avg,
            "rating": overall_rating,
            "num_contributions": len(valid),
        },
        "by_sdg": by_sdg,
    }
