# modules/cleaning.py

import re
from typing import List, Optional

import spacy
from config.settings import SPACY_MODEL

# Load spaCy model once at import time
nlp = spacy.load(SPACY_MODEL)

TABLE_HEADING_RE = re.compile(r"^(Table|Annex|Illustration)\s+\d+", re.IGNORECASE)
DOT_LEADER_RE = re.compile(r"([._-]){2,}")
NUMERIC_ONLY_RE = re.compile(r"^[\d\s,.\-()\[\]]+$")
ALL_CAPS_HEADING_RE = re.compile(r"^[A-Z\s]{5,}$")


def split_into_sentences(text: str) -> List[str]:
    """
    Use spaCy to split a large text into sentences.
    Much better than text.split(".") – handles abbreviations, etc.
    """
    doc = nlp(text)
    return [sent.text.strip() for sent in doc.sents if sent.text.strip()]


def clean_sentence(sentence: str) -> Optional[str]:
    """
    Clean a single sentence:
    - drop table/annex headings
    - drop numeric-only junk
    - drop very short/heading-like lines
    - normalize whitespace
    """
    if not sentence:
        return None

    # strip once
    sentence = sentence.strip()
    if not sentence:
        return None

    lines = sentence.splitlines()
    cleaned_lines = []

    for line in lines:
        l = line.strip()
        if not l:
            continue

        # skip table / annex headings
        if TABLE_HEADING_RE.match(l):
            continue

        # skip lines like "... ..... 12"
        if DOT_LEADER_RE.search(l):
            continue

        # skip numeric-only lines
        if NUMERIC_ONLY_RE.fullmatch(l):
            continue

        # skip all-caps short headings
        if ALL_CAPS_HEADING_RE.match(l) and len(l.split()) <= 8:
            continue

        cleaned_lines.append(" ".join(l.split()))

    if not cleaned_lines:
        return None

    joined = " ".join(cleaned_lines).strip()

    # your original logic: at least 6 words and 30 chars
    if len(joined.split()) < 6 or len(joined) < 30:
        return None

    return joined
