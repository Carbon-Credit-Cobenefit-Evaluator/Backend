# filterdocs.py

import re
import json
from datetime import datetime
from pathlib import Path


# -------------------------------------------------------------
# 0. BASE DIR (so it works no matter where you run from)
# -------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
PROJECTS_PATH = BASE_DIR / "projects.json"
PROJECTDOCS_PATH = BASE_DIR / "projectdocs.json"


# -------------------------------------------------------------
# 1. REGEX PATTERNS FOR TIER-1 DOCUMENTS
# -------------------------------------------------------------
TIER1_PATTERNS = {
    "project_description": re.compile(r"project\s*description", re.I),
    "monitoring_report": re.compile(r"monitor(ing)?\s*report", re.I),
    "verification_report": re.compile(r"verif(ication)?\s*report", re.I),

    "ccb_project_description": re.compile(r"ccb.*project\s*description", re.I),
    "ccb_monitoring_report": re.compile(r"ccb.*monitor(ing)?\s*report", re.I),
    "ccb_verification_report": re.compile(r"ccb.*verif(ication)?\s*report", re.I),

    "sdv_project_description": re.compile(r"sd\s*vista.*project\s*description", re.I),
    "sdv_monitoring_report": re.compile(r"sd\s*vista.*monitor(ing)?\s*report", re.I),
}


def is_tier1_doc(doc_type: str) -> bool:
    """Return True if document type is Tier-1."""
    for regex in TIER1_PATTERNS.values():
        if regex.search(doc_type):
            return True
    return False


# -------------------------------------------------------------
# 2. GROUP KEY FOR DOCUMENT TYPE
# -------------------------------------------------------------
def group_key(doc_type: str) -> str | None:
    """Normalize documentType into a category key."""
    dt = doc_type.lower().strip()

    # SD VISta-specific first (so they don't get picked by generic ones)
    if "sd vista" in dt or "sdvista" in dt.replace(" ", ""):
        if "monitor" in dt:
            return "sdv_monitoring_report"
        if "project description" in dt:
            return "sdv_project_description"

    # CCB-specific next
    if dt.startswith("ccb"):
        if "monitor" in dt:
            return "ccb_monitoring_report"
        if "verif" in dt:
            return "ccb_verification_report"
        if "project description" in dt:
            return "ccb_project_description"

    # General VCS
    if "monitor" in dt:
        return "monitoring_report"
    if "verification report" in dt or "verification" in dt:
        return "verification_report"
    if "project description" in dt:
        return "project_description"

    return None


# -------------------------------------------------------------
# 3. FILTER + SELECT LATEST VERSION
# -------------------------------------------------------------
def filter_latest_tier1_docs(docs):
    """Return only Tier-1 docs, and only the latest version of each group."""
    grouped = {}

    for doc in docs:
        dtype = doc.get("documentType", "")

        if not is_tier1_doc(dtype):
            continue

        key = group_key(dtype)
        if not key:
            continue

        # Parse upload timestamp (strip trailing Z)
        ts_raw = doc.get("uploadDate", "")
        try:
            ts = datetime.fromisoformat(ts_raw.replace("Z", ""))
        except ValueError:
            # If parsing fails, skip this doc
            print(f"⚠️ Could not parse date '{ts_raw}' for doc {doc.get('documentName')}")
            continue

        # Keep only latest per type
        if key not in grouped or ts > grouped[key]["ts"]:
            grouped[key] = {"ts": ts, "doc": doc}

    return [entry["doc"] for entry in grouped.values()]


# -------------------------------------------------------------
# 4. SAVE INTO projectdocs.json (inside "projectdocs" array)
# -------------------------------------------------------------
def save_to_projectdocs(project_key: str, docs: list):
    """
    Maintain structure:
    {
      "projectdocs": [
        { "VCS_1566": [ ...docs... ] },
        { "VCS_9999": [ ... ] }
      ]
    }
    """
    if PROJECTDOCS_PATH.exists():
        data = json.loads(PROJECTDOCS_PATH.read_text(encoding="utf-8"))
    else:
        data = {"projectdocs": []}

    proj_list = data.get("projectdocs", [])

    # Remove any existing entry with the same key (to overwrite cleanly)
    proj_list = [obj for obj in proj_list if project_key not in obj]

    # Append new entry
    proj_list.append({project_key: docs})

    data["projectdocs"] = proj_list

    PROJECTDOCS_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"✅ Saved {len(docs)} filtered docs under '{project_key}' → {PROJECTDOCS_PATH.name}")


# -------------------------------------------------------------
# 5. MAIN EXECUTION
# -------------------------------------------------------------
def main():
    if not PROJECTS_PATH.exists():
        print(f"❌ ERROR: {PROJECTS_PATH.name} not found in {BASE_DIR}")
        return

    # Load data
    data = json.loads(PROJECTS_PATH.read_text(encoding="utf-8"))

    # Example: {"projects": [ { "VCS_1566": { ... } } ]}
    proj_obj = data["projects"][0]
    project_key = list(proj_obj.keys())[0]

    print(f"🔍 Processing project: {project_key}")

    docs = proj_obj[project_key].get("documents", [])

    # Apply filtering logic
    filtered_docs = filter_latest_tier1_docs(docs)

    # Print results
    print("\n📌 Selected Tier-1 latest docs:")
    for d in filtered_docs:
        print(f" - {d['documentType']} → {d['documentName']} (uploaded {d['uploadDate']})")

    # Save to projectdocs.json
    save_to_projectdocs(project_key, filtered_docs)


if __name__ == "__main__":
    main()
