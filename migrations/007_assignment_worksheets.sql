-- ============================================
-- Assignment Worksheet Support
-- Migration 007: Worksheet metadata + answers
-- ============================================

-- Worksheet metadata for each assignment project
CREATE TABLE IF NOT EXISTS worksheets (
    project_id BIGINT PRIMARY KEY REFERENCES assignment_projects(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    pdf_url TEXT NOT NULL,
    fields JSONB DEFAULT '[]'::jsonb,
    page_count INTEGER DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_worksheets_user ON worksheets(user_id);

ALTER TABLE worksheets ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view their worksheets"
    ON worksheets FOR SELECT
    USING (user_id = auth.uid());

CREATE POLICY "Users can insert their worksheets"
    ON worksheets FOR INSERT
    WITH CHECK (user_id = auth.uid());

CREATE POLICY "Users can update their worksheets"
    ON worksheets FOR UPDATE
    USING (user_id = auth.uid());

CREATE POLICY "Users can delete their worksheets"
    ON worksheets FOR DELETE
    USING (user_id = auth.uid());

-- Worksheet answers (field-by-field responses)
CREATE TABLE IF NOT EXISTS worksheet_answers (
    project_id BIGINT NOT NULL REFERENCES assignment_projects(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    field_id TEXT NOT NULL,
    answer TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (project_id, field_id)
);

CREATE INDEX IF NOT EXISTS idx_worksheet_answers_user ON worksheet_answers(user_id);

ALTER TABLE worksheet_answers ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view their worksheet answers"
    ON worksheet_answers FOR SELECT
    USING (user_id = auth.uid());

CREATE POLICY "Users can insert their worksheet answers"
    ON worksheet_answers FOR INSERT
    WITH CHECK (user_id = auth.uid());

CREATE POLICY "Users can update their worksheet answers"
    ON worksheet_answers FOR UPDATE
    USING (user_id = auth.uid());

CREATE POLICY "Users can delete their worksheet answers"
    ON worksheet_answers FOR DELETE
    USING (user_id = auth.uid());

-- Updated-at trigger helper
CREATE OR REPLACE FUNCTION touch_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_worksheets_updated_at ON worksheets;
CREATE TRIGGER trg_worksheets_updated_at
BEFORE UPDATE ON worksheets
FOR EACH ROW
EXECUTE FUNCTION touch_updated_at();

DROP TRIGGER IF EXISTS trg_worksheet_answers_updated_at ON worksheet_answers;
CREATE TRIGGER trg_worksheet_answers_updated_at
BEFORE UPDATE ON worksheet_answers
FOR EACH ROW
EXECUTE FUNCTION touch_updated_at();

