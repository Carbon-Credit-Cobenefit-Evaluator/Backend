# assessments/run_assessments.py

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from config.settings import logger
from modules.assessments.sdg1_assessor import assess_sdg1_for_project

# ✅ Keep registry INSIDE this file (no separate config file)
SDG_ASSESSMENT_REGISTRY: Dict[str, bool] = {
    "SDG_1_No_Poverty": True,
    # Later:
    # "SDG_2_Zero_Hunger": True,
    # "SDG_3_Good_Health": True,
}


def run_assessments_for_project(
    project_id: str,
    project_root: Path,
    registry: Dict[str, bool] | None = None,
) -> List[Path]:
    """
    Run all enabled SDG assessors for a project.
    Returns list of written score file paths.
    """
    registry = registry or SDG_ASSESSMENT_REGISTRY
    written: List[Path] = []

    for sdg_key, enabled in registry.items():
        if not enabled:
            continue

        try:
            if sdg_key == "SDG_1_No_Poverty":
                out = assess_sdg1_for_project(
                    project_id=project_id,
                    project_root=project_root,
                )
                written.append(out)
                logger.info(f"[ASSESS] Wrote {sdg_key} assessment: {out}")
            else:
                logger.warning(f"[ASSESS] No assessor implemented yet for {sdg_key} (skipping)")

        except Exception as e:
            logger.warning(f"[ASSESS] Assessment failed for {sdg_key} on project {project_id}: {e}")

    return written
