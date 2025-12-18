# assessments/sdg1_assessor.py

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any, List, Tuple


def _load_json(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _normalize_sentence(s: str) -> str:
    # stable dedupe key (lightweight)
    return " ".join((s or "").strip().lower().split())


def _invert_rules(sdg1_rules_block: Dict[str, Dict[str, str]]) -> Dict[str, str]:
    """
    Input:
      {
        "OUTPUT": {"O1": "...", ...},
        "OUTCOME": {"R1": "...", ...},
        "IMPACT": {"I1": "...", ...}
      }
    Return:
      {"O1":"OUTPUT","R1":"OUTCOME","I1":"IMPACT",...}
    """
    out: Dict[str, str] = {}
    for level, rules in sdg1_rules_block.items():
        for rule_code in rules.keys():
            out[rule_code] = level
    return out


def _filter_unique_rule_evidence(
    satisfied_rules: Dict[str, List[Dict[str, Any]]],
    rule_to_level: Dict[str, str],
    thresholds: Dict[str, float],
) -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, int], Dict[str, int]]:
    """
    Keep only evidence items that pass the level threshold, and dedupe per rule by sentence text.
    Returns:
      filtered_evidence_by_rule, counts_by_rule, counts_by_level
    """
    filtered: Dict[str, List[Dict[str, Any]]] = {}
    counts_by_rule: Dict[str, int] = {}
    counts_by_level: Dict[str, int] = {"OUTPUT": 0, "OUTCOME": 0, "IMPACT": 0}

    for rule, items in (satisfied_rules or {}).items():
        level = rule_to_level.get(rule)
        if level not in ("OUTPUT", "OUTCOME", "IMPACT"):
            # rule not part of SDG1 rule ontology -> ignore
            continue

        thr = float(thresholds.get(level, 0.0))

        seen_sent = set()
        kept: List[Dict[str, Any]] = []

        for it in items or []:
            sent = it.get("sentence", "")
            prob = float(it.get("probability", 0.0))

            if prob < thr:
                continue

            key = _normalize_sentence(sent)
            if not key or key in seen_sent:
                continue
            seen_sent.add(key)

            kept.append({"sentence": sent, "probability": round(prob, 4)})

        if kept:
            # sort best evidence first
            kept.sort(key=lambda x: x["probability"], reverse=True)
            filtered[rule] = kept
            counts_by_rule[rule] = len(kept)
            counts_by_level[level] += len(kept)

    return filtered, counts_by_rule, counts_by_level


def _weighted_sum(
    counts_by_rule: Dict[str, int],
    rule_weights: Dict[str, float],
) -> float:
    total = 0.0
    for rule, cnt in counts_by_rule.items():
        w = float(rule_weights.get(rule, 1.0))
        total += float(cnt) * w
    return total


def _cap_norm(x: float, cap: float) -> float:
    cap = float(cap)
    if cap <= 0:
        return 0.0
    return min(float(x), cap) / cap


