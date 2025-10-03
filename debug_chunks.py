#!/usr/bin/env python3
"""
Debug script to check PDF chunking and database storage.
Run this to see what's actually being stored in your database.
"""

import os
import sys
from pathlib import Path

# Add the current directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

from core.ingest_pg import _pdf_chunks, _split_by_sections
from core.chunk import split_text


def debug_pdf_chunking(pdf_path):
    """Debug PDF chunking process."""
    print(f"Debugging PDF chunking for: {pdf_path}")

    # Read PDF file
    with open(pdf_path, 'rb') as f:
        pdf_bytes = f.read()

    print(f"PDF file size: {len(pdf_bytes)} bytes")

    # Test chunking
    chunks = _pdf_chunks(pdf_bytes, chunk_chars=360, overlap=90)

    print(f"\nTotal chunks created: {len(chunks)}")

    for i, (page, chunk) in enumerate(chunks):
        print(f"\nChunk {i+1} (Page {page}):")
        print(f"Length: {len(chunk)} chars")
        print(f"Preview: {chunk[:200]}...")
        print("-" * 50)

    return chunks


def check_database_contents():
    """Check what's actually in the database."""
    try:
        from api.supa import admin_client

        supa = admin_client()

        # Get all documents
        docs = supa.table("documents").select("*").limit(10).execute()
        print(f"\nDocuments in database: {len(docs.data)}")

        for doc in docs.data:
            print(f"\nDocument: {doc['filename']} (ID: {doc['id']})")

            # Get chunks for this document
            chunks = supa.table("chunks").select("id, page, text").eq("doc_id", doc['id']).execute()

            print(f"  Chunks: {len(chunks.data)}")

            for chunk in chunks.data[:5]:  # Show first 5 chunks
                print(f"    Page {chunk['page']}: {chunk['text'][:100]}...")

            if len(chunks.data) > 5:
                print(f"    ... and {len(chunks.data) - 5} more chunks")

        # Check embedding dimensions in database
        print(f"\n{'='*50}")
        print("Checking embedding vector dimensions...")
        try:
            # Get one chunk with embedding to check dimensions
            sample_chunk = supa.table("chunks").select("embedding").limit(1).execute()
            if sample_chunk.data:
                embedding = sample_chunk.data[0]['embedding']
                if embedding:
                    print(f"Sample embedding dimensions: {len(embedding)}")
                    print(f"Sample embedding preview: {embedding[:5]}...")
                else:
                    print("Sample chunk has null embedding")
            else:
                print("No chunks found with embeddings")
        except Exception as e:
            print(f"Error checking embeddings: {e}")

    except Exception as e:
        print(f"Database check failed: {e}")


if __name__ == "__main__":
    # Check if PDF path is provided
    if len(sys.argv) > 1:
        pdf_path = sys.argv[1]
        if os.path.exists(pdf_path):
            debug_pdf_chunking(pdf_path)
        else:
            print(f"PDF file not found: {pdf_path}")
    else:
        print("Usage: python debug_chunks.py <path_to_pdf>")
        print("Or run without arguments to check database contents")

    # Always check database
    print("\n" + "="*50)
    check_database_contents()
