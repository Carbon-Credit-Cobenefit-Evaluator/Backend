# Scraping.py (inside data/)

import json
from urllib.parse import urlparse
from pathlib import Path
import httpx

API_BASE = "https://registry.verra.org/uiapi/resource/resourceSummary/"
PROJECTS_FILE = Path(__file__).resolve().parent / "projects.json"


def load_projects_file():
    if PROJECTS_FILE.exists():
        return json.loads(PROJECTS_FILE.read_text(encoding="utf-8"))
    return {"projects": []}


def save_projects_file(data):
    PROJECTS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def get_attr(attrs, code):
    for item in attrs or []:
        if item.get("code") == code:
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
    vcs = next((p for p in data.get("participationSummaries", []) if p.get("programCode") == "VCS"), None)
    ccb = next((p for p in data.get("participationSummaries", []) if p.get("programCode") == "CCB"), None)
    sdv = next((p for p in data.get("participationSummaries", []) if p.get("programCode") == "SDVISTA"), None)

    result = {
        "resourceIdentifier": data.get("resourceIdentifier"),
        "resourceName": data.get("resourceName"),
        "description": data.get("description"),
        "location": data.get("location"),

        # VCS values
        "vcs_project_status": get_attr(vcs.get("attributes") if vcs else None, "PROJECT_STATUS"),
        "estimated_annual_emission_reduction": get_attr(vcs.get("attributes") if vcs else None, "EST_ANNUAL_EMISSION_REDCT"),
        "total_buffer_pool_credits": get_attr(vcs.get("attributes") if vcs else None, "TOTAL_BUFFER_POOL_CREDITS"),
        "primary_project_category": get_attr(vcs.get("attributes") if vcs else None, "PRIMARY_PROJECT_CATEGORY_NAME"),
        "subcategory": get_attr(vcs.get("attributes") if vcs else None, "PROJECT_SUBCATERGORY_NAMES"),
        "project_acreage": get_attr(vcs.get("attributes") if vcs else None, "PROJECT_ACREAGE"),

        # Other standards project status
        "ccb_project_status": get_attr(ccb.get("attributes") if ccb else None, "PROJECT_STATUS"),
        "sdvista_project_status": get_attr(sdv.get("attributes") if sdv else None, "PROJECT_STATUS"),

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
                "uploadDate": d.get("uploadDate"),
            })

    result["documents"] = all_docs
    return result


# ✅ IMPORTANT: no execution on import
if __name__ == "__main__":
    print("Run runner.py. This module only provides functions.")
