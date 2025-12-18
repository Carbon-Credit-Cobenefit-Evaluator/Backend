# runner.py  (inside data/ folder)

import asyncio
import json
from pathlib import Path

# Import functions from the other scripts
from Scraping import fetch_verra_json, rearrange, load_projects_file, save_projects_file
from FilterDocs import filter_latest_tier1_docs, save_to_projectdocs
from DownloadPdf import download_all_for_project


# ------------------------
# MAIN ORCHESTRATION LOGIC
# ------------------------
async def run_all(project_url: str):
    print("\n==============================")
    print("   SDG DATA PIPELINE START")
    print("==============================\n")

    # -----------------------------
    # 1️⃣ FETCH + REARRANGE JSON
    # -----------------------------
    print(f"🌐 Fetching JSON for URL:\n{project_url}")

    raw_json = await fetch_verra_json(project_url)

    print("⚙️ Rearranging JSON structure...")
    cleaned = rearrange(raw_json)

    rid = cleaned["resourceIdentifier"]
    project_key = f"VCS_{rid}"

    # Save to projects.json
    print(f"📌 Saving rearranged JSON under key: {project_key}")
    projects_file_data = load_projects_file()
    projects_file_data["projects"].append({project_key: cleaned})
    save_projects_file(projects_file_data)

    # -----------------------------
    # 2️⃣ FILTER DOCS (Tier-1 only)
    # -----------------------------
    print("\n🔍 Filtering Tier-1 documents (latest versions)...")

    docs = cleaned.get("documents", [])
    filtered_docs = filter_latest_tier1_docs(docs)

    print(f"📄 Selected {len(filtered_docs)} Tier-1 docs:")
    for d in filtered_docs:
        print(f" - {d['documentType']} → {d['documentName']}")

    # Save them into projectdocs.json
    save_to_projectdocs(project_key, filtered_docs)

    # -----------------------------
    # 3️⃣ DOWNLOAD PDFs
    # -----------------------------
    print("\n📥 Starting PDF downloads...")
    await download_all_for_project(project_key)

    print("\n==============================")
    print("      🎉 PIPELINE DONE!")
    print("==============================\n")


# ------------------------
# RUN WITH CUSTOM URL
# ------------------------
if __name__ == "__main__":
    # Change only this:
    PROJECT_URL = "https://registry.verra.org/app/projectDetail/VCS/4811"

    asyncio.run(run_all(PROJECT_URL))
