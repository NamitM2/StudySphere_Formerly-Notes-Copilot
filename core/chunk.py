# core/chunk.py
# Path: core/chunk.py
from __future__ import annotations
import re
from typing import List


def _normalize(s: str) -> str:
    s = s.replace("\u2013", "-").replace("\u2014", "-")
    s = re.sub(r"[ \t]+", " ", s)
    return s.strip()


def split_text(text: str, max_chars: int = 900, overlap: int = 150) -> List[str]:
    """
    Windowed chunking with overlap. Preserves context so entities like
    'University of Illinois Urbana–Champaign' don't get split away.
    """
    t = _normalize(text)
    if not t:
        return []
    chunks: List[str] = []
    start = 0
    n = len(t)
    while start < n:
        end = min(n, start + max_chars)
        chunks.append(t[start:end])
        if end == n:
            break
        start = max(0, end - overlap)
    return chunks
