-- ============================================
-- Assignment Folders
-- Migration 006: Folder organization for assignments
-- ============================================

-- Assignment Folders
CREATE TABLE IF NOT EXISTS assignment_folders (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,

    -- Folder Details
    name TEXT NOT NULL,
    color TEXT DEFAULT 'teal',
    icon TEXT DEFAULT 'folder',

    -- Hierarchy
    parent_folder_id BIGINT REFERENCES assignment_folders(id) ON DELETE CASCADE,
    position INTEGER DEFAULT 0,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_assignment_folders_user ON assignment_folders(user_id);
CREATE INDEX idx_assignment_folders_parent ON assignment_folders(parent_folder_id);

ALTER TABLE assignment_folders ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own folders"
    ON assignment_folders FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own folders"
    ON assignment_folders FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own folders"
    ON assignment_folders FOR UPDATE
    USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own folders"
    ON assignment_folders FOR DELETE
    USING (auth.uid() = user_id);

-- Add folder_id to assignment_projects
ALTER TABLE assignment_projects
ADD COLUMN IF NOT EXISTS folder_id BIGINT REFERENCES assignment_folders(id) ON DELETE SET NULL;

CREATE INDEX idx_assignment_projects_folder ON assignment_projects(folder_id);
