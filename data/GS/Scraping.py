import asyncio
import json
from urllib.parse import urlparse
from pathlib import Path
import httpx


# -------------------------------------------------------------
# CONFIG
# -------------------------------------------------------------
GS_API_BASE = "https://public-api.goldstandard.org/projects"
BASE_DIR = Path(__file__).resolve().parent
PROJECTS_FILE = BASE_DIR / "projects.json"


# -------------------------------------------------------------
# FILE HELPERS (same pattern as Verra)
# -------------------------------------------------------------
def load_projects_file():
    if PROJECTS_FILE.exists():
        return json.loads(PROJECTS_FILE.read_text(encoding="utf-8"))
    return {"projects": []}


def save_projects_file(data):
    PROJECTS_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


# -------------------------------------------------------------
# URL + CLEANING
# -------------------------------------------------------------
def extract_project_id(details_url: str) -> str:
    """
    https://registry.goldstandard.org/projects/details/1795
    -> 1795
    """
    parsed = urlparse(details_url)
    parts = [p for p in parsed.path.split("/") if p]
    if not parts:
        raise ValueError(f"Invalid Gold Standard URL: {details_url}")
    return parts[-1]


def clean_gold_standard_json(data: dict) -> dict:
    """
    1) Remove noisy / unneeded keys
    2) Flatten SDGs to list[str]
    """
    cleaned = dict(data)

    # Remove unwanted keys
    for key in [
        "gsf_standards_version",
        "carbon_stream",
        "programme_of_activities",
    ]:
        cleaned.pop(key, None)

    # Flatten SDGs
    sdgs = cleaned.get("sustainable_development_goals", [])
    if isinstance(sdgs, list):
        cleaned["sustainable_development_goals"] = [
            item.get("name")
            for item in sdgs
            if isinstance(item, dict) and item.get("name")
        ]

    return cleaned


# -------------------------------------------------------------
# FETCH
# -------------------------------------------------------------
async def fetch_gold_standard_json(details_url: str) -> dict:
    project_id = extract_project_id(details_url)
    api_url = f"{GS_API_BASE}/{project_id}"

    print(f"🔗 Calling Gold Standard API:")
    print(f"    {api_url}")

    headers = {
        "accept": "application/json",
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/143.0.0.0 Safari/537.36"
        ),
        "origin": "https://registry.goldstandard.org",
        "referer": "https://registry.goldstandard.org/",
    }

    async with httpx.AsyncClient(timeout=30, headers=headers) as client:
        resp = await client.get(api_url)
        print("HTTP status:", resp.status_code)
        resp.raise_for_status()
        return resp.json()


# -------------------------------------------------------------
# MAIN (DIRECT EXECUTION)
# -------------------------------------------------------------
async def main():
    PROJECT_URL = "https://registry.goldstandard.org/projects/details/1795"

    print(f"🌐 Fetching Gold Standard project:\n{PROJECT_URL}")
    raw = await fetch_gold_standard_json(PROJECT_URL)

    print("⚙️ Cleaning JSON...")
    cleaned = clean_gold_standard_json(raw)

    project_id = cleaned.get("id")
    if not project_id:
        raise ValueError("❌ Gold Standard JSON missing 'id'")

    project_key = f"GS_{project_id}"

    print(f"📌 Appending under key: {project_key}")

    projects_data = load_projects_file()
    projects_data.setdefault("projects", []).append(
        {project_key: cleaned}
    )
    save_projects_file(projects_data)

    print("\n✅ Saved into projects.json")
    print("\n--- Final appended object ---")
    print(json.dumps({project_key: cleaned}, indent=2, ensure_ascii=False))


