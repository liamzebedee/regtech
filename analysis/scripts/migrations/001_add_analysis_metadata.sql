-- Migration 001: Add analysis metadata columns
-- Purpose: Track document length, chunking, and analysis coverage
--
-- Run with: sqlite3 data/legislation.db < analysis/scripts/migrations/001_add_analysis_metadata.sql

-- Add column for original document length in characters
ALTER TABLE legislation ADD COLUMN document_length INTEGER;

-- Add column for analysis coverage (0.0-1.0)
-- 1.0 = fully analyzed, <1.0 = partial analysis
ALTER TABLE legislation ADD COLUMN analysis_coverage REAL DEFAULT 1.0;

-- Add column for number of chunks used in analysis
ALTER TABLE legislation ADD COLUMN analysis_chunks INTEGER DEFAULT 1;

-- Add column to indicate if document was truncated
-- 0 = fully analyzed, 1 = truncated/partial
ALTER TABLE legislation ADD COLUMN was_truncated INTEGER DEFAULT 0;

-- Update analysis_status CHECK constraint to include 'partial'
-- Note: SQLite doesn't support ALTER COLUMN, so we create a new table if needed
-- For now, we allow 'partial' as a valid status value

-- Create index for finding partially analyzed documents
CREATE INDEX IF NOT EXISTS idx_legislation_analysis_coverage ON legislation(analysis_coverage);

-- Verify the changes
SELECT
    'Columns added successfully' as status,
    (SELECT COUNT(*) FROM pragma_table_info('legislation')
     WHERE name IN ('document_length', 'analysis_coverage', 'analysis_chunks', 'was_truncated')
    ) as new_columns_count;
