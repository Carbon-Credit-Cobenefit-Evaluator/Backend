# runner.py (inside data/)

import asyncio

from Scraping import fetch_verra_json, rearrange, load_projects_file, save_projects_file
from FilterDocs import select_prioritized_docs, save_to_projectdocs
from DownloadPdf import download_all_for_project


async def run_all(project_url: str, max_docs: int = 10):
    print("\n==============================")
    print("   SDG DATA PIPELINE START")
    print("==============================\n")

    # 1) FETCH + REARRANGE JSON
    print(f"🌐 Fetching JSON for URL:\n{project_url}")
    raw_json = await fetch_verra_json(project_url)

    print("⚙️ Rearranging JSON structure...")
    cleaned = rearrange(raw_json)

    rid = cleaned.get("resourceIdentifier")
    if not rid:
        raise ValueError("❌ resourceIdentifier missing in fetched JSON. API response format may have changed.")

    project_key = f"VCS_{rid}"

    # Save to projects.json
    print(f"📌 Saving rearranged JSON under key: {project_key}")
    projects_file_data = load_projects_file()
    projects_file_data.setdefault("projects", []).append({project_key: cleaned})
    save_projects_file(projects_file_data)

    # 2) FILTER + PRIORITIZE (max 10)
    print(f"\n🔍 Selecting prioritized docs (max {max_docs})...")
    docs = cleaned.get("documents", [])
    selected_docs = select_prioritized_docs(docs, max_docs=max_docs)

    print(f"📄 Selected {len(selected_docs)} docs:")
    for d in selected_docs:
        print(f" - {d.get('documentType','')} → {d.get('documentName','')}")

    save_to_projectdocs(project_key, selected_docs)

    # 3) DOWNLOAD PDFs
    print("\n📥 Starting PDF downloads...")
    await download_all_for_project(project_key)

    print("\n==============================")
    print("      🎉 PIPELINE DONE!")
    print("==============================\n")


if __name__ == "__main__":
    # ✅ change only this
    PROJECT_URL = "https://registry.verra.org/app/projectDetail/VCS/514"

    asyncio.run(run_all(PROJECT_URL, max_docs=10))
