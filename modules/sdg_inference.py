# modules/sdg_inference.py

from __future__ import annotations

from pathlib import Path
import json
import logging
from typing import Dict, List, Any, Optional

import torch
from tqdm import tqdm
from transformers import AutoTokenizer, AutoModelForSequenceClassification

logger = logging.getLogger("SDG-Inference")

# ----------------------------
# Helpers
# ----------------------------

def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)

def _default_device() -> torch.device:
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def run_sdg_models_for_project(
    project_output_dir: Path,
    models_dir: Path,
    sdg_model_registry: Dict[str, Dict[str, Any]],
    sentence_file: str = "refined_sentences.json",
    output_subdir: str = "SDG_evidence",
    device: Optional[torch.device] = None,
) -> Dict[str, Path]:
    """
    Reads refined_sentences.json from project_output_dir,
    runs the correct model per SDG key, and writes evidence JSONs.

    sdg_model_registry format example:
    {
      "SDG_1_No_Poverty": {
        "model_folder": "SDG1",
        "labels": ["O1","O2",...],
        "threshold": 0.60
      },
      "SDG_2_Zero_Hunger": {...},
      ...
    }

    Returns:
      Dict[sdg_key -> evidence_json_path]
    """
    device = device or _default_device()

    sentences_path = project_output_dir / sentence_file
    if not sentences_path.exists():
        raise FileNotFoundError(f"Missing refined sentences file: {sentences_path}")

    with open(sentences_path, "r", encoding="utf-8") as f:
        refined = json.load(f)

    out_dir = project_output_dir / output_subdir
    _ensure_dir(out_dir)

    written: Dict[str, Path] = {}

    # We only run SDGs that exist in refined AND exist in registry (have a model configured)
    for sdg_key, cfg in sdg_model_registry.items():
        if sdg_key not in refined:
            continue

        sentences: List[str] = refined.get(sdg_key, []) or []
        if not sentences:
            evidence_path = out_dir / f"{sdg_key}_evidence.json"
            with open(evidence_path, "w", encoding="utf-8") as f:
                json.dump({"satisfied_rules": {}}, f, indent=2, ensure_ascii=False)
            written[sdg_key] = evidence_path
            continue


        model_folder = cfg["model_folder"]
        labels: List[str] = cfg["labels"]
        threshold: float = float(cfg.get("threshold", 0.60))

        model_path = models_dir / model_folder
        if not model_path.exists():
            logger.warning(f"[INF] Model folder not found for {sdg_key}: {model_path} (skipping)")
            continue

        logger.info(f"[INF] Running {sdg_key} using model '{model_folder}' on {len(sentences)} sentences")

        tokenizer = AutoTokenizer.from_pretrained(model_path)
        model = AutoModelForSequenceClassification.from_pretrained(model_path)
        model.to(device)
        model.eval()

        # Safety check
        try:
            if model.config.num_labels != len(labels):
                logger.warning(
                    f"[INF] {sdg_key}: model.num_labels={model.config.num_labels} "
                    f"!= labels={len(labels)}. Ensure label order/size matches training."
                )
        except Exception:
            pass

        rule_evidence: Dict[str, List[Dict[str, Any]]] = {lab: [] for lab in labels}

        for text in tqdm(sentences, desc=f"{sdg_key} inference", unit="sent"):
            inputs = tokenizer(
                text,
                return_tensors="pt",
                truncation=True,
                padding=True,
                max_length=512,
            )
            inputs = {k: v.to(device) for k, v in inputs.items()}

            with torch.no_grad():
                logits = model(**inputs).logits
                probs = torch.sigmoid(logits).squeeze().detach().cpu().numpy()

            # Handle edge cases: single label output
            if probs.ndim == 0:
                probs = [float(probs)]

            for i, prob in enumerate(probs):
                if i >= len(labels):
                    break
                if float(prob) >= threshold:
                    rule_evidence[labels[i]].append(
                        {"sentence": text, "probability": round(float(prob), 4)}
                    )

        final_output = {
            "satisfied_rules": {k: v for k, v in rule_evidence.items() if v},
        }

        evidence_path = out_dir / f"{sdg_key}_evidence.json"
        with open(evidence_path, "w", encoding="utf-8") as f:
            json.dump(final_output, f, indent=2, ensure_ascii=False)

        written[sdg_key] = evidence_path

    logger.info(f"[INF] Wrote {len(written)} SDG evidence files to {out_dir}")
    return written
