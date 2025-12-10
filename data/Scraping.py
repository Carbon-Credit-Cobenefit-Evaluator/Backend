# data/Scraping.py

import asyncio
import json
from urllib.parse import urlparse
from pathlib import Path
import httpx


API_BASE = "https://registry.verra.org/uiapi/resource/resourceSummary/"
PROJECTS_FILE = Path(__file__).resolve().parent / "projects.json"


def load_projects_file():
    """Load or initialize projects.json structure."""
    if PROJECTS_FILE.exists():
        with PROJECTS_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    else:
        return {"projects": []}


def save_projects_file(data):
    """Save updated JSON back to projects.json."""
    with PROJECTS_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# Extract specific attribute value from participation attributes
def get_attr(attrs, code):
    for item in attrs:
        if item["code"] == code:
            vals = item.get("values", [])
            if vals:
                return vals[0].get("value")
    return None


async def fetch_verra_json(app_url: str) -> dict:
    parsed = urlparse(app_url)
    parts = [p for p in parsed.path.split("/") if p]
    project_id = parts[-1]

    api_url = f"{API_BASE}{project_id}"
    print(f"🔗 Calling API URL: {api_url}")

    headers = {
        "Accept": "application/json",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/123.0.0.0 Safari/537.36"
        ),
    }

    async with httpx.AsyncClient(timeout=30, headers=headers) as client:
        resp = await client.get(api_url)
        print("HTTP status:", resp.status_code)
        resp.raise_for_status()
        return resp.json()


def rearrange(data: dict) -> dict:
    """Return cleaned and reorganized structure."""

    vcs = next((p for p in data["participationSummaries"] if p["programCode"] == "VCS"), None)
    ccb = next((p for p in data["participationSummaries"] if p["programCode"] == "CCB"), None)
    sdv = next((p for p in data["participationSummaries"] if p["programCode"] == "SDVISTA"), None)

    result = {
        "resourceIdentifier": data.get("resourceIdentifier"),
        "resourceName": data.get("resourceName"),
        "description": data.get("description"),
        "location": data.get("location"),

        # VCS values
        "vcs_project_status": get_attr(vcs["attributes"], "PROJECT_STATUS") if vcs else None,
        "estimated_annual_emission_reduction": get_attr(vcs["attributes"], "EST_ANNUAL_EMISSION_REDCT") if vcs else None,
        "total_buffer_pool_credits": get_attr(vcs["attributes"], "TOTAL_BUFFER_POOL_CREDITS") if vcs else None,
        "primary_project_category": get_attr(vcs["attributes"], "PRIMARY_PROJECT_CATEGORY_NAME") if vcs else None,
        "subcategory": get_attr(vcs["attributes"], "PROJECT_SUBCATERGORY_NAMES") if vcs else None,
        "project_acreage": get_attr(vcs["attributes"], "PROJECT_ACREAGE") if vcs else None,

        # Other standards project status
        "ccb_project_status": get_attr(ccb["attributes"], "PROJECT_STATUS") if ccb else None,
        "sdvista_project_status": get_attr(sdv["attributes"], "PROJECT_STATUS") if sdv else None,

        # documents
        "documents": [],
    }

    all_docs = []
    for group in data.get("documentGroups", []):
        for d in group.get("documents", []):
            all_docs.append({
                "uri": d.get("uri"),
                "documentType": d.get("documentType"),
                "documentName": d.get("documentName"),
                "uploadDate": d.get("uploadDate")
            })

    result["documents"] = all_docs
    return result


# -----------------------------
# DIRECT EXECUTION
# -----------------------------
project_url = "https://registry.verra.org/app/projectDetail/VCS/1566"

print(f"Fetching: {project_url}")
raw_json = asyncio.run(fetch_verra_json(project_url))

print("\n⚙️ Rearranging JSON...")
cleaned = rearrange(raw_json)

resource_id = cleaned["resourceIdentifier"]
key_name = f"VCS_{resource_id}"

print(f"\n🔧 Appending into projects.json as key: {key_name}")

# Load existing list
projects_file_data = load_projects_file()

# Append new object
projects_file_data["projects"].append({key_name: cleaned})

# Save back
save_projects_file(projects_file_data)

print("\n✅ Saved into projects.json")
print("\n--- Final appended object ---")
print(json.dumps({key_name: cleaned}, indent=2, ensure_ascii=False))
