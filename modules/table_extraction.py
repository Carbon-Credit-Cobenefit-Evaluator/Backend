# modules/table_extraction.py

from typing import List, Dict
import re

import camelot
from config.settings import logger


NUMERIC_ONLY_RE = re.compile(r"^[\d\s.,%()\-+/]+$")


def _clean_cell(val: str) -> str:
    """Basic cleanup for table cell text."""
    if val is None:
        return ""
    # collapse whitespace and strip
    return " ".join(str(val).split()).strip()


def _clean_header(val: str, idx: int) -> str:
    """Normalize header names: lowercase, no weird spacing, fallback to col_#."""
    txt = _clean_cell(val)
    if not txt:
        return f"col_{idx+1}"
    # lowercase and replace spaces with underscores
    txt = txt.lower()
    txt = re.sub(r"\s+", "_", txt)
    return txt


def extract_table_sentences(pdf_path: str, pdf_name: str) -> List[Dict[str, str]]:
    """
    Extract tables from a PDF and convert rows into pseudo-sentences.

    Returns a list of dicts:
        [{ "pdf": pdf_name, "text": "header1 value1; header2 value2; ..." }, ...]
    """
    results: List[Dict[str, str]] = []

    logger.info(f"[TABLE] Extracting tables from {pdf_name} ({pdf_path})")

    try:
        # First try lattice mode (works well for bordered tables)
        tables = camelot.read_pdf(pdf_path, pages="all", flavor="lattice", backend = "ghostscript")
    except Exception as e:
        logger.warning(f"[TABLE] Lattice extraction failed for {pdf_name}: {e}")
        tables = None

    # If lattice found nothing, fall back to stream mode
    if not tables or tables.n == 0:
        try:
            tables = camelot.read_pdf(pdf_path, pages="all", flavor="stream")
        except Exception as e:
            logger.warning(f"[TABLE] Stream extraction failed for {pdf_name}: {e}")
            return results  # no tables at all

    if not tables or tables.n == 0:
        logger.info(f"[TABLE] No tables detected in {pdf_name}.")
        return results

    logger.info(f"[TABLE] Found {tables.n} tables in {pdf_name}.")

    for t_idx, table in enumerate(tables):
        df = table.df  # pandas DataFrame-like

        if df.shape[0] < 2 or df.shape[1] == 0:
            # Need at least one header row + one data row
            continue

        # Assume first row is header
        raw_headers = df.iloc[0].tolist()
        headers = [_clean_header(h, i) for i, h in enumerate(raw_headers)]

        # If all headers are generic col_# and all cells numeric, this is probably junk
        generic_headers = all(h.startswith("col_") for h in headers)

        # Iterate over data rows
        for row_idx in range(1, df.shape[0]):
            row_vals = [ _clean_cell(v) for v in df.iloc[row_idx].tolist() ]

            # Skip completely empty rows
            if not any(row_vals):
                continue

            # Optionally skip pure numeric rows when headers are generic
            if generic_headers and all((not v) or NUMERIC_ONLY_RE.fullmatch(v) for v in row_vals):
                continue

            parts = []
            for h, v in zip(headers, row_vals):
                if not v:
                    continue
                # Build key-value style fragment: "header value"
                parts.append(f"{h} {v}")

            if not parts:
                continue

            pseudo_sentence = "; ".join(parts)
            results.append({
                "pdf": pdf_name,
                "text": pseudo_sentence,
            })

    logger.info(f"[TABLE] Extracted {len(results)} table sentences from {pdf_name}.")
    return results
