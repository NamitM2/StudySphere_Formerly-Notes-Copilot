# Supabase Storage Setup

## Storage Buckets Required

### 1. `worksheets` Bucket (for PDF worksheets with AI field detection)
- **Purpose**: Store PDF worksheets that students fill out in the assignments IDE
- **Public**: Yes (students need to access PDFs via public URLs)
- **File Type**: PDF only
- **Path Structure**: `{user_id}/worksheets/{project_id}/{filename}.pdf`

### 2. `assignments` Bucket (for student PDF submissions)
- **Purpose**: Store student-uploaded PDFs for assignment submissions
- **Public**: No (private submissions, access controlled by RLS)
- **File Type**: PDF primarily, but can support other document types
- **Path Structure**: `{user_id}/assignments/{project_id}/{filename}.pdf`

## Setup Instructions

### Step 1: Create Buckets in Supabase Dashboard

1. Go to your Supabase project dashboard
2. Navigate to **Storage** in the left sidebar
3. Click **New Bucket**

**For `worksheets` bucket:**
- Name: `worksheets`
- Public bucket: ✅ **Enable**
- File size limit: 50 MB (or as needed)
- Allowed MIME types: `application/pdf`

**For `assignments` bucket:**
- Name: `assignments`
- Public bucket: ❌ **Disable**
- File size limit: 50 MB (or as needed)
- Allowed MIME types: `application/pdf, image/png, image/jpeg` (flexible for screenshots)

### Step 2: Set Up Row Level Security (RLS) Policies

#### For `worksheets` bucket:
Since this is public, minimal RLS needed. Users should only be able to upload to their own folder.

```sql
-- Allow authenticated users to upload to their own folder
CREATE POLICY "Users can upload worksheets to their own folder"
ON storage.objects FOR INSERT
TO authenticated
WITH CHECK (
  bucket_id = 'worksheets'
  AND (storage.foldername(name))[1] = auth.uid()::text
);

-- Allow authenticated users to read their own worksheets
CREATE POLICY "Users can read their own worksheets"
ON storage.objects FOR SELECT
TO authenticated
USING (
  bucket_id = 'worksheets'
  AND (storage.foldername(name))[1] = auth.uid()::text
);

-- Allow authenticated users to delete their own worksheets
CREATE POLICY "Users can delete their own worksheets"
ON storage.objects FOR DELETE
TO authenticated
USING (
  bucket_id = 'worksheets'
  AND (storage.foldername(name))[1] = auth.uid()::text
);
```

#### For `assignments` bucket:
Private bucket with strict access control.

```sql
-- Allow authenticated users to upload assignments to their own folder
CREATE POLICY "Users can upload assignments to their own folder"
ON storage.objects FOR INSERT
TO authenticated
WITH CHECK (
  bucket_id = 'assignments'
  AND (storage.foldername(name))[1] = auth.uid()::text
);

-- Allow authenticated users to read their own assignments
CREATE POLICY "Users can read their own assignments"
ON storage.objects FOR SELECT
TO authenticated
USING (
  bucket_id = 'assignments'
  AND (storage.foldername(name))[1] = auth.uid()::text
);

-- Allow authenticated users to update their own assignments
CREATE POLICY "Users can update their own assignments"
ON storage.objects FOR UPDATE
TO authenticated
USING (
  bucket_id = 'assignments'
  AND (storage.foldername(name))[1] = auth.uid()::text
);

-- Allow authenticated users to delete their own assignments
CREATE POLICY "Users can delete their own assignments"
ON storage.objects FOR DELETE
TO authenticated
USING (
  bucket_id = 'assignments'
  AND (storage.foldername(name))[1] = auth.uid()::text
);
```

### Step 3: Database Tables (if not already created)

The `worksheets` table should already exist. For assignment submissions, ensure you have proper tables:

```sql
-- Assignment submissions table
CREATE TABLE IF NOT EXISTS assignment_submissions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id TEXT NOT NULL,
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  file_url TEXT NOT NULL,
  filename TEXT NOT NULL,
  file_size BIGINT,
  mime_type TEXT,
  submitted_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),

  UNIQUE(project_id, user_id)
);

-- RLS policies for submissions
ALTER TABLE assignment_submissions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can read their own submissions"
ON assignment_submissions FOR SELECT
TO authenticated
USING (user_id = auth.uid());

CREATE POLICY "Users can insert their own submissions"
ON assignment_submissions FOR INSERT
TO authenticated
WITH CHECK (user_id = auth.uid());

CREATE POLICY "Users can update their own submissions"
ON assignment_submissions FOR UPDATE
TO authenticated
USING (user_id = auth.uid());

CREATE POLICY "Users can delete their own submissions"
ON assignment_submissions FOR DELETE
TO authenticated
USING (user_id = auth.uid());
```

## Environment Variables

Make sure these are set in your `.env` file:

```bash
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
SUPABASE_ANON_KEY=your-anon-key  # For frontend
```

## Testing

After setup, test with:

```bash
# Backend test (from api/ directory)
python -c "from api.db import get_repo; repo = get_repo(); print('✓ Repo connected')"

# Storage test
python -c "from api.supa import admin_client; client = admin_client(); print('✓ Storage client ready')"
```

## Troubleshooting

**Issue**: "Row Level Security policy violation"
- **Solution**: Make sure RLS policies are created and enabled on both storage.objects and your tables

**Issue**: "Bucket not found"
- **Solution**: Double-check bucket names match exactly (case-sensitive)

**Issue**: "403 Forbidden on file upload"
- **Solution**: Verify the service role key is correct and has admin privileges
