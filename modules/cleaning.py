import re

def clean_sentence(text):
    lines = text.splitlines()
    cleaned = []

    for line in lines:
        if re.match(r'^(Table|Annex|Illustration) \d+', line):
            continue
        if len(line.split()) < 6 or len(line) < 30:
            continue
        cleaned.append(" ".join(line.split()))

    return " ".join(cleaned).strip()
