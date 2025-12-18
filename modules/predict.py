from pathlib import Path
import numpy as np
import json
import torch
import argparse
from transformers import AutoTokenizer, AutoModelForSequenceClassification

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent

MODELS_DIR = PROJECT_ROOT / "models"
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = DATA_DIR / "outputs"
SENTENCE_FILE = "refined_sentences.json"

def predict_SDG1_impact(model_name, project_id):
    # 1. Load the dataset to find the project text
    model_path = MODELS_DIR / model_name
    proj_path = OUTPUT_DIR / project_id
    sentences_path = proj_path / SENTENCE_FILE
    threshold = 0.60
    with open(sentences_path, 'r') as f:
     json_data = json.load(f) 
    sentences = json_data["SDG_1_No_Poverty"]
    print(f"\nAnalyzing Project ID: {project_id}")

    # 2. Load Model and Tokenizer
    tokenizer = AutoTokenizer.from_pretrained(model_path)
    model = AutoModelForSequenceClassification.from_pretrained(model_path)

    # 3. Perform Inference
    model.eval()
    labels = ['O1', 'O2', 'O3', 'O5', 'O6', 'R3', 'R4', 'R5', 'R6', 'I1', 'I3', 'I5']
    rule_evidence = {label: [] for label in labels}
    # class_names = model.config.id2label
    for text in sentences:
        inputs = tokenizer(text, return_tensors="pt", truncation=True, padding=True, max_length=512)
        
        with torch.no_grad():
            logits = model(**inputs).logits
            probs = torch.sigmoid(logits).squeeze().cpu().numpy()
            
            for i, prob in enumerate(probs):
                if prob >= threshold:
                    label = labels[i]
                    # Store the sentence and its probability
                    rule_evidence[label].append({
                        "sentence": text,
                        "probability": round(float(prob), 4)
                    })

    # 3. Filter out rules that had zero matches to keep the JSON clean
    final_output = {
        "satisfied_rules": {k: v for k, v in rule_evidence.items() if len(v) > 0}
    }

    # 4. Save to JSON file
    output_filename = f"{model_name}_evidence.json"
    output_path = proj_path / output_filename
    output_path.parent.mkdir(parents=True, exist_ok=True) # Ensure folder exists

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(final_output, f, indent=4)

    print(f"Evidence saved to: {output_path}")
    return final_output

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Predict SDG impact for a project.")
    parser.add_argument("--m", type=str, required=True, help="Model name")
    parser.add_argument("--p", type=str, required=True, help="ID of the project to analyze")

    args = parser.parse_args()
    predict_SDG1_impact(args.m, args.p)