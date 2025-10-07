-- Create qa_history table to store user question/answer history
CREATE TABLE IF NOT EXISTS qa_history (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    citations JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for fast user lookups
CREATE INDEX IF NOT EXISTS idx_qa_history_user_id ON qa_history(user_id);

-- Index for timestamp ordering
CREATE INDEX IF NOT EXISTS idx_qa_history_created_at ON qa_history(created_at DESC);

-- Composite index for user + timestamp queries
CREATE INDEX IF NOT EXISTS idx_qa_history_user_time ON qa_history(user_id, created_at DESC);
