from modules.pdf_extraction import load_pdfs
from modules.cleaning import split_into_sentences, clean_sentence
from modules.factor_matching import match_factors
from modules.scoring import aggregate_by_sdg
from modules.assessment import assess_factors_from_refined
from modules.table_extraction import extract_table_sentences
from modules.evidence_refiner import refine_evidence
from config.settings import BASE_OUTPUT_DIR

import json
import os

def run_pipeline(project_name: str):
    print(f"\n==============================")
    print(f"[PIPELINE] Project: {project_name}")
    print(f"==============================")

    docs = load_pdfs(project_name)

    text_sentences = []
    table_sentences = []

    for doc in docs:
        for sent in split_into_sentences(doc["text"]):
            cleaned = clean_sentence(sent)
            if cleaned:
                text_sentences.append({"pdf": doc["filename"], "text": cleaned})

    for doc in docs:
        pdf_path = doc["path"]
        pdf_name = doc["filename"]
        table_sentences.extend(extract_table_sentences(pdf_path, pdf_name))

    print(f"[INFO] Text sentences for {project_name}: {len(text_sentences)}")
    print(f"[INFO] Table sentences for {project_name}: {len(table_sentences)}")
    print(f"[INFO] Total sentences for {project_name}: {len(text_sentences) + len(table_sentences)}")

    text_matches = match_factors(text_sentences)
    table_matches = match_factors(table_sentences) if table_sentences else {}

    refined_text_matches = refine_evidence(text_matches)

    final_evidence = {}

# include all factors that appear in either text or tables
    all_factors = set(refined_text_matches.keys()) | set(table_matches.keys())

    for factor in all_factors:
        from_text = refined_text_matches.get(factor, [])
        from_tables = table_matches.get(factor, [])
        final_evidence[factor] = from_text + from_tables

    assessments = assess_factors_from_refined(final_evidence)


    # Per-project output folder
    output_dir = os.path.join(BASE_OUTPUT_DIR, project_name)
    os.makedirs(output_dir, exist_ok=True)

    with open(os.path.join(output_dir, "text_factor_sentences.json"), "w", encoding="utf-8") as f:
        json.dump(text_matches, f, ensure_ascii=False, indent=2)

    with open(os.path.join(output_dir, "table_factor_sentences.json"), "w", encoding="utf-8") as f:
        json.dump(table_matches, f, ensure_ascii=False, indent=2)

    with open(os.path.join(output_dir, "refined_sentences.json"), "w", encoding="utf-8") as f:
        json.dump(final_evidence, f, ensure_ascii=False, indent=2)

    with open(os.path.join(output_dir, "assessments.json"), "w", encoding="utf-8") as f:
        json.dump(assessments, f, ensure_ascii=False, indent=2)

    sdg_aggregation = aggregate_by_sdg(assessments)
    with open(os.path.join(output_dir, "sdg_ratings.json"), "w", encoding="utf-8") as f:
        json.dump(sdg_aggregation, f, ensure_ascii=False, indent=2)

    print(f"[INFO] Overall SDG rating for {project_name}: {sdg_aggregation['overall']}")
    print("[SUCCESS] Pipeline finished for", project_name)
