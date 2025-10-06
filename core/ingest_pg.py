# core/ingest.py
from __future__ import annotations

"""
Robust ingest for PDF/MD/TXT into Supabase (documents + chunks with pgvector).

- Cleans text to remove NUL (\x00) and other control characters that Postgres can't store.
- Dedupe identical chunk texts.
- Uses on_conflict="doc_id,chunk_index" for idempotent upserts.
- Auto-fallback to delete+insert if DB lacks the unique constraint (42P10).
- Rolls back the `documents` row + deletes the stored file if anything fails.
"""

import io
import time
from typing import Any, Dict, List, Tuple

from pypdf import PdfReader

from api.supa import admin_client
from api.storage import upload_bytes, delete_paths
from core.embeddings import embed_texts  # returns np.ndarray [n, d]
from core.chunk import split_text


# ------------------------------ helpers -------------------------------------
def _sanitize_text(s: str) -> str:
    """
    Remove NULs and control characters that Postgres TEXT cannot store.
    Keep newlines and tabs, collapse excessive whitespace.
    Also handles Unicode characters safely for console output.
    """
    if not s:
        return ""
    # Replace NULs fast
    s = s.replace("\x00", " ")
    # Strip other C0 controls except \n and \t
    # (Chars 0x00-0x1F except \n(0x0A) and \t(0x09))
    s = "".join(ch if (ch >= " " or ch in ("\n", "\t")) else " " for ch in s)
    # Normalize CRLF and collapse long whitespace runs
    s = s.replace("\r", "\n")
    # Trim lines
    lines = [ln.strip() for ln in s.splitlines()]
    s = "\n".join(ln for ln in lines if ln)
    return s.strip()


def _safe_print(msg: str) -> None:
    """
    Print with fallback encoding for Windows console.
    Prevents crashes from Unicode characters that can't be displayed.
    """
    try:
        print(msg)
    except UnicodeEncodeError:
        # Fallback: encode to ASCII with replacement for problematic chars
        safe_msg = msg.encode('ascii', errors='replace').decode('ascii')
        print(safe_msg)


def _collect_chunks(pairs: List[Tuple[int, str]]) -> List[Tuple[int, str]]:
    """
    Deduplicate identical chunk texts while preserving first occurrence page index.
    """
    seen: set[str] = set()
    out: List[Tuple[int, str]] = []
    for page, txt in pairs:
        key = _sanitize_text(txt or "")
        if not key or key in seen:
            continue
        seen.add(key)
        out.append((page, key))
    return out


def _pdf_chunks(file_bytes: bytes, chunk_chars: int = 360, overlap: int = 90) -> List[Tuple[int, str]]:
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        _safe_print(f"[PDF] Opened PDF with {len(reader.pages)} pages")
    except Exception as e:
        _safe_print(f"[PDF] ERROR: Failed to read PDF: {e}")
        raise

    pieces: List[Tuple[int, str]] = []
    empty_pages = 0

    for i, page in enumerate(reader.pages):
        raw = page.extract_text() or ""
        raw = _sanitize_text(raw)
        if not raw:
            empty_pages += 1
            continue
        _safe_print(f"[PDF] Page {i+1}: Extracted {len(raw)} chars")
        for seg in split_text(raw, max_chars=chunk_chars, overlap=overlap):
            seg = _sanitize_text(seg)
            if seg:
                pieces.append((i + 1, seg))  # 1-based page

    if empty_pages == len(reader.pages):
        _safe_print(f"[PDF] WARNING: No text extracted from any page. This PDF may be scanned/image-based.")
        _safe_print(f"[PDF] Scanned PDFs require OCR (Optical Character Recognition) which is not currently enabled.")
    elif empty_pages > 0:
        _safe_print(f"[PDF] Note: {empty_pages}/{len(reader.pages)} pages had no extractable text")

    result = _collect_chunks(pieces)
    _safe_print(f"[PDF] Extracted {len(result)} text chunks")
    return result


def _plain_chunks(file_bytes: bytes, chunk_chars: int = 360, overlap: int = 90) -> List[Tuple[int, str]]:
    raw = file_bytes.decode("utf-8", errors="replace")
    raw = _sanitize_text(raw)
    if not raw:
        return []
    pieces = []
    for seg in split_text(raw, max_chars=chunk_chars, overlap=overlap):
        seg = _sanitize_text(seg)
        if seg:
            pieces.append((1, seg))
    return _collect_chunks(pieces)


