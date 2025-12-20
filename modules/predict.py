from pathlib import Path
import numpy as np
import json
import torch
import argparse
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from tqdm import tqdm  # ✅ progress bar

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent

MODELS_DIR = PROJECT_ROOT / "models"
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = DATA_DIR / "outputs"
SENTENCE_FILE = "refined_sentences.json"


def predict_SDG1_impact(model_name, project_id):
    # -----------------------------
    # 1) Resolve paths + load data
    # -----------------------------
    model_path = MODELS_DIR / model_name
    proj_path = OUTPUT_DIR / project_id
    sentences_path = proj_path / SENTENCE_FILE
    threshold = 0.60

    print("\n[SDG1] -----------------------------")
    print(f"[SDG1] Analyzing Project ID: {project_id}")
    print(f"[SDG1] Model path: {model_path}")
    print(f"[SDG1] Sentences path: {sentences_path}")
    print(f"[SDG1] Threshold: {threshold}")
    print("[SDG1] -----------------------------")

    if not sentences_path.exists():
        raise FileNotFoundError(f"[SDG1] refined_sentences.json not found at: {sentences_path}")

    with open(sentences_path, "r", encoding="utf-8") as f:
        json_data = json.load(f)

    if "SDG_1_No_Poverty" not in json_data:
        raise KeyError("[SDG1] Key 'SDG_1_No_Poverty' not found in refined_sentences.json")

    sentences = json_data["SDG_1_No_Poverty"]
    print(f"[SDG1] Loaded sentences: {len(sentences)}")

    # -----------------------------
    # 2) Load model + tokenizer
    # -----------------------------
    print("[SDG1] Loading tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(model_path)

    print("[SDG1] Loading model...")
    model = AutoModelForSequenceClassification.from_pretrained(model_path)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = model.to(device)

    print(f"[SDG1] Using device: {device}")
    model.eval()
    print("[SDG1] Model ready. Starting inference...")

    # -----------------------------
    # 3) Perform inference
    # -----------------------------
    labels = ["O1", "O2", "O3", "O5", "O6", "R3", "R4", "R5", "R6", "I1", "I3", "I5"]
    rule_evidence = {label: [] for label in labels}

    matched_total = 0
    processed_total = 0

    # tqdm progress bar over sentences
    for text in tqdm(sentences, desc="[SDG1] Processing sentences", ncols=100):
        processed_total += 1

        inputs = tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            padding=True,
            max_length=512
        )

        # Move inputs to device (NO logic change, just makes GPU work properly too)
        inputs = {k: v.to(device) for k, v in inputs.items()}

        with torch.no_grad():
            logits = model(**inputs).logits
            probs = torch.sigmoid(logits).squeeze().detach().cpu().numpy()

            # Safety: if single label returns scalar, make it array-like
            probs = np.atleast_1d(probs)

            for i, prob in enumerate(probs):
                if prob >= threshold:
                    label = labels[i]
                    rule_evidence[label].append({
                        "sentence": text,
                        "probability": round(float(prob), 4)
                    })
                    matched_total += 1

        # lightweight heartbeat logs every 200 sentences
        if processed_total % 200 == 0:
            print(f"[SDG1] Progress: {processed_total}/{len(sentences)} | total matches so far: {matched_total}")

    print(f"[SDG1] Inference complete. Total matches found: {matched_total}")

    # -----------------------------
    # 4) Filter and save output
    # -----------------------------
    final_output = {
        "satisfied_rules": {k: v for k, v in rule_evidence.items() if len(v) > 0}
    }

    output_filename = f"{model_name}_evidence.json"
    output_path = proj_path / output_filename
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(final_output, f, indent=4, ensure_ascii=False)

    print(f"[SDG1] Evidence saved to: {output_path}")
    print(f"[SDG1] Rules satisfied: {len(final_output['satisfied_rules'])}/{len(labels)}")

    # Optional: quick per-rule counts
    for r, ev in final_output["satisfied_rules"].items():
        print(f"[SDG1]  - {r}: {len(ev)}")

    return final_output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Predict SDG impact for a project.")
    parser.add_argument("--m", type=str, required=True, help="Model name (folder inside ./models)")
    parser.add_argument("--p", type=str, required=True, help="ID of the project to analyze (folder inside ./data/outputs)")

    args = parser.parse_args()
    predict_SDG1_impact(args.m, args.p)
