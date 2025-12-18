# filterdocs.py (Gold Standard)  ✅ prioritize SDG co-benefit dense + latest + max 10

import asyncio
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from typing import Optional, Dict, Any, List, Tuple

import httpx


# -------------------------------------------------------------
# PATHS
# -------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
PROJECTS_PATH = BASE_DIR / "projects.json"
PROJECTDOCS_PATH = BASE_DIR / "projectdocs.json"


# -------------------------------------------------------------
# LOAD PROJECTS + FIND ONE PROJECT
# -------------------------------------------------------------
def load_projects_file() -> dict:
    if PROJECTS_PATH.exists():
        return json.loads(PROJECTS_PATH.read_text(encoding="utf-8"))
    return {"projects": []}


def find_project(projects_data: dict, project_key: str) -> Optional[dict]:
    """
    projects.json structure:
    {
      "projects": [
        { "GS_1795": { ... } },
        { "GS_1234": { ... } }
      ]
    }
    """
    for obj in projects_data.get("projects", []):
        if project_key in obj:
            return obj[project_key]
    return None


# -------------------------------------------------------------
# sustaincert_url -> SustainCERT API URL
# -------------------------------------------------------------
def to_sustaincert_api_url(sustaincert_url: str) -> str:
    """
    UI:  https://assurance-platform.goldstandard.org/project-documents/GS2913
    API: https://assurance-platform.goldstandard.org/api/public/project-documents/GS2913
    """
    if not sustaincert_url:
        raise ValueError("Empty sustaincert_url")

    if "/api/public/" in sustaincert_url:
        return sustaincert_url

    parsed = urlparse(sustaincert_url)
    parts = [p for p in parsed.path.split("/") if p]
    if not parts:
        raise ValueError(f"Invalid sustaincert_url path: {sustaincert_url}")

    gsid = parts[-1]  # GS2913
    return f"{parsed.scheme}://{parsed.netloc}/api/public/project-documents/{gsid}"


# -------------------------------------------------------------
# FETCH SustainCERT JSON
# -------------------------------------------------------------
async def fetch_sustaincert_json(sustaincert_url: str) -> dict:
    api_url = to_sustaincert_api_url(sustaincert_url)

    print("🔗 Fetching SustainCERT docs JSON:")
    print(f"    UI : {sustaincert_url}")
    print(f"    API: {api_url}")

    headers = {
        "accept": "application/json",
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/143.0.0.0 Safari/537.36 Edg/143.0.0.0"
        ),
        "referer": sustaincert_url,
        # ok to keep (matches what your browser shows)
        "x-gold-standard-api-version": "2023-04-19",
    }

    async with httpx.AsyncClient(timeout=30, headers=headers, follow_redirects=True) as client:
        resp = await client.get(api_url)
        print("HTTP status:", resp.status_code)
        resp.raise_for_status()
        return resp.json()


# -------------------------------------------------------------
# FLATTEN requests[].documents[] INTO ONE ARRAY
# -------------------------------------------------------------
def flatten_documents(gs_docs_json: Dict[str, Any]) -> List[Dict[str, Any]]:
    flat: List[Dict[str, Any]] = []

    for req in gs_docs_json.get("requests", []) or []:
        req_id = req.get("id")
        req_name = req.get("name")
        req_type = req.get("requestType")
        req_index = req.get("index")

        for doc in req.get("documents", []) or []:
            flat.append(
                {
                    # request context
                    "requestId": req_id,
                    "requestName": req_name,
                    "requestType": req_type,
                    "requestIndex": req_index,

                    # document fields
                    "id": doc.get("id"),
                    "filename": doc.get("filename"),
                    "uploadedTimestamp": doc.get("uploadedTimestamp"),
                    "modifiedTimestamp": doc.get("modifiedTimestamp"),
                    "displayCategoryType": doc.get("displayCategoryType"),

                    # raw fields (optional)
                    "access": doc.get("access"),
                    "category": doc.get("category"),
                    "type": doc.get("type"),
                    "isLatest": doc.get("isLatest"),
                }
            )

    return flat


