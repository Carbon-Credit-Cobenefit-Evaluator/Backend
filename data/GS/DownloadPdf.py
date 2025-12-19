# downloadpdf.py (Gold Standard) ✅ download selected projectdocs into data/pdfs/<project_key>/
from config.settings import PROJECTS_ROOT
import asyncio
import json
import re
from pathlib import Path
from typing import Optional
import httpx


# -------------------------------------------------------------
# PATHS
# -------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
PROJECTDOCS_PATH = BASE_DIR / "projectdocs.json"

# Your required output base:
# D:\FYPNew\FYProject\data\pdfs\<PROJECT_KEY>\
PDF_BASE_DIR = Path(r"D:\FYPNew\FYProject\data\pdfs")


# -------------------------------------------------------------
# GS DOWNLOAD ENDPOINT
# -------------------------------------------------------------
GS_DOWNLOAD_BASE = "https://assurance-platform.goldstandard.org/api/public/documents"


# -------------------------------------------------------------
# HELPERS
# -------------------------------------------------------------
def load_projectdocs() -> dict:
    if PROJECTDOCS_PATH.exists():
        return json.loads(PROJECTDOCS_PATH.read_text(encoding="utf-8"))
    return {"projectdocs": []}


def find_project_docs(projectdocs_data: dict, project_key: str) -> Optional[list]:
    """
    projectdocs.json structure:
    {
      "projectdocs": [
        { "GS_1795": [ ...docs... ] },
        { "VCS_1566": [ ... ] }
      ]
    }
    """
    for obj in projectdocs_data.get("projectdocs", []):
        if project_key in obj:
            return obj[project_key]
    return None


def safe_filename(name: str) -> str:
    """
    Make a Windows-safe filename.
    """
    name = (name or "").strip()
    name = re.sub(r'[<>:"/\\|?*\x00-\x1F]', "_", name)  # illegal Windows chars
    name = re.sub(r"\s+", " ", name).strip()
    return name[:240] if len(name) > 240 else name


def filename_from_content_disposition(cd: Optional[str]) -> Optional[str]:
    """
    Parse Content-Disposition header for filename=...
    """
    if not cd:
        return None

    # filename*=UTF-8''...
    m = re.search(r"filename\*\s*=\s*UTF-8''([^;]+)", cd, flags=re.I)
    if m:
        return m.group(1).strip().strip('"')

    # filename="..."
    m = re.search(r'filename\s*=\s*"([^"]+)"', cd, flags=re.I)
    if m:
        return m.group(1).strip()

    # filename=...
    m = re.search(r"filename\s*=\s*([^;]+)", cd, flags=re.I)
    if m:
        return m.group(1).strip().strip('"')

    return None


async def download_one(client: httpx.AsyncClient, doc_id: str, referer: str, fallback_name: str, save_dir: Path):
    url = f"{GS_DOWNLOAD_BASE}/{doc_id}/download"

    headers = {
        "accept": "*/*",
        "referer": referer,
        "x-gold-standard-api-version": "2023-04-19",
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/143.0.0.0 Safari/537.36 Edg/143.0.0.0"
        ),
    }

    try:
        resp = await client.get(url, headers=headers, timeout=60)
        resp.raise_for_status()

        cd = resp.headers.get("content-disposition")
        server_name = filename_from_content_disposition(cd)

        filename = server_name or fallback_name or f"{doc_id}.pdf"
        filename = safe_filename(filename)

        if not filename.lower().endswith(".pdf"):
            filename += ".pdf"

        save_path = save_dir / filename

        if save_path.exists():
            print(f"  ⏩ Already exists: {filename}")
            return

        save_path.write_bytes(resp.content)
        print(f"  📥 Saved: {filename}")

    except Exception as e:
        print(f"  ❌ Failed doc_id={doc_id}: {e}")


# -------------------------------------------------------------
# MAIN
# -------------------------------------------------------------
async def download_all_for_project(project_key: str):
    data = load_projectdocs()
    docs = find_project_docs(data, project_key)

    if not docs:
        print(f"❌ No entry found for {project_key} in projectdocs.json")
        return

    # Folder: D:\FYPNew\FYProject\data\pdfs\<project_key>\
    project_pdf_dir = PDF_BASE_DIR / project_key
    project_pdf_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n📂 Downloading PDFs for {project_key}")
    print(f"📁 Saving into: {project_pdf_dir}")

    async with httpx.AsyncClient(follow_redirects=True) as client:
        for doc in docs:
            doc_id = doc.get("id")
            if not doc_id:
                print("  ⚠️ Skipping doc with missing 'id'")
                continue

            # UI referer (matches how browser hits it, not required but good)
            # If you have GSID in your project data, you can build it more accurately.
            referer = "https://assurance-platform.goldstandard.org/"
            # fallback filename from your flattened doc:
            fallback_name = doc.get("filename") or f"{doc_id}.pdf"

            print(f"  ↓ Downloading: {fallback_name}")
            await download_one(client, doc_id, referer, fallback_name, project_pdf_dir)

    print("\n✅ Completed!")


