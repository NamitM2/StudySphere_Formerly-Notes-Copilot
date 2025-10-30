-- Migration: Add async processing support
-- Add status tracking for background document processing

-- Add status column to documents table
ALTER TABLE documents
ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'ready';

-- Add processing metadata
ALTER TABLE documents
ADD COLUMN IF NOT EXISTS processing_started_at TIMESTAMP,
ADD COLUMN IF NOT EXISTS processing_completed_at TIMESTAMP,
ADD COLUMN IF NOT EXISTS processing_error TEXT;

-- Create index for efficient status queries
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
CREATE INDEX IF NOT EXISTS idx_documents_user_status ON documents(user_id, status);

-- Status values:
-- 'processing' - Document is being processed in background
-- 'ready' - Document is ready to be queried
-- 'error' - Processing failed

COMMENT ON COLUMN documents.status IS 'Processing status: processing, ready, error';
COMMENT ON COLUMN documents.processing_started_at IS 'When background processing started';
COMMENT ON COLUMN documents.processing_completed_at IS 'When processing completed successfully';
COMMENT ON COLUMN documents.processing_error IS 'Error message if processing failed';
