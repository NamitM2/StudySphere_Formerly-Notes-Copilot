-- ============================================
-- Assignment IDE Tables
-- Migration 005: Core IDE functionality
-- ============================================

-- Assignment Projects (the main IDE workspace)
CREATE TABLE IF NOT EXISTS assignment_projects (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,

    -- Assignment Details
    title TEXT NOT NULL,
    assignment_prompt TEXT,
    assignment_type TEXT NOT NULL,
    subject_area TEXT,

    -- Template Info
    template_file_id BIGINT REFERENCES documents(id),
    has_template BOOLEAN DEFAULT FALSE,

    -- Workspace Structure
    workspace_structure JSONB,
    current_content TEXT DEFAULT '',

    -- AI Context
    ai_instructions TEXT,
    rubric JSONB,
    key_requirements TEXT[],

    -- Progress Tracking
    status TEXT DEFAULT 'in_progress',
    progress_percentage INTEGER DEFAULT 0,
    word_count INTEGER DEFAULT 0,
    ai_contribution_percentage INTEGER DEFAULT 0,

    -- Metadata
    due_date TIMESTAMPTZ,
    estimated_time_minutes INTEGER,
    actual_time_minutes INTEGER DEFAULT 0,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    last_edited_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_assignment_projects_user_id ON assignment_projects(user_id);
CREATE INDEX idx_assignment_projects_status ON assignment_projects(status);
CREATE INDEX idx_assignment_projects_type ON assignment_projects(assignment_type);

ALTER TABLE assignment_projects ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own projects"
    ON assignment_projects FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own projects"
    ON assignment_projects FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own projects"
    ON assignment_projects FOR UPDATE
    USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own projects"
    ON assignment_projects FOR DELETE
    USING (auth.uid() = user_id);

-- AI Interactions
CREATE TABLE IF NOT EXISTS ide_ai_interactions (
    id BIGSERIAL PRIMARY KEY,
    project_id BIGINT NOT NULL REFERENCES assignment_projects(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,

    -- Interaction Details
    interaction_type TEXT NOT NULL,
    user_input TEXT,
    ai_output TEXT,

    -- Context
    cursor_position INTEGER,
    surrounding_context TEXT,
    section_working_on TEXT,

    -- User Action
    user_action TEXT,
    final_text TEXT,

    -- Metrics
    tokens_used INTEGER,
    latency_ms INTEGER,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_ide_interactions_project ON ide_ai_interactions(project_id, created_at);
CREATE INDEX idx_ide_interactions_type ON ide_ai_interactions(interaction_type);

ALTER TABLE ide_ai_interactions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view interactions for own projects"
    ON ide_ai_interactions FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert interactions for own projects"
    ON ide_ai_interactions FOR INSERT
    WITH CHECK (auth.uid() = user_id);

-- Project Versions
CREATE TABLE IF NOT EXISTS project_versions (
    id BIGSERIAL PRIMARY KEY,
    project_id BIGINT NOT NULL REFERENCES assignment_projects(id) ON DELETE CASCADE,

    -- Version Info
    version_number INTEGER NOT NULL,
    content TEXT NOT NULL,
    word_count INTEGER,

    -- Change Summary
    change_description TEXT,
    is_autosave BOOLEAN DEFAULT TRUE,
    is_milestone BOOLEAN DEFAULT FALSE,

    -- Timestamp
    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(project_id, version_number)
);

CREATE INDEX idx_project_versions_project ON project_versions(project_id, version_number DESC);

ALTER TABLE project_versions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view versions of own projects"
    ON project_versions FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM assignment_projects
            WHERE assignment_projects.id = project_versions.project_id
            AND assignment_projects.user_id = auth.uid()
        )
    );

CREATE POLICY "Users can insert versions for own projects"
    ON project_versions FOR INSERT
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM assignment_projects
            WHERE assignment_projects.id = project_versions.project_id
            AND assignment_projects.user_id = auth.uid()
        )
    );
