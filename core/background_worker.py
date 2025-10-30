"""
Background worker for async document processing.
Uses threading to process documents without blocking the upload endpoint.
"""
import time
import threading
from queue import Queue, Empty
from typing import Dict, Any
import traceback

# Global job queue
job_queue = Queue()

# Worker thread reference
worker_thread = None


def process_document_job(job: Dict[str, Any]):
    """
    Process a single document job.

    Args:
        job: Dict with 'doc_id', 'user_id', 'filename', 'file_bytes', 'mime'
    """
    from api.supa import admin_client

    doc_id = job['doc_id']
    user_id = job['user_id']
    filename = job['filename']
    file_bytes = job['file_bytes']
    mime = job.get('mime', 'application/octet-stream')

    supa = admin_client()

    try:
        print(f"[WORKER] Starting processing: {filename} (doc_id: {doc_id})")

        # Update status to processing
        print(f"[WORKER] Updating document status to 'processing'...")
        supa.table('documents').update({
            'status': 'processing',
            'processing_started_at': 'now()'
        }).eq('id', doc_id).execute()
        print(f"[WORKER] Status updated successfully")

        # Process the document manually (ingest_file creates its own doc record, so we do it ourselves)
        from core.ingest_pg import _pdf_chunks, _plain_chunks
        from core.embeddings import embed_texts

        # Determine if PDF or plain text
        is_pdf = filename.lower().endswith('.pdf')

        print(f"[WORKER] Extracting text from PDF...")
        if is_pdf:
            chunk_pairs = _pdf_chunks(file_bytes)
        else:
            chunk_pairs = _plain_chunks(file_bytes)

        print(f"[WORKER] Extracted {len(chunk_pairs)} chunks from document")

        # If no text chunks found and it's a PDF, try visual processing
        if not chunk_pairs and is_pdf:
            from core.ingest_visual import ingest_visual_content
            visual_result = ingest_visual_content(
                doc_id=doc_id,
                user_id=user_id,
                filename=filename,
                pdf_bytes=file_bytes,
                min_images=1,
            )

            # Mark as ready
            supa.table('documents').update({
                'status': 'ready',
                'processing_completed_at': 'now()',
                'processing_error': None
            }).eq('id', doc_id).execute()

            print(f"[WORKER] Completed (visual): {filename} - {visual_result.get('images_stored', 0)} images")
            return

        # Embed and store chunks
        if chunk_pairs:
            texts_to_embed = [text for _, text in chunk_pairs]
            embeddings = embed_texts(texts_to_embed)

            # Insert chunks
            chunk_records = []
            for i, ((page, text), embedding) in enumerate(zip(chunk_pairs, embeddings)):
                chunk_records.append({
                    'doc_id': doc_id,
                    'chunk_index': i,
                    'page': page,
                    'text': text,
                    'embedding': embedding.tolist() if hasattr(embedding, 'tolist') else embedding,
                })

            supa.table('chunks').upsert(chunk_records).execute()

            print(f"[WORKER] Completed: {filename} - {len(chunk_records)} chunks")

        # Mark as ready
        supa.table('documents').update({
            'status': 'ready',
            'processing_completed_at': 'now()',
            'processing_error': None
        }).eq('id', doc_id).execute()

    except Exception as e:
        error_msg = str(e)
        print(f"[WORKER] ERROR processing {filename}: {error_msg}")
        traceback.print_exc()

        # Mark as error
        try:
            supa.table('documents').update({
                'status': 'error',
                'processing_completed_at': 'now()',
                'processing_error': error_msg[:500]  # Limit error message length
            }).eq('id', doc_id).execute()
        except Exception as update_error:
            print(f"[WORKER] Failed to update error status: {update_error}")


def background_worker():
    """
    Main worker loop. Processes jobs from the queue.
    Runs in a separate thread.
    """
    print("[WORKER] Background worker started")

    while True:
        try:
            # Wait for a job (blocking, with timeout)
            job = job_queue.get(timeout=1.0)

            # Process the job
            process_document_job(job)

            # Mark job as done
            job_queue.task_done()

        except Empty:
            # No jobs in queue, continue waiting
            continue
        except Exception as e:
            print(f"[WORKER] Unexpected error in worker loop: {e}")
            traceback.print_exc()
            time.sleep(1)  # Prevent tight loop on persistent errors


def start_worker():
    """
    Start the background worker thread.
    Should be called once at application startup.
    """
    global worker_thread

    if worker_thread is not None and worker_thread.is_alive():
        print("[WORKER] Worker already running")
        return

    worker_thread = threading.Thread(target=background_worker, daemon=True, name="DocumentWorker")
    worker_thread.start()
    print("[WORKER] Background worker thread started")


def enqueue_document(doc_id: int, user_id: str, filename: str, file_bytes: bytes, mime: str = None):
    """
    Add a document to the processing queue.

    Args:
        doc_id: Document ID
        user_id: User ID
        filename: Original filename
        file_bytes: PDF file bytes
        mime: MIME type
    """
    job = {
        'doc_id': doc_id,
        'user_id': user_id,
        'filename': filename,
        'file_bytes': file_bytes,
        'mime': mime or 'application/octet-stream',
    }

    job_queue.put(job)
    print(f"[WORKER] Queued: {filename} (doc_id: {doc_id}), queue size: {job_queue.qsize()}")


def get_queue_size() -> int:
    """Get current number of jobs in queue."""
    return job_queue.qsize()
