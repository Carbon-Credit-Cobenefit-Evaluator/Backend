# run_pipeline.py

from __future__ import annotations

import json
import os
from pathlib import Path

from config.settings import BASE_OUTPUT_DIR
from config.SDG_model_registry import SDG_MODEL_REGISTRY

from modules.pdf_extraction import load_pdfs
from modules.cleaning import split_into_sentences, clean_sentence
from modules.factor_matching import match_factors
from modules.table_extraction import extract_table_sentences
from modules.evidence_refiner import (
    refine_evidence,
    refine_table_evidence,
    _dedupe_preserve_order,
)
from modules.sdg_inference import run_sdg_models_for_project


def run_pipeline(project_name: str):
    print(f"\n==============================")
    print(f"[PIPELINE] Project: {project_name}")
    print(f"==============================")

    # ----------------------------
    # 1) Load PDFs
    # ----------------------------
    docs = load_pdfs(project_name)

    # ----------------------------
    # 2) Extract + clean text sentences
    # ----------------------------
    text_sentences = []
    for doc in docs:
        for sent in split_into_sentences(doc["text"]):
            cleaned = clean_sentence(sent)
            if cleaned:
                text_sentences.append({"pdf": doc["filename"], "text": cleaned})

    # ----------------------------
    # 3) Extract table sentences
    # ----------------------------
    table_sentences = []
    for doc in docs:
        pdf_path = doc["path"]
        pdf_name = doc["filename"]
        table_sentences.extend(extract_table_sentences(pdf_path, pdf_name))

    print(f"[INFO] Text sentences for {project_name}: {len(text_sentences)}")
    print(f"[INFO] Table sentences for {project_name}: {len(table_sentences)}")
    print(f"[INFO] Total sentences for {project_name}: {len(text_sentences) + len(table_sentences)}")

    # ----------------------------
    # 4) Semantic filtering (match to SDG factors)
    # ----------------------------
    text_matches = match_factors(
        text_sentences,
        min_similarity=0.5,
    )

    table_matches = (
        match_factors(table_sentences, min_similarity=0.4)
        if table_sentences
        else {}
    )

    # ----------------------------
    # 5) Refine evidence (LLM cleanup)
    # ----------------------------
    refined_text_matches = refine_evidence(text_matches)
    refined_table_matches = refine_table_evidence(table_matches)

    # ----------------------------
    # 6) Merge text + table evidence per SDG and dedupe
    # ----------------------------
    final_evidence = {}
    all_factors = set(refined_text_matches.keys()) | set(refined_table_matches.keys())

    for factor in all_factors:
        from_text = refined_text_matches.get(factor, [])
        from_tables = refined_table_matches.get(factor, [])
        combined = from_text + from_tables
        final_evidence[factor] = _dedupe_preserve_order(combined)

    # ----------------------------
    # 7) Write refined_sentences.json
    # ----------------------------
    output_dir = os.path.join(BASE_OUTPUT_DIR, project_name)
    os.makedirs(output_dir, exist_ok=True)

    refined_path = os.path.join(output_dir, "refined_sentences.json")
    with open(refined_path, "w", encoding="utf-8") as f:
        json.dump(final_evidence, f, ensure_ascii=False, indent=2)

    print("[SUCCESS] refined_sentences.json saved to:", refined_path)

    # ----------------------------
    # 8) NEW: Run SDG-specific trained models (SDG1, SDG2, ...)
    #     and write evidence JSONs into:
    #     data/outputs/{project}/SDG_evidence/{SDG_KEY}_evidence.json
    # ----------------------------
    project_output_dir = Path(output_dir)

    # models/ folder at project root
    PROJECT_ROOT = Path(BASE_OUTPUT_DIR).resolve().parent.parent
    MODELS_DIR = PROJECT_ROOT / "models"


    run_sdg_models_for_project(
        project_output_dir=project_output_dir,
        models_dir=MODELS_DIR,
        sdg_model_registry=SDG_MODEL_REGISTRY,
    )

    print("[SUCCESS] SDG evidence JSONs saved to:", project_output_dir / "SDG_evidence")
    print("[SUCCESS] Pipeline finished for", project_name)