# -------------------------------------------------------------
# TIME PARSING (latest rule)
# -------------------------------------------------------------
def parse_ts(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    t = ts.strip().replace("Z", "")
    try:
        return datetime.fromisoformat(t)
    except ValueError:
        return None


def best_doc_ts(doc: dict) -> Optional[datetime]:
    # prefer modifiedTimestamp, fallback uploadedTimestamp
    return parse_ts(doc.get("modifiedTimestamp")) or parse_ts(doc.get("uploadedTimestamp"))


# -------------------------------------------------------------
# CLASSIFY BY FILENAME/REQUEST TYPE (density rule)
# -------------------------------------------------------------
def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


# strong filename signals you showed (MR / annual / perf cert / verification / validation / PDD)
MR_PAT = re.compile(r"\b(monitoring[-\s]*report|monitoring report|_mr\b| mr\b)\b", re.I)
ANNUAL_PAT = re.compile(r"\b(annual[-\s]*report|project[-\s]*annual[-\s]*report)\b", re.I)
PERFCERT_PAT = re.compile(r"\b(perf(cert)?|performance[-\s]*cert|performance[-\s]*certification)\b", re.I)

PDD_PAT = re.compile(r"\b(pdd|project[-\s]*design[-\s]*document|project[-\s]*description)\b", re.I)
VERIF_PAT = re.compile(r"\b(verification[-\s]*report|verif(ication)? report|fverr|ver report)\b", re.I)
VALID_PAT = re.compile(r"\b(validation[-\s]*report|fval)\b", re.I)

SMP_PAT = re.compile(r"\b(sustainability[-\s]*monitoring[-\s]*plan|monitoring[-\s]*plan)\b", re.I)
LSC_PAT = re.compile(r"\b(local[-\s]*stakeholder[-\s]*consultation|stakeholder consultation)\b", re.I)

ZIP_PAT = re.compile(r"\.zip$", re.I)
DOCX_PAT = re.compile(r"\.docx?$", re.I)


def classify(doc: dict) -> Optional[str]:
    """
    Return a category key.
    We look at filename + requestType + displayCategoryType (but mostly filename).
    """
    filename = _norm(doc.get("filename", ""))
    req_type = _norm(doc.get("requestType", ""))
    disp = _norm(doc.get("displayCategoryType", ""))

    text = f"{filename} {req_type} {disp}"

    # drop non-pdf bundles from top priority (still allowed but low)
    if ZIP_PAT.search(filename):
        return "zip_bundle"
    if DOCX_PAT.search(filename):
        return "docx"

    # Most SDG co-benefit dense (GS style)
    # Performance certification monitoring reports + annual reports are usually richest.
    if PERFCERT_PAT.search(text) and MR_PAT.search(text):
        return "perfcert_monitoring_report"

    if MR_PAT.search(text):
        return "monitoring_report"

    if ANNUAL_PAT.search(text):
        return "annual_report"

    # Project design / description
    if PDD_PAT.search(text):
        return "pdd"

    # Validation / verification
    if VERIF_PAT.search(text):
        return "verification_report"

    if VALID_PAT.search(text):
        return "validation_report"

    # Supporting but often lower SDG density
    if SMP_PAT.search(text):
        return "sustainability_monitoring_plan"

    if LSC_PAT.search(text):
        return "stakeholder_consultation"

    # Certificates / “certification report” can still have SD sections sometimes
    if "certification report" in text or "certification" in text:
        return "certification_report"

    return None


# -------------------------------------------------------------
# PRIORITY WEIGHTS (density rule) + latest tie-break
# -------------------------------------------------------------
CATEGORY_WEIGHT = {
    # Highest expected SDG co-benefit density
    "perfcert_monitoring_report": 100,
    "monitoring_report": 95,
    "annual_report": 92,

    # High
    "pdd": 80,

    # Medium
    "verification_report": 65,
    "validation_report": 60,

    # Lower / supporting
    "certification_report": 45,
    "sustainability_monitoring_plan": 35,
    "stakeholder_consultation": 30,

    # usually not useful for SDG evidence extraction
    "zip_bundle": 10,
    "docx": 5,
}


def family(category: str) -> str:
    # diversity buckets (avoid picking 10 monitoring reports only)
    if "monitoring_report" in category:
        return "MR"
    if "annual_report" in category:
        return "AR"
    if category == "pdd":
        return "PDD"
    if "verification" in category:
        return "VR"
    if "validation" in category:
        return "VAL"
    return "OTHER"


# -------------------------------------------------------------
# SELECT: latest per category -> rank -> cap 10 with diversity
# -------------------------------------------------------------
def select_prioritized_docs(docs: List[dict], max_docs: int = 10) -> List[dict]:
    """
    Rules:
    1) prioritize by category SDG-density weight
    2) must be latest (keep latest per category)
    3) max 10 docs, with small diversity rule
    """
    latest_by_cat: Dict[str, Tuple[datetime, dict]] = {}

    for doc in docs:
        cat = classify(doc)
        if not cat:
            continue

        ts = best_doc_ts(doc)
        if not ts:
            continue

        if cat not in latest_by_cat or ts > latest_by_cat[cat][0]:
            latest_by_cat[cat] = (ts, doc)

    pool: List[Tuple[int, datetime, str, dict]] = []
    for cat, (ts, doc) in latest_by_cat.items():
        w = CATEGORY_WEIGHT.get(cat, 0)
        pool.append((w, ts, cat, doc))

    # rank: weight desc, then timestamp desc
    pool.sort(key=lambda x: (x[0], x[1]), reverse=True)

    selected: List[dict] = []
    fam_count: Dict[str, int] = {}
    MAX_PER_FAMILY = 4  # tweak if needed

    for w, ts, cat, doc in pool:
        fam = family(cat)
        if fam_count.get(fam, 0) >= MAX_PER_FAMILY:
            continue

        selected.append(doc)
        fam_count[fam] = fam_count.get(fam, 0) + 1

        if len(selected) >= max_docs:
            break

    return selected


# -------------------------------------------------------------
# SAVE TO projectdocs.json
# -------------------------------------------------------------
def save_to_projectdocs(project_key: str, docs: List[Dict[str, Any]]) -> None:
    """
    projectdocs.json structure:
    {
      "projectdocs": [
        { "GS_1795": [ ...docs... ] },
        { "GS_1234": [ ... ] }
      ]
    }
    """
    if PROJECTDOCS_PATH.exists():
        data = json.loads(PROJECTDOCS_PATH.read_text(encoding="utf-8"))
    else:
        data = {"projectdocs": []}

    proj_list = data.get("projectdocs", [])

    # overwrite cleanly
    proj_list = [obj for obj in proj_list if project_key not in obj]
    proj_list.append({project_key: docs})

    data["projectdocs"] = proj_list
    PROJECTDOCS_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"✅ Saved {len(docs)} prioritized docs under '{project_key}' → {PROJECTDOCS_PATH.name}")


