# runner.py (Gold Standard)
import asyncio
from pathlib import Path

from Scraping import (
    fetch_gold_standard_json,
    clean_gold_standard_json,
    load_projects_file,
    save_projects_file,
)
from FilterDocs import run_filter_for_project
from DownloadPdf import download_all_for_project


def pdfs_already_exist(project_key: str) -> bool:
    """
    Check if PDFs already exist for this project.
    data/pdfs/{project_key}/*.pdf
    """
    pdf_dir = Path(__file__).resolve().parent.parent / "pdfs" / project_key
    return pdf_dir.exists() and any(pdf_dir.glob("*.pdf"))


async def run_all(project_url: str, max_docs: int = 2):
    print("\n==============================")
    print("   GS SDG DATA PIPELINE START")
    print("==============================\n")

    # -------------------------------------------------
    # 1) FETCH + CLEAN + SAVE PROJECT JSON
    # -------------------------------------------------
    print(f"🌐 Fetching Gold Standard project:\n{project_url}")
    raw = await fetch_gold_standard_json(project_url)

    print("⚙️ Cleaning JSON...")
    cleaned = clean_gold_standard_json(raw)

    project_id = cleaned.get("id")
    if not project_id:
        raise ValueError("❌ Gold Standard JSON missing 'id'")

    project_key = f"GS_{project_id}"
    print(f"📌 Project key: {project_key}")

    print("💾 Appending into projects.json...")
    projects_data = load_projects_file()
    projects_data.setdefault("projects", []).append({project_key: cleaned})
    save_projects_file(projects_data)
    print("✅ Saved project into projects.json")

    # -------------------------------------------------
    # 2) FILTER DOCS
    # -------------------------------------------------
    print("\n🔍 Filtering project documents (dense SDG co-benefit + latest)...")
    await run_filter_for_project(project_key, max_docs=max_docs)

    # -------------------------------------------------
    # 3) DOWNLOAD PDFs (ONLY IF NOT PRESENT)
    # -------------------------------------------------
    print("\n📥 Checking existing PDFs...")
    if pdfs_already_exist(project_key):
        print(f"✅ PDFs already exist for {project_key}. Skipping download.")
    else:
        print("📥 No existing PDFs found. Starting download...")
        await download_all_for_project(project_key)

    print("\n==============================")
    print("      🎉 PIPELINE DONE!")
    print("==============================\n")


if __name__ == "__main__":
    PROJECT_URL = "https://registry.goldstandard.org/projects/details/2913"
    asyncio.run(run_all(PROJECT_URL, max_docs=10))
