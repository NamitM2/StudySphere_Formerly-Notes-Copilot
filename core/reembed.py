# core/reembed.py
# Path: core/reembed.py
from __future__ import annotations

import io
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from pypdf import PdfReader

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from api.supa import admin_client, BUCKET
from core.embeddings import embed_texts
from core.chunk import split_text


def _collect_chunks(pairs: List[Tuple[int, str]]) -> List[Tuple[int, str]]:
    seen: set[str] = set()
    cleaned: List[Tuple[int, str]] = []
    for page, chunk in pairs:
        key = chunk.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        cleaned.append((page, chunk))
    return cleaned


def _pdf_chunks(file_bytes: bytes, chunk_chars: int = 360, overlap: int = 90) -> List[Tuple[int, str]]:
    reader = PdfReader(io.BytesIO(file_bytes))
    pieces: List[Tuple[int, str]] = []
    for i, page in enumerate(reader.pages):
        raw = page.extract_text() or ""
        cleaned = '\n'.join(line.strip() for line in raw.replace('\r', '\n').splitlines() if line.strip())
        for segment in split_text(cleaned, max_chars=chunk_chars, overlap=overlap):
            if segment:
                pieces.append((i + 1, segment))
    return _collect_chunks(pieces)


def _text_chunks(file_bytes: bytes, chunk_chars: int = 360, overlap: int = 90) -> List[Tuple[int, str]]:
    raw = file_bytes.decode("utf-8", errors="ignore")
    cleaned = '\n'.join(line.strip() for line in raw.replace('\r', '\n').splitlines() if line.strip())
    pieces = [(1, segment) for segment in split_text(cleaned, max_chars=chunk_chars, overlap=overlap)]
    return _collect_chunks(pieces)


def _chunk_by_mime(filename: str, file_bytes: bytes) -> List[Tuple[int, str]]:
    if filename.lower().endswith(".pdf"):
        return _pdf_chunks(file_bytes)
    return _text_chunks(file_bytes)


def _download_bytes(path: str) -> bytes:
    supa = admin_client()
    res = supa.storage.from_(BUCKET).download(path)
    if isinstance(res, dict) and "data" in res:
        return res["data"]
    if isinstance(res, (bytes, bytearray)):
        return bytes(res)
    try:
        return res.read()
    except Exception as exc:  # pragma: no cover - defensive
        raise RuntimeError(f"Could not download storage object: {path}") from exc


def reembed_user(user_id: str, only_doc_id: Optional[int] = None) -> Dict[str, Any]:
    """Rebuild embeddings for all docs (or a single doc) owned by user_id."""
    supa = admin_client()

    q = supa.table("documents").select("id, filename, storage_path, byte_size").eq("user_id", user_id)
    if only_doc_id is not None:
        q = q.eq("id", only_doc_id)
    docs = q.order("id", desc=False).execute().data or []

    results: List[Dict[str, Any]] = []
    for doc in docs:
        doc_id = doc["id"]
        filename = doc["filename"]
        storage_path = doc["storage_path"]
        try:
            b = _download_bytes(storage_path)
            chunks = _chunk_by_mime(filename, b)
            pages = [p for p, _ in chunks]
            texts = [t for _, t in chunks]

            embeddings = embed_texts(texts)

            supa.table("chunks").delete().eq("doc_id", doc_id).execute()
            if texts:
                rows = [
                    {
                        "doc_id": doc_id,
                        "page": page,
                        "text": text,
                        "embedding": embedding.tolist(),
                    }
                    for page, text, embedding in zip(pages, texts, embeddings)
                ]
                res = supa.table("chunks").insert(rows).execute()
                print(f"doc {doc_id}: inserted={getattr(res, 'data', None)} error={getattr(res, 'error', None)}")

            results.append({
                "doc_id": doc_id,
                "filename": filename,
                "chunks": len(texts),
                "status": "ok",
            })
        except Exception as exc:
            results.append({
                "doc_id": doc_id,
                "filename": filename,
                "chunks": 0,
                "status": f"error: {exc}",
            })

    return {"reembedded": results, "count": len(results)}