# -------------------------------------------------------------
# MAIN
# -------------------------------------------------------------
async def main(project_key: str, max_docs: int = 10):
    if not PROJECTS_PATH.exists():
        print(f"❌ projects.json not found at: {PROJECTS_PATH}")
        return

    projects_data = load_projects_file()
    project = find_project(projects_data, project_key)

    if not project:
        print(f"❌ Project key not found in projects.json: {project_key}")
        return

    sustaincert_url = project.get("sustaincert_url")
    if not sustaincert_url:
        print(f"❌ sustaincert_url missing for {project_key}")
        return

    gs_docs_json = await fetch_sustaincert_json(sustaincert_url)
    flat_docs = flatten_documents(gs_docs_json)

    print(f"\n📄 Total docs found (flattened): {len(flat_docs)}")

    selected = select_prioritized_docs(flat_docs, max_docs=max_docs)

    print(f"\n🏆 Selected docs (max {max_docs}) — prioritized for SDG co-benefit density + latest:")
    for d in selected:
        ts = d.get("modifiedTimestamp") or d.get("uploadedTimestamp")
        cat = classify(d) or "unknown"
        print(f" - [{cat}] {d.get('filename')}  (ts={ts})")

    save_to_projectdocs(project_key, selected)


async def run_filter_for_project(project_key: str, max_docs: int = 10):
    await main(project_key, max_docs=max_docs)

