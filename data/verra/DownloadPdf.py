# DownloadPdf.py (inside data/)

import json
import httpx
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
PROJECTDOCS_PATH = BASE_DIR / "projectdocs.json"
PDF_BASE_DIR = BASE_DIR / "pdfs"


async def download_file(client: httpx.AsyncClient, url: str, save_path: Path):
    try:
        resp = await client.get(url, timeout=60)
        resp.raise_for_status()
        save_path.write_bytes(resp.content)
        print(f"  📥 Saved: {save_path.name}")
    except Exception as e:
        print(f"  ❌ Failed to download {url}: {e}")


async def download_all_for_project(project_key: str):
    if not PROJECTDOCS_PATH.exists():
        print("❌ projectdocs.json not found.")
        return

    data = json.loads(PROJECTDOCS_PATH.read_text(encoding="utf-8"))
    docs_list = data.get("projectdocs", [])

    project_entry = next((item for item in docs_list if project_key in item), None)
    if not project_entry:
        print(f"❌ No entry found for {project_key} in projectdocs.json")
        return

    docs = project_entry[project_key]

    project_pdf_dir = PDF_BASE_DIR / project_key
    project_pdf_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n📂 Downloading PDFs for {project_key}")
    print(f"📁 Saving into: {project_pdf_dir}")

    async with httpx.AsyncClient(follow_redirects=True) as client:
        for doc in docs:
            url = doc.get("uri")
            filename = doc.get("documentName") or "document.pdf"

            if not url:
                print("  ⚠️ Skipping doc without uri")
                continue

            if not filename.lower().endswith(".pdf"):
                filename += ".pdf"

            save_path = project_pdf_dir / filename

            if save_path.exists():
                print(f"  ⏩ Already exists: {filename}")
                continue

            print(f"  ↓ Downloading: {filename}")
            await download_file(client, url, save_path)

    print("\n✅ Completed downloads!")


if __name__ == "__main__":
    print("Run runner.py. This module only provides functions.")