# ------------------------------ public API ----------------------------------
def ingest_file(
    user_id: str,
    filename: str,
    file_bytes: bytes,
    mime: str | None,
) -> Dict[str, Any]:
    """
    Ingest a single file for a user:
      1) Store raw bytes in Supabase Storage
      2) Insert `documents` row
      3) Chunk + embed (sanitized)
      4) Upsert into `chunks` (doc_id, chunk_index) with pgvector
    Returns:
      { doc_id, filename, bytes, pages, chunks, elapsed_ms }
    """
    supa = admin_client()
    t0 = time.time()

    # ---- 1) Upload to storage ------------------------------------------------
    storage_path, _created = upload_bytes(
        user_id=user_id,
        filename=filename,
        data=file_bytes,
        content_type=mime or "application/octet-stream",
        upsert=True,
        unique_fallback=True,
    )

    # ---- 2) Insert document row ---------------------------------------------
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
        # Clean up storage if DB insert fails
        try:
            delete_paths([storage_path])
        except Exception:
            pass
        raise RuntimeError(f"DB insert failed: {e}")

    try:
        # ---- 3) Chunking -----------------------------------------------------
        if filename.lower().endswith(".pdf"):
            chunk_pairs = _pdf_chunks(file_bytes)
        else:
            chunk_pairs = _plain_chunks(file_bytes)

        if not chunk_pairs:
            # Remove empty doc row and stored file (no useful text)
            _safe_print(f"[INGEST] WARNING: No chunks extracted from {filename}")
            supa.table("documents").delete().eq("id", doc_id).execute()
            try:
                delete_paths([storage_path])
            except Exception:
                pass

            # Provide helpful error message
            if filename.lower().endswith(".pdf"):
                raise RuntimeError(
                    "No text could be extracted from this PDF. "
                    "This usually means the PDF is scanned or image-based. "
                    "Please try a PDF with searchable text, or use a tool to convert scanned PDFs to text first."
                )
            else:
                raise RuntimeError(f"No text could be extracted from {filename}")

        pages: List[int] = [p for p, _ in chunk_pairs]
        texts: List[str] = [t for _, t in chunk_pairs]
        n = len(texts)

        # ---- 4) Embed all chunks --------------------------------------------
        _safe_print(f"[INGEST] Embedding {n} text chunks (this may take a minute for large documents)...")
        vectors = embed_texts(texts)  # np.ndarray [n, d]
        if vectors.shape[0] != n:
            raise RuntimeError(
                f"Embedding count mismatch: have {n} chunks but embed_texts returned {vectors.shape[0]} vectors"
            )
        _safe_print(f"[INGEST] Successfully created {vectors.shape[0]} embeddings")

        # ---- 5) Build rows ---------------------------------------------------
        rows = [
            {
                "doc_id": doc_id,
                "chunk_index": i,              # must match UNIQUE(doc_id, chunk_index)
                "page": pages[i],
                "text": texts[i],              # already sanitized
                "embedding": vectors[i].tolist(),  # pgvector accepts Python lists
            }
            for i in range(n)
        ]

        # ---- 6) Upsert in batches -------------------------------------------
        BATCH = 200
        _safe_print(f"[INGEST] Writing {len(rows)} chunks to database...")
        try:
            for start in range(0, len(rows), BATCH):
                end = min(start + BATCH, len(rows))
                batch = rows[start:end]
                _safe_print(f"[INGEST]   Batch {start+1}-{end} of {len(rows)}")
                (
                    supa.table("chunks")
                    .upsert(
                        batch,
                        on_conflict="doc_id,chunk_index",  # string form is most compatible
                        returning="minimal",
                    )
                    .execute()
                )
        except Exception as e:
            # If DB missing unique (42P10) OR other upsert issue → fallback to delete+insert
            msg = str(e)
            if "42P10" in msg or "no unique or exclusion constraint" in msg.lower():
                _safe_print(f"[INGEST] Falling back to delete+insert...")
                supa.table("chunks").delete().eq("doc_id", doc_id).execute()
                for start in range(0, len(rows), BATCH):
                    end = min(start + BATCH, len(rows))
                    batch = rows[start:end]
                    supa.table("chunks").insert(batch).execute()
            else:
                raise

        ms = int((time.time() - t0) * 1000)
        _safe_print(f"[INGEST] Successfully ingested '{filename}': {len(rows)} chunks in {ms/1000:.1f}s")
        return {
            "doc_id": doc_id,
            "filename": filename,
            "bytes": len(file_bytes),
            "pages": max(pages) if pages else 0,
            "chunks": len(rows),
            "elapsed_ms": ms,
        }

    except Exception as e:
        # ---- Rollback on any failure after doc insert ------------------------
        try:
            supa.table("documents").delete().eq("id", doc_id).execute()
        finally:
            try:
                delete_paths([storage_path])
            except Exception:
                pass
        raise
