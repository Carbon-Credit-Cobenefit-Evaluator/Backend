# modules/scoring.py

from typing import Dict, List, Any
import statistics


# -------------------------------------------------------------------
# NEW: Score function that returns BOTH (score, details)
# -------------------------------------------------------------------
def score_factor(assessment: Dict[str, Any]) -> tuple[int, Dict[str, float]]:
    """
    Returns:
        (score: int, details: { ... })
    """

    excluded_reason = assessment.get("excluded_reason")
    if excluded_reason:
        details = {
            "level_base": 0,
            "evidence_weight": 0.0,
            "durability_bonus": 0,
            "raw_score": 0.0,
            "score": 0,
        }
        return 0, details

    level = assessment.get("level_of_change", "")
    evid = assessment.get("evidence_quality", "")
    durability = bool(assessment.get("durability_measures", False))

    # ---------------- LEVEL ----------------
    level_map = {
        "predicted_only": 0,
        "output": 4,
        "outcome": 7,
        "impact": 9
    }
    level_base = level_map.get(level, 0)

    # ---------------- EVIDENCE QUALITY ----------------
    evidence_map = {
        "narrated": 0.6,
        "estimated": 0.8,
        "quantified": 1.0,
        "quantified_with_method": 1.2,
    }
    evidence_weight = evidence_map.get(evid, 0.6)

    # ---------------- DURABILITY ----------------
    durability_bonus = 2 if durability else 0

    raw = level_base * evidence_weight + durability_bonus

    # ---------------- FINAL SCORE ----------------
    if raw <= 0:
        score = 0
    else:
        score = int(round(raw))
        score = max(1, min(15, score))

    details = {
        "level_base": level_base,
        "evidence_weight": evidence_weight,
        "durability_bonus": durability_bonus,
        "raw_score": raw,
        "score": score,
    }

    return score, details


# -------------------------------------------------------------------
# Rating thresholds (unchanged)
# -------------------------------------------------------------------
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


# -------------------------------------------------------------------
# Aggregation logic (unchanged)
# -------------------------------------------------------------------
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

    sdg_groups = {}
    sdg_targets = {}

    for a in valid:
        goal = str(a["sdg_goal"])
        target = a.get("sdg_target")
        score = a["score"]

        sdg_groups.setdefault(goal, []).append(score)

        if target:
            sdg_targets.setdefault(goal, {}).setdefault(target, []).append(score)

    by_sdg = {}
    for goal, scores in sdg_groups.items():
        avg = statistics.mean(scores)
        rating = map_score_to_rating(avg)

        per_target = {}
        for t, tscores in sdg_targets.get(goal, {}).items():
            t_avg = statistics.mean(tscores)
            t_rating = map_score_to_rating(t_avg)
            per_target[t] = {
                "average_score": t_avg,
                "rating": t_rating,
                "num_contributions": len(tscores),
            }

        by_sdg[goal] = {
            "average_score": avg,
            "rating": rating,
            "num_contributions": len(scores),
            "targets": per_target,
        }

    return {
        "overall": {
            "average_score": overall_avg,
            "rating": overall_rating,
            "num_contributions": len(valid),
        },
        "by_sdg": by_sdg,
    }
