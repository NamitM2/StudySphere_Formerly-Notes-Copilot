# core/pdf.py
from __future__ import annotations
from typing import List
import fitz  # PyMuPDF


def extract_text_from_pdf(pdf_bytes: bytes) -> List[str]:
    """
    Robust PDF text extraction using PyMuPDF.
    Returns a list of page texts (already lightly normalized).
    """
    pages: List[str] = []
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for page in doc:
            t = page.get_text("text") or ""
            t = t.replace("\u2013", "-").replace("\u2014", "-")
            t = "\n".join(line.strip() for line in t.splitlines())
            pages.append(t)
    return pages


def smoke_assert_contains(texts: List[str], needle: str) -> None:
    """
    Quick ingestion smoke test. Join texts and assert a phrase exists.
    Raise early if a PDF parsed empty/garbled.
    """
    hay = " ".join(texts).lower()
    if needle.lower() not in hay:
        raise ValueError(f"PDF text missing expected phrase: {needle!r}")