def assess_sdg1_for_project(
    project_id: str,
    project_root: Path,
) -> Path:
    """
    Reads:
      data/outputs/{project_id}/SDG_evidence/SDG_1_No_Poverty_evidence.json
      config/SDG_rules.json
      config/scoring.json   (global config; uses SDG_1_No_Poverty block)

    Writes:
      data/outputs/{project_id}/SDG_assessment/SDG_1_No_Poverty_score.json

    Returns: output path
    """
    sdg_key = "SDG_1_No_Poverty"

    evidence_path = (
        project_root / "data" / "outputs" / project_id / "SDG_evidence" / f"{sdg_key}_evidence.json"
    )
    rules_path = project_root / "config" / "SDG_rules.json"
    scoring_path = project_root / "config" / "SDG_scoring.json"

    if not evidence_path.exists():
        raise FileNotFoundError(f"Missing evidence file: {evidence_path}")
    if not rules_path.exists():
        raise FileNotFoundError(f"Missing rules config: {rules_path}")
    if not scoring_path.exists():
        raise FileNotFoundError(f"Missing scoring config: {scoring_path}")

    evidence = _load_json(evidence_path)
    rules_cfg = _load_json(rules_path)
    scoring_all = _load_json(scoring_path)

    # ----------------------------
    # SDG-1 rules ontology (O/R/I)
    # ----------------------------
    sdg1_rules_block = rules_cfg.get("SDG1_RULES")
    if not isinstance(sdg1_rules_block, dict):
        raise KeyError('Expected "SDG1_RULES" object in config/SDG_rules.json')

    rule_to_level = _invert_rules(sdg1_rules_block)

    # ----------------------------
    # SDG-1 scoring config block
    # ----------------------------
    if sdg_key not in scoring_all:
        raise KeyError(f'{sdg_key} not found in config/SDG_scoring.json')

    scoring_cfg = scoring_all[sdg_key]

    thresholds = scoring_cfg.get("thresholds", {})
    rule_weights = scoring_cfg.get("rule_weights", {})
    caps = scoring_cfg.get("caps", {})
    level_mix = scoring_cfg.get("level_mix", {})
    gates_cfg = scoring_cfg.get("gates", {})
    top_n = int(scoring_cfg.get("top_evidence_per_rule", 3))

    satisfied_rules = evidence.get("satisfied_rules", {}) or {}

    # Step 1: filter + unique evidence per rule using level thresholds
    filtered_evidence, counts_by_rule, counts_by_level = _filter_unique_rule_evidence(
        satisfied_rules=satisfied_rules,
        rule_to_level=rule_to_level,
        thresholds=thresholds,
    )

    # Split rule counts by level
    counts_O = {r: c for r, c in counts_by_rule.items() if rule_to_level.get(r) == "OUTPUT"}
    counts_R = {r: c for r, c in counts_by_rule.items() if rule_to_level.get(r) == "OUTCOME"}
    counts_I = {r: c for r, c in counts_by_rule.items() if rule_to_level.get(r) == "IMPACT"}

    # Step 2: weighted raw sums per level
    raw_O = _weighted_sum(counts_O, rule_weights)
    raw_R = _weighted_sum(counts_R, rule_weights)
    raw_I = _weighted_sum(counts_I, rule_weights)

    # Step 3: causal gates
    penalties: List[str] = []

    core_outputs = set(gates_cfg.get("core_outputs", ["O2", "O3", "O5"]))
    core_output_count = sum(counts_by_rule.get(r, 0) for r in core_outputs)

    outcome_weight = 1.0
    if counts_by_level.get("OUTCOME", 0) > 0 and core_output_count == 0:
        outcome_weight = float(gates_cfg.get("outcome_penalty_if_no_core_outputs", 0.5))
        penalties.append("Outcome downweighted: outcomes present but core outputs missing")

    impact_weight = 1.0
    min_outcomes_for_impact = int(gates_cfg.get("min_outcome_for_impact", 3))
    if counts_by_level.get("IMPACT", 0) > 0 and counts_by_level.get("OUTCOME", 0) < min_outcomes_for_impact:
        impact_weight = float(gates_cfg.get("impact_penalty_if_low_outcomes", 0.4))
        penalties.append(f"Impact downweighted: outcomes < {min_outcomes_for_impact}")

    gated_R = raw_R * outcome_weight
    gated_I = raw_I * impact_weight

    # Step 4: cap normalization per level
    cap_O = float(caps.get("OUTPUT", 30.0))
    cap_R = float(caps.get("OUTCOME", 25.0))
    cap_I = float(caps.get("IMPACT", 10.0))

    norm_O = _cap_norm(raw_O, cap_O)
    norm_R = _cap_norm(gated_R, cap_R)
    norm_I = _cap_norm(gated_I, cap_I)

    # Step 5: final mix (0..1) then to 0..100
    mix_O = float(level_mix.get("OUTPUT", 0.30))
    mix_R = float(level_mix.get("OUTCOME", 0.40))
    mix_I = float(level_mix.get("IMPACT", 0.30))

    final_0_1 = (norm_O * mix_O) + (norm_R * mix_R) + (norm_I * mix_I)
    final_0_100 = round(final_0_1 * 100.0, 2)

    # top evidence per rule (for auditability)
    top_evidence: Dict[str, List[Dict[str, Any]]] = {}
    for rule, items in filtered_evidence.items():
        top_evidence[rule] = items[:top_n]

    output_path = (
        project_root
        / "data"
        / "outputs"
        / project_id
        / "SDG_assessment"
        / f"{sdg_key}_score.json"
    )

    result = {
        "sdg": sdg_key,
        "project_id": str(project_id),
        "final_score_0_100": final_0_100,
        "final_score_0_1": round(final_0_1, 4),
        "components": {
            "output_raw": round(raw_O, 4),
            "outcome_raw": round(raw_R, 4),
            "impact_raw": round(raw_I, 4),
            "outcome_weight": round(outcome_weight, 3),
            "impact_weight": round(impact_weight, 3),
            "output_norm": round(norm_O, 4),
            "outcome_norm": round(norm_R, 4),
            "impact_norm": round(norm_I, 4),
            "mix": {"OUTPUT": mix_O, "OUTCOME": mix_R, "IMPACT": mix_I},
            "caps": {"OUTPUT": cap_O, "OUTCOME": cap_R, "IMPACT": cap_I},
        },
        "counts": {
            "by_level_unique_sentences": counts_by_level,
            "by_rule_unique_sentences": dict(sorted(counts_by_rule.items())),
            "core_output_unique_sentences": int(core_output_count),
        },
        "rules_present": {
            "OUTPUT": sorted(counts_O.keys()),
            "OUTCOME": sorted(counts_R.keys()),
            "IMPACT": sorted(counts_I.keys()),
        },
        "penalties": penalties,
        "top_evidence": top_evidence,
        "source_files": {
            "evidence": str(evidence_path),
            "rules_config": str(rules_path),
            "scoring_config": str(scoring_path),
        },
    }

    _write_json(output_path, result)
    return output_path


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Assess SDG-1 score for a project (SDG1 only).")
    parser.add_argument("--p", required=True, help="Project ID (folder inside data/outputs)")
    args = parser.parse_args()

    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    out = assess_sdg1_for_project(project_id=args.p, project_root=PROJECT_ROOT)
    print(f"[SUCCESS] SDG-1 assessment written: {out}")
