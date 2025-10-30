# core/ingest_visual.py
"""
Visual content ingestion pipeline.
Extracts images from PDFs, analyzes them with vision AI, and stores them with embeddings.
"""
from __future__ import annotations

import os
import time
from typing import Any, Dict, List

from api.supa import admin_client
from api.storage import upload_bytes, delete_paths
from core.image_extractor import extract_images_from_pdf, get_image_summary
from core.vision import batch_analyze_images
from core.embeddings import embed_texts


def _safe_print(msg: str) -> None:
    """Print with fallback encoding for Windows console."""
    try:
        print(msg)
    except UnicodeEncodeError:
        safe_msg = msg.encode('ascii', errors='replace').decode('ascii')
        print(safe_msg)


def ingest_visual_content(
    doc_id: int,
    user_id: str,
    filename: str,
    pdf_bytes: bytes,
    min_images: int = 1,
    max_images: int = 50,
) -> Dict[str, Any]:
    """
    Extract and ingest visual content from a PDF.

    Args:
        doc_id: The document ID from the documents table
        user_id: User ID for storage organization
        filename: Original filename
        pdf_bytes: Raw PDF bytes
        min_images: Minimum number of images to process (skip if fewer)
        max_images: Maximum number of images to process (to avoid quota exhaustion)

    Returns:
        Dict with:
        - images_extracted: int
        - images_stored: int
        - visual_chunks_created: int
        - elapsed_ms: int
    """
    t0 = time.time()
    supa = admin_client()

    # Step 1: Extract images from PDF
    _safe_print(f"[VISUAL] Extracting images from {filename}...")
    try:
        images = extract_images_from_pdf(pdf_bytes)
    except Exception as e:
        _safe_print(f"[VISUAL] ERROR: Image extraction failed: {e}")
        return {
            "images_extracted": 0,
            "images_stored": 0,
            "visual_chunks_created": 0,
            "elapsed_ms": 0,
            "error": str(e),
        }

    if not images:
        _safe_print(f"[VISUAL] No images found in {filename}")
        return {
            "images_extracted": 0,
            "images_stored": 0,
            "visual_chunks_created": 0,
            "elapsed_ms": int((time.time() - t0) * 1000),
        }

    summary = get_image_summary(images)
    _safe_print(f"[VISUAL] Found {summary['total_images']} images across {summary['pages_with_images']} pages")

    # Apply limits
    if len(images) < min_images:
        _safe_print(f"[VISUAL] Skipping: fewer than {min_images} images")
        return {
            "images_extracted": len(images),
            "images_stored": 0,
            "visual_chunks_created": 0,
            "elapsed_ms": int((time.time() - t0) * 1000),
        }

    if len(images) > max_images:
        _safe_print(f"[VISUAL] Limiting to first {max_images} images (found {len(images)})")
        images = images[:max_images]

    # Step 2: Analyze images with vision AI
    _safe_print(f"[VISUAL] Analyzing {len(images)} images with vision AI...")
    try:
        analyzed_images = batch_analyze_images(images, pdf_bytes, filename)
    except Exception as e:
        _safe_print(f"[VISUAL] ERROR: Vision analysis failed: {e}")
        return {
            "images_extracted": len(images),
            "images_stored": 0,
            "visual_chunks_created": 0,
            "elapsed_ms": int((time.time() - t0) * 1000),
            "error": str(e),
        }

    # Step 3: Store images and create visual chunks (OPTIMIZED: batch operations)
    images_stored = 0
    visual_chunks_created = 0
    image_records = []

    # First pass: upload images to storage and prepare image records
    image_records_to_insert = []
    chunk_texts_to_embed = []
    img_to_chunk_text = {}  # Map image to its chunk text for later

    for img in analyzed_images:
        try:
            # Upload image to storage
            image_filename = f"{filename}_p{img['page']}_img{img['image_index']}.{img['format']}"
            storage_path, _ = upload_bytes(
                user_id=user_id,
                filename=f"images/{doc_id}/{image_filename}",
                data=img["image_bytes"],
                content_type=f"image/{img['format']}",
                upsert=True,
            )

            # Prepare image record
            image_record = {
                "doc_id": doc_id,
                "page": img["page"],
                "image_index": img["image_index"],
                "width": img["width"],
                "height": img["height"],
                "format": img["format"],
                "storage_path": storage_path,
                "byte_size": len(img["image_bytes"]),
                "description": img.get("description", ""),
                "caption": img.get("nearby_text", "")[:500],  # Limit caption length
                "image_type": img.get("image_type", "unknown"),
            }
            image_records_to_insert.append(image_record)

            # Prepare searchable text chunk for this image
            searchable_parts = []

            # Create explicit statement combining text and image content
            text_in_img = img.get("text_in_image", "").strip()
            description = img.get("description", "")

            # If we have both text and description, create explicit, direct connection
            if text_in_img and description:
                # Make it as direct as possible for embedding similarity
                # Extract first sentence of description which usually has the main object
                first_sentence = description.split('.')[0] if '.' in description else description
                # Create direct statement: "Text: object"
                searchable_parts.append(f"{text_in_img} {first_sentence}.")
                # Also add full description for context
                searchable_parts.append(description)
                _safe_print(f"[VISUAL] Created connection: '{text_in_img}' -> {first_sentence[:50]}...")
            elif text_in_img:
                searchable_parts.append(text_in_img)
                _safe_print(f"[VISUAL] Text only: {text_in_img[:50]}...")
            elif description:
                searchable_parts.append(description)

            # Add searchable text (if different)
            if img.get("searchable_text") and img["searchable_text"] != description:
                searchable_parts.append(img["searchable_text"])

            # Add key concepts
            if img.get("key_concepts"):
                concepts_text = "Key concepts: " + ", ".join(img["key_concepts"])
                searchable_parts.append(concepts_text)

            # Add educational value
            if img.get("educational_value"):
                searchable_parts.append(img["educational_value"])

            # Add caption/nearby text
            if img.get("caption"):
                searchable_parts.append(f"Caption: {img['caption']}")

            # Combine into searchable text
            chunk_text = " ".join(searchable_parts)
            chunk_texts_to_embed.append(chunk_text)
            img_to_chunk_text[img["page"]] = chunk_text

        except Exception as e:
            _safe_print(f"[VISUAL] WARNING: Failed to prepare image on page {img['page']}: {e}")
            continue

    # Batch insert image records
    if image_records_to_insert:
        try:
            result = supa.table("images").insert(image_records_to_insert).execute()
            if result.data:
                image_records = result.data
                images_stored = len(image_records)
                _safe_print(f"[VISUAL] Inserted {images_stored} images in batch")
            else:
                _safe_print(f"[VISUAL] WARNING: Batch image insert returned no data")
        except Exception as e:
            _safe_print(f"[VISUAL] ERROR: Batch image insert failed: {e}")

    # Batch generate embeddings
    embeddings = []
    if chunk_texts_to_embed:
        try:
            _safe_print(f"[VISUAL] Generating {len(chunk_texts_to_embed)} embeddings in batch...")
            embeddings = embed_texts(chunk_texts_to_embed)
            _safe_print(f"[VISUAL] Generated {len(embeddings)} embeddings")
        except Exception as e:
            _safe_print(f"[VISUAL] ERROR: Batch embedding failed: {e}")

    # Batch insert visual chunks
    if image_records and len(embeddings) > 0 and len(image_records) == len(embeddings):
        visual_chunks_to_insert = []
        for i, img_record in enumerate(image_records):
            visual_chunk = {
                "image_id": img_record["id"],
                "doc_id": doc_id,
                "text": chunk_texts_to_embed[i],
                "page": img_record["page"],
                "embedding": embeddings[i].tolist() if hasattr(embeddings[i], 'tolist') else embeddings[i],
            }
            visual_chunks_to_insert.append(visual_chunk)

        try:
            result = supa.table("visual_chunks").insert(visual_chunks_to_insert).execute()
            if result.data:
                visual_chunks_created = len(result.data)
                _safe_print(f"[VISUAL] Inserted {visual_chunks_created} visual chunks in batch")
        except Exception as e:
            _safe_print(f"[VISUAL] ERROR: Batch visual chunk insert failed: {e}")

    elapsed_ms = int((time.time() - t0) * 1000)
    _safe_print(f"[VISUAL] Completed: {images_stored} images stored, {visual_chunks_created} searchable chunks created in {elapsed_ms/1000:.1f}s")

    return {
        "images_extracted": len(images),
        "images_stored": images_stored,
        "visual_chunks_created": visual_chunks_created,
        "elapsed_ms": elapsed_ms,
        "image_summary": summary,
    }


def get_image_by_id(image_id: int) -> Dict[str, Any] | None:
    """Retrieve image metadata by ID."""
    supa = admin_client()
    try:
        result = supa.table("images").select("*").eq("id", image_id).limit(1).execute()
        if result.data:
            return result.data[0]
    except Exception as e:
        _safe_print(f"[VISUAL] ERROR: Failed to retrieve image {image_id}: {e}")
    return None


def get_images_for_document(doc_id: int) -> List[Dict[str, Any]]:
    """Get all images for a document."""
    supa = admin_client()
    try:
        result = supa.table("images").select("*").eq("doc_id", doc_id).order("page", desc=False).execute()
        return result.data or []
    except Exception as e:
        _safe_print(f"[VISUAL] ERROR: Failed to retrieve images for doc {doc_id}: {e}")
        return []
