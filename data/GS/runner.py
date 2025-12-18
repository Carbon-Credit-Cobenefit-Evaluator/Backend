# runner.py (Gold Standard) ✅ run: scrape -> filter docs -> download PDFs

import asyncio

from Scraping import fetch_gold_standard_json, clean_gold_standard_json, load_projects_file, save_projects_file
from FilterDocs import run_filter_for_project  # you'll add this function (below)
from DownloadPdf import download_all_for_project


async def run_all(project_url: str, max_docs: int = 10):
    print("\n==============================")
    print("   GS SDG DATA PIPELINE START")
    print("==============================\n")

    # -----------------------------
    # 1) FETCH + CLEAN + SAVE PROJECT JSON
    # -----------------------------
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

    # -----------------------------
    # 2) FILTER DOCS (top max_docs, dense + latest)
    # -----------------------------
    print("\n🔍 Filtering project documents (dense SDG co-benefit + latest)...")
    await run_filter_for_project(project_key, max_docs=max_docs)

    # -----------------------------
    # 3) DOWNLOAD PDFs
    # -----------------------------
    print("\n📥 Downloading PDFs...")
    await download_all_for_project(project_key)

    print("\n==============================")
    print("      🎉 PIPELINE DONE!")
    print("==============================\n")


if __name__ == "__main__":
    # ✅ Change only this URL
    PROJECT_URL = "https://registry.goldstandard.org/projects/details/2913"

    asyncio.run(run_all(PROJECT_URL, max_docs=10))
