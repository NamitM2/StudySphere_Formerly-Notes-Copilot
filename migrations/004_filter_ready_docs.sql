-- Migration: Filter only 'ready' documents in search
-- Ensures documents still processing are not included in search results

-- Drop and recreate the search function to add status filter
DROP FUNCTION IF EXISTS search_chunks_multimodal(TEXT, vector(768), INTEGER, BOOLEAN);

CREATE OR REPLACE FUNCTION search_chunks_multimodal(
    p_user_id TEXT,
    p_query_embedding vector(768),
    p_match_count INTEGER DEFAULT 10,
    p_include_visual BOOLEAN DEFAULT TRUE
)
RETURNS TABLE (
    doc_id BIGINT,
    chunk_id BIGINT,
    filename TEXT,
    page INTEGER,
    text TEXT,
    distance FLOAT,
    content_type TEXT,
    image_id BIGINT,
    image_description TEXT,
    image_type TEXT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    WITH text_results AS (
        SELECT
            c.doc_id,
            c.id as chunk_id,
            d.filename,
            c.page,
            c.text,
            (c.embedding <=> p_query_embedding) as distance,
            'text'::TEXT as content_type,
            NULL::BIGINT as image_id,
            NULL::TEXT as image_description,
            NULL::TEXT as image_type
        FROM chunks c
        JOIN documents d ON c.doc_id = d.id
        WHERE d.user_id::text = p_user_id
          AND (d.status IS NULL OR d.status = 'ready')  -- Only search ready documents
    ),
    visual_results AS (
        SELECT
            vc.doc_id,
            vc.id as chunk_id,
            d.filename,
            vc.page,
            vc.text,
            (vc.embedding <=> p_query_embedding) as distance,
            'visual'::TEXT as content_type,
            i.id as image_id,
            i.description as image_description,
            i.image_type
        FROM visual_chunks vc
        JOIN documents d ON vc.doc_id = d.id
        JOIN images i ON vc.image_id = i.id
        WHERE d.user_id::text = p_user_id
          AND (d.status IS NULL OR d.status = 'ready')  -- Only search ready documents
          AND p_include_visual = TRUE
    ),
    combined AS (
        SELECT * FROM text_results
        UNION ALL
        SELECT * FROM visual_results
    )
    SELECT *
    FROM combined
    ORDER BY distance ASC
    LIMIT p_match_count;
END;
$$;

COMMENT ON FUNCTION search_chunks_multimodal IS 'Multimodal search across text and visual chunks, filtering only ready documents';
