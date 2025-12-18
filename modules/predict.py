from pathlib import Path
import json
import torch
import argparse
import logging
from tqdm import tqdm
from transformers import AutoTokenizer, AutoModelForSequenceClassification

# ----------------------------
# PATH SETUP
# ----------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent

MODELS_DIR = PROJECT_ROOT / "models"
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = DATA_DIR / "outputs"
SENTENCE_FILE = "refined_sentences.json"

# ----------------------------
# LOGGING
# ----------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("SDG1-Inference")


def predict_SDG1_impact(model_name: str, project_id: str):
    logger.info("Starting SDG1 impact prediction")

    # 1) Paths
    model_path = MODELS_DIR / model_name
    proj_path = OUTPUT_DIR / project_id
    sentences_path = proj_path / SENTENCE_FILE
    threshold = 0.60

    logger.info(f"Model path: {model_path}")
    logger.info(f"Project path: {proj_path}")
    logger.info(f"Sentences file: {sentences_path}")
    logger.info(f"Threshold: {threshold}")

    if not model_path.exists():
        raise FileNotFoundError(f"Model folder not found: {model_path}")

    if not sentences_path.exists():
        raise FileNotFoundError(f"Sentences JSON not found: {sentences_path}")

    # 2) Load sentences
    logger.info("Loading refined sentences JSON...")
    with open(sentences_path, "r", encoding="utf-8") as f:
        json_data = json.load(f)

    if "SDG_1_No_Poverty" not in json_data:
        raise KeyError(
            f'"SDG_1_No_Poverty" key not found in {sentences_path}. '
            f"Available keys: {list(json_data.keys())}"
        )

    sentences = json_data["SDG_1_No_Poverty"]
    logger.info(f"Loaded {len(sentences)} SDG1 candidate sentences")

    # 3) Device
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info(f"Using device: {device}")

    # 4) Load Model + Tokenizer
    logger.info("Loading tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(model_path)

    logger.info("Loading model...")
    model = AutoModelForSequenceClassification.from_pretrained(model_path)
    model.to(device)
    model.eval()
    logger.info("Model loaded successfully")

    # 5) Labels (must match model output order)
    labels = ['O1', 'O2', 'O3', 'O5', 'O6', 'R3', 'R4', 'R5', 'R6', 'I1', 'I3', 'I5']
    rule_evidence = {label: [] for label in labels}

    # Optional safety check: ensure output size matches labels count
    try:
        num_model_labels = model.config.num_labels
        if num_model_labels != len(labels):
            logger.warning(
                f"Model num_labels ({num_model_labels}) != labels list length ({len(labels)}). "
                f"Make sure label order/size matches your trained model."
            )
    except Exception:
        pass

    # 6) Inference with progress bar
    logger.info("Starting inference over sentences...")
    for text in tqdm(sentences, desc="Analyzing sentences", unit="sent"):
        inputs = tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            padding=True,
            max_length=512
        )
        inputs = {k: v.to(device) for k, v in inputs.items()}

        with torch.no_grad():
            logits = model(**inputs).logits
            probs = torch.sigmoid(logits).squeeze().cpu().numpy()

            for i, prob in enumerate(probs):
                if prob >= threshold:
                    rule_evidence[labels[i]].append({
                        "sentence": text,
                        "probability": round(float(prob), 4)
                    })

    # 7) Filter empty rules
    final_output = {
        "satisfied_rules": {k: v for k, v in rule_evidence.items() if len(v) > 0}
    }

    # 8) Save output JSON
    output_filename = f"{model_name}_evidence.json"
    output_path = proj_path / output_filename
    output_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"Saving evidence JSON to: {output_path}")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(final_output, f, indent=4, ensure_ascii=False)

    logger.info("Done ✅")
    return final_output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Predict SDG impact for a project.")
    parser.add_argument("--m", type=str, required=True, help="Model name (folder inside PROJECT_ROOT/models)")
    parser.add_argument("--p", type=str, required=True, help="Project ID (folder inside data/outputs)")

    args = parser.parse_args()
    predict_SDG1_impact(args.m, args.p)
