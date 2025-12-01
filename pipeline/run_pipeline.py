from modules.pdf_extraction import load_pdfs
from modules.cleaning import split_into_sentences, clean_sentence
from modules.factor_matching import match_factors
from modules.scoring import aggregate_by_sdg
from modules.assessment import assess_factors_from_refined
from modules.evidence_refiner import refine_evidence
from config.settings import BASE_OUTPUT_DIR

import json
import os

def run_pipeline(project_name: str):
    print(f"\n==============================")
    print(f"[PIPELINE] Project: {project_name}")
    print(f"==============================")

    docs = load_pdfs(project_name)

    sentences = []
    for doc in docs:
        for sent in split_into_sentences(doc["text"]):
            cleaned = clean_sentence(sent)
            if cleaned:
                sentences.append({"pdf": doc["filename"], "text": cleaned})


    print(f"[INFO] Total cleaned sentences for {project_name}: {len(sentences)}")

    matches = match_factors(sentences)
    refined = refine_evidence(matches)
    assessments = assess_factors_from_refined(matches)


    # Per-project output folder
    output_dir = os.path.join(BASE_OUTPUT_DIR, project_name)
    os.makedirs(output_dir, exist_ok=True)

    with open(os.path.join(output_dir, "factor_sentences.json"), "w", encoding="utf-8") as f:
        json.dump(matches, f, ensure_ascii=False, indent=2)

    with open(os.path.join(output_dir, "refined_sentences.json"), "w", encoding="utf-8") as f:
        json.dump(refined, f, ensure_ascii=False, indent=2)

    with open(os.path.join(output_dir, "assessments.json"), "w", encoding="utf-8") as f:
        json.dump(assessments, f, ensure_ascii=False, indent=2)

    sdg_aggregation = aggregate_by_sdg(assessments)
    with open(os.path.join(output_dir, "sdg_ratings.json"), "w", encoding="utf-8") as f:
        json.dump(sdg_aggregation, f, ensure_ascii=False, indent=2)

    print(f"[INFO] Overall SDG rating for {project_name}: {sdg_aggregation['overall']}")
    print("[SUCCESS] Pipeline finished for", project_name)
