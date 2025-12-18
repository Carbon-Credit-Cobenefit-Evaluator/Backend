# FilterDocs.py (inside data/)

import re
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Tuple


BASE_DIR = Path(__file__).resolve().parent
PROJECTDOCS_PATH = BASE_DIR / "projectdocs.json"


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def doc_text(doc: dict) -> str:
    return _norm(f"{doc.get('documentType', '')} {doc.get('documentName', '')}")


def parse_upload_date(doc: dict) -> Optional[datetime]:
    ts_raw = (doc.get("uploadDate") or "").strip()
    if not ts_raw:
        return None
    ts_raw = ts_raw.replace("Z", "")
    try:
        return datetime.fromisoformat(ts_raw)
    except ValueError:
        return None


# Markers
CCB_MARK = re.compile(r"\bccb\b", re.I)
SDV_MARK = re.compile(r"\bsd\s*vista\b|\bsdvista\b", re.I)

# Type/name patterns
PD_PAT = re.compile(r"\b(project\s*description|proj[_\s-]*desc|projectdescription|pdd|\bvcs\s*pd\b|\bpd\b)\b", re.I)
MR_PAT = re.compile(r"\b(monitoring\s*report|monit[_\s-]*rep|\bvcs\s*mr\b|\bmr\b)\b", re.I)
VR_PAT = re.compile(r"\b(verification\s*report|verif[_\s-]*rep|\bvcs\s*vr\b|\bverr\b|\bvr\b)\b", re.I)

NPRR_PAT = re.compile(r"\b(non[-\s]*permanence|nprr|non[_\s-]*perm|afolu[_\s-]*risk|risk[_\s-]*elem)\b", re.I)
PRR_PAT = re.compile(r"\b(prr|project\s*review\s*report|issuance|issuance[-\s]*representation|representation)\b", re.I)


def classify(doc: dict) -> Optional[str]:
    text = doc_text(doc)
    is_ccb = bool(CCB_MARK.search(text)) or text.startswith("ccb")
    is_sdv = bool(SDV_MARK.search(text))

    if PD_PAT.search(text):
        if is_sdv: return "sdv_project_description"
        if is_ccb: return "ccb_project_description"
        return "project_description"

    if MR_PAT.search(text):
        if is_sdv: return "sdv_monitoring_report"
        if is_ccb: return "ccb_monitoring_report"
        return "monitoring_report"

    if VR_PAT.search(text):
        if is_sdv: return "sdv_verification_report"
        if is_ccb: return "ccb_verification_report"
        return "verification_report"

    if NPRR_PAT.search(text):
        if is_ccb: return "ccb_nprr"
        if is_sdv: return "sdv_nprr"
        return "nprr"

    if PRR_PAT.search(text):
        if is_ccb: return "ccb_prr"
        if is_sdv: return "sdv_prr"
        return "prr"

    return None


CATEGORY_WEIGHT = {
    # Highest (SDG co-benefit dense)
    "ccb_monitoring_report": 100,
    "ccb_project_description": 95,
    "ccb_verification_report": 80,

    "sdv_project_description": 95,
    "sdv_monitoring_report": 100,
    "sdv_verification_report": 85,
    "sdv_prr": 60,

    # High
    "monitoring_report": 85,
    "project_description": 75,

    # Medium
    "verification_report": 55,

    # Optional / lower
    "nprr": 30,
    "sdv_nprr": 32,
    "ccb_nprr": 35,
    "prr": 25,
    "sdv_prr": 28,
    "ccb_prr": 30,
}


def family(category: str) -> str:
    if "monitoring" in category: return "MR"
    if "project_description" in category: return "PD"
    if "verification" in category: return "VR"
    if "nprr" in category: return "NPRR"
    if "prr" in category: return "PRR"
    return "OTHER"


def select_prioritized_docs(docs: list, max_docs: int = 10) -> List[dict]:
    # 1) keep latest per category
    latest_by_cat = {}

    for doc in docs:
        cat = classify(doc)
        if not cat:
            continue

        ts = parse_upload_date(doc)
        if not ts:
            continue

        if cat not in latest_by_cat or ts > latest_by_cat[cat][0]:
            latest_by_cat[cat] = (ts, doc)

    # 2) rank by weight then recency
    pool: List[Tuple[int, datetime, str, dict]] = []
    for cat, (ts, doc) in latest_by_cat.items():
        w = CATEGORY_WEIGHT.get(cat, 0)
        pool.append((w, ts, cat, doc))

    pool.sort(key=lambda x: (x[0], x[1]), reverse=True)

    # 3) cap to max_docs with diversity
    selected = []
    fam_count = {}
    MAX_PER_FAMILY = 4

    for w, ts, cat, doc in pool:
        fam = family(cat)
        if fam_count.get(fam, 0) >= MAX_PER_FAMILY:
            continue
        selected.append(doc)
        fam_count[fam] = fam_count.get(fam, 0) + 1
        if len(selected) >= max_docs:
            break

    return selected


def save_to_projectdocs(project_key: str, docs: list):
    if PROJECTDOCS_PATH.exists():
        data = json.loads(PROJECTDOCS_PATH.read_text(encoding="utf-8"))
    else:
        data = {"projectdocs": []}

    proj_list = data.get("projectdocs", [])
    proj_list = [obj for obj in proj_list if project_key not in obj]
    proj_list.append({project_key: docs})
    data["projectdocs"] = proj_list

    PROJECTDOCS_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"✅ Saved {len(docs)} prioritized docs under '{project_key}' → {PROJECTDOCS_PATH.name}")


if __name__ == "__main__":
    print("Run runner.py. This module only provides functions.")
