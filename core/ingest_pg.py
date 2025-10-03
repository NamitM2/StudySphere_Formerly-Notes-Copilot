# core/ingest_pg.py
from __future__ import annotations

import io
from typing import List, Tuple, Dict, Any

from pypdf import PdfReader

from api.supa import admin_client
from api.storage import upload_bytes
from core.embeddings import embed_texts
from core.chunk import split_text


def _collect_chunks(pairs: List[Tuple[int, str]]) -> List[Tuple[int, str]]:
    seen: set[str] = set()
    cleaned: List[Tuple[int, str]] = []
    for page, chunk in pairs:
        key = (chunk or "").strip()
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
        cleaned = "\n".join(
            line.strip()
            for line in raw.replace("\r", "\n").splitlines()
            if line.strip()
        )
        for segment in split_text(cleaned, max_chars=chunk_chars, overlap=overlap):
            if segment:
                pieces.append((i + 1, segment))  # 1-based page for display
    return _collect_chunks(pieces)


def _text_chunks(file_bytes: bytes, chunk_chars: int = 360, overlap: int = 90) -> List[Tuple[int, str]]:
    raw = file_bytes.decode("utf-8", errors="ignore")
    cleaned = "\n".join(
        line.strip()
        for line in raw.replace("\r", "\n").splitlines()
        if line.strip()
    )
    pieces = [(1, segment) for segment in split_text(cleaned, max_chars=chunk_chars, overlap=overlap)]
    return _collect_chunks(pieces)


def ingest_file(user_id: str, filename: str, file_bytes: bytes, mime: str | None):
    supa = admin_client()

    # 1) Upload to storage
    storage_path, _created = upload_bytes(
        user_id=user_id,
        filename=filename,
        data=file_bytes,
        content_type=mime or "application/octet-stream",
        upsert=True,
        unique_fallback=True,
    )

    # 2) Insert document row
    try:
        doc_res = (
            supa.table("documents")
            .insert(
                {
                    "user_id": user_id,
                    "filename": filename,
                    "mime": mime,
                    "byte_size": len(file_bytes),
                    "storage_path": storage_path,
                }
            )
            .execute()
        )
        doc_id = doc_res.data[0]["id"]
    except Exception as e:
        try:
            from api.storage import delete_paths
            delete_paths([storage_path])
        except Exception:
            pass
        raise RuntimeError(f"DB insert failed: {e}")

    # 3) Chunking
    if filename.lower().endswith(".pdf"):
        chunk_pairs = _pdf_chunks(file_bytes)
    else:
        chunk_pairs = _text_chunks(file_bytes)

    if not chunk_pairs:
        return {"doc_id": doc_id, "filename": filename, "chunks": 0}

    pages: List[int] = [p for p, _ in chunk_pairs]
    texts: List[str] = [t for _, t in chunk_pairs]
    n = len(texts)

    # 4) Embed ALL chunks
    vectors = embed_texts(texts)
    if vectors.shape[0] != n:
        raise RuntimeError(
            f"Embedding count mismatch: have {n} chunks but embed_texts returned {vectors.shape[0]} vectors"
        )

    # 5) Build rows with explicit chunk_index
    rows: List[Dict[str, Any]] = []
    for i in range(n):
        rows.append(
            {
                "doc_id": doc_id,
                "chunk_index": i,          # matches UNIQUE(doc_id, chunk_index)
                "page": pages[i],
                "text": texts[i],
                "embedding": vectors[i].tolist(),  # pgvector accepts lists
            }
        )

    # 6) Upsert in batches; fallback to delete+insert if constraint missing
    BATCH = 200
    try:
        for start in range(0, len(rows), BATCH):
            batch = rows[start:start + BATCH]
            (
                supa.table("chunks")
                .upsert(batch, on_conflict="doc_id,chunk_index")  # <-- string, not list
                .execute()
            )
    except Exception:
        # Fallback: idempotent recreate for this document
        supa.table("chunks").delete().eq("doc_id", doc_id).execute()
        for start in range(0, len(rows), BATCH):
            batch = rows[start:start + BATCH]
            supa.table("chunks").insert(batch).execute()

    return {"doc_id": doc_id, "filename": filename, "chunks": len(rows)}

