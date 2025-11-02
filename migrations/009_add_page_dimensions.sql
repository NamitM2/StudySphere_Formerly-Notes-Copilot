-- Add page_dimensions column to track per-page width/height for worksheets
alter table worksheets
    add column if not exists page_dimensions jsonb;

-- Ensure bounds_version is present for existing records
update worksheets
set bounds_version = coalesce(bounds_version, 1)
where bounds_version is null;
