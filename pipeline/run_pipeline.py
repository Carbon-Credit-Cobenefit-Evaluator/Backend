# pipeline/run_pipeline.py

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal, Callable, Optional, Any, Dict

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
from modules.assessments.run_assessments import run_assessments_for_project

PipelineMode = Literal["full", "inference_only"]

# progress_cb(step, message, stats_dict)
ProgressCB = Callable[[str, str, Dict[str, Any]], None]


def run_pipeline(
    project_name: str,
    mode: PipelineMode = "full",
    progress_cb: Optional[ProgressCB] = None,
) -> None:
    """
    End-to-end project pipeline.

    mode:
      - "full": runs steps 1..9
          (PDF ingest -> sentence extraction/cleaning -> semantic filtering ->
           LLM refinement -> refined_sentences.json -> SDG model inference -> SDG assessment)
      - "inference_only": runs only steps 8..9 using existing refined_sentences.json
          (SDG model inference -> SDG assessment)

    progress_cb:
      Optional callback for live progress updates.
      Called as: progress_cb(step: str, message: str, stats: dict)
    """

    def _emit(step: str, message: str, stats: Optional[Dict[str, Any]] = None) -> None:
        if progress_cb:
            progress_cb(step, message, stats or {})

    print(f"\n==============================")
    print(f"[PIPELINE] Project: {project_name} | mode={mode}")
    print(f"==============================")

    _emit("decide_mode", f"Deciding mode for {project_name} (mode={mode})...", {"mode": mode})

    # ------------------------------------------------------------
    # Paths
    # ------------------------------------------------------------
    output_dir = os.path.join(BASE_OUTPUT_DIR, project_name)
    os.makedirs(output_dir, exist_ok=True)
    project_output_dir = Path(output_dir)

    # Project root (where /models, /config, /data live)
    PROJECT_ROOT = Path(BASE_OUTPUT_DIR).resolve().parent.parent
    MODELS_DIR = PROJECT_ROOT / "models"

    # ------------------------------------------------------------
    # Steps 1..7 (only in FULL mode)
    # ------------------------------------------------------------
    if mode == "full":
        # 1) Load PDFs
        _emit("load_pdfs", "Loading PDFs from data/pdfs/...", {})
        docs = load_pdfs(project_name)
        _emit("load_pdfs", f"Loaded {len(docs)} PDFs.", {"pdf_count": len(docs)})

        # 2) Extract + clean text sentences
        _emit("extract_text_sentences", "Extracting & cleaning text sentences...", {})
        text_sentences = []
        for doc in docs:
            for sent in split_into_sentences(doc["text"]):
                cleaned = clean_sentence(sent)
                if cleaned:
                    text_sentences.append({"pdf": doc["filename"], "text": cleaned})
        _emit(
            "extract_text_sentences",
            f"Extracted {len(text_sentences)} text sentences.",
            {"text_sentences": len(text_sentences)},
        )

        # 3) Extract table sentences
        _emit("extract_table_sentences", "Extracting table sentences...", {})
        table_sentences = []
        for doc in docs:
            pdf_path = doc["path"]
            pdf_name = doc["filename"]
            table_sentences.extend(extract_table_sentences(pdf_path, pdf_name))
        _emit(
            "extract_table_sentences",
            f"Extracted {len(table_sentences)} table sentences.",
            {"table_sentences": len(table_sentences)},
        )

        print(f"[INFO] Text sentences for {project_name}: {len(text_sentences)}")
        print(f"[INFO] Table sentences for {project_name}: {len(table_sentences)}")
        print(f"[INFO] Total sentences for {project_name}: {len(text_sentences) + len(table_sentences)}")

        # 4) Semantic filtering (match to SDG factors)
        _emit("factor_matching", "Running semantic filtering (embeddings + similarity)...", {})
        text_matches = match_factors(text_sentences, min_similarity=0.5)
        table_matches = match_factors(table_sentences, min_similarity=0.4) if table_sentences else {}

        _emit(
            "factor_matching",
            "Semantic filtering complete.",
            {
                "text_match_sdg_count": len(text_matches),
                "table_match_sdg_count": len(table_matches),
            },
        )

        # 5) Refine evidence (LLM cleanup)
        _emit("refine_evidence", "Refining evidence (LLM cleanup)...", {})
        refined_text_matches = refine_evidence(text_matches)
        refined_table_matches = refine_table_evidence(table_matches)

        # 6) Merge text + table evidence per SDG and dedupe
        all_factors = set(refined_text_matches.keys()) | set(refined_table_matches.keys())
        _emit(
            "refine_evidence",
            "Refinement complete. Merging & deduping evidence...",
            {"sdg_keys": len(all_factors)},
        )

        final_evidence: Dict[str, Any] = {}
        for factor in all_factors:
            from_text = refined_text_matches.get(factor, [])
            from_tables = refined_table_matches.get(factor, [])
            combined = from_text + from_tables
            final_evidence[factor] = _dedupe_preserve_order(combined)

        # 7) Write refined_sentences.json
        refined_path = os.path.join(output_dir, "refined_sentences.json")
        with open(refined_path, "w", encoding="utf-8") as f:
            json.dump(final_evidence, f, ensure_ascii=False, indent=2)

        print("[SUCCESS] refined_sentences.json saved to:", refined_path)
        _emit(
            "write_refined",
            "Saved refined_sentences.json.",
            {"refined_path": refined_path, "sdg_keys": len(final_evidence)},
        )

    elif mode == "inference_only":
        refined_path = project_output_dir / "refined_sentences.json"
        if not refined_path.exists():
            raise FileNotFoundError(
                f"Missing refined_sentences.json at: {refined_path}\n"
                f"Run mode='full' once to generate it (steps 1..7), then use inference_only."
            )

        print("[INFO] Using existing refined_sentences.json:", refined_path)
        # ✅ clearer step name for inference_only
        _emit(
            "use_refined",
            "Using existing refined_sentences.json (inference only).",
            {"refined_path": str(refined_path)},
        )

    else:
        raise ValueError(f"Invalid mode: {mode}")

    # ------------------------------------------------------------
    # Step 8) SDG-specific trained model inference
    # ------------------------------------------------------------
    _emit("sdg_inference", "Running SDG model inference...", {})
    run_sdg_models_for_project(
        project_output_dir=project_output_dir,
        models_dir=MODELS_DIR,
        sdg_model_registry=SDG_MODEL_REGISTRY,
    )
    print("[SUCCESS] SDG evidence JSONs saved to:", project_output_dir / "SDG_evidence")
    _emit(
        "sdg_inference",
        "SDG model inference finished. Evidence JSONs written.",
        {"evidence_dir": str(project_output_dir / "SDG_evidence")},
    )

    # ------------------------------------------------------------
    # Step 9) SDG assessment/scoring
    # ------------------------------------------------------------
    _emit("sdg_assessment", "Running SDG assessments (scoring)...", {})
    written_scores = run_assessments_for_project(
        project_id=project_name,
        project_root=PROJECT_ROOT,
    )
    print(f"[SUCCESS] Wrote {len(written_scores)} assessment files to:", project_output_dir / "SDG_assessment")
    _emit(
        "sdg_assessment",
        f"Assessments written ({len(written_scores)} files).",
        {"assessment_count": len(written_scores)},
    )

    print("[SUCCESS] Pipeline finished for", project_name)
    _emit("done", "Pipeline completed successfully.", {})
