-- ============================================
-- Add bounds_version column to worksheets
-- Migration 008: Support for coordinate normalization versioning
-- ============================================

-- Add bounds_version column to track coordinate format version
ALTER TABLE worksheets ADD COLUMN IF NOT EXISTS bounds_version INTEGER DEFAULT 1;

-- Update existing worksheets to version 1 (old absolute coordinates)
-- New worksheets with normalized coordinates will be version 2
UPDATE worksheets SET bounds_version = 1 WHERE bounds_version IS NULL;
