# modules/table_extraction.py

from typing import List, Dict
import re
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import camelot
from PyPDF2 import PdfReader
from config.settings import logger


NUMERIC_ONLY_RE = re.compile(r"^[\d\s.,%()\-+/]+$")


def _clean_cell(val: str) -> str:
    if val is None:
        return ""
    return " ".join(str(val).split()).strip()


def _clean_header(val: str, idx: int) -> str:
    txt = _clean_cell(val)
    if not txt:
        return f"col_{idx+1}"
    txt = txt.lower()
    txt = re.sub(r"\s+", "_", txt)
    return txt


def _normalize_for_dedupe(text: str) -> str:
    t = text.lower().strip()
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"[,:;|•·—–\-_/()\[\]{}]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _extract_lattice_page(pdf_path: str, pdf_name: str, page: int) -> List[Dict[str, str]]:
    results: List[Dict[str, str]] = []

    try:
        tables = camelot.read_pdf(
            pdf_path,
            pages=str(page),
            flavor="lattice",
            backend="ghostscript",
        )
    except Exception:
        return results

    if not tables or tables.n == 0:
        return results

    for table in tables:
        df = table.df
        if df.shape[0] < 2 or df.shape[1] == 0:
            continue

        raw_headers = df.iloc[0].tolist()
        headers = [_clean_header(h, i) for i, h in enumerate(raw_headers)]
        generic_headers = all(h.startswith("col_") for h in headers)

        for row_idx in range(1, df.shape[0]):
            row_vals = [_clean_cell(v) for v in df.iloc[row_idx].tolist()]
            if not any(row_vals):
                continue

            if generic_headers and all((not v) or NUMERIC_ONLY_RE.fullmatch(v) for v in row_vals):
                continue

            parts = []
            for h, v in zip(headers, row_vals):
                if v:
                    parts.append(f"{h} {v}")

            if parts:
                results.append({"pdf": pdf_name, "text": "; ".join(parts)})

    return results


def extract_table_sentences(pdf_path: str, pdf_name: str) -> List[Dict[str, str]]:
    logger.info(f"[TABLE] Extracting tables from {pdf_name} ({pdf_path})")

    try:
        num_pages = len(PdfReader(pdf_path).pages)
    except Exception as e:
        logger.error(f"[TABLE] Failed to read page count for {pdf_name}: {e}")
        return []

    logger.info(f"[TABLE] PDF pages: {num_pages}")

    workers = max(1, (os.cpu_count() or 2) - 1)
    logger.info(f"[TABLE] Using {workers} parallel workers (lattice-only)")

    results: List[Dict[str, str]] = []

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [
            executor.submit(_extract_lattice_page, pdf_path, pdf_name, page)
            for page in range(1, num_pages + 1)
        ]
        for fut in as_completed(futures):
            try:
                results.extend(fut.result())
            except Exception as e:
                logger.warning(f"[TABLE] Page extraction failed in {pdf_name}: {e}")

    # Global normalized dedupe
    seen = set()
    final: List[Dict[str, str]] = []
    for r in results:
        key = _normalize_for_dedupe(r["text"])
        if key in seen:
            continue
        seen.add(key)
        final.append(r)

    logger.info(f"[TABLE] Extracted {len(final)} table sentences from {pdf_name}.")
    return final