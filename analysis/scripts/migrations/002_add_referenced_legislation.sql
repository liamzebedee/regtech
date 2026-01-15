-- Migration: Add referenced_legislation column to legislation table
--
-- WHY: Many pieces of legislation reference other legislation (Acts, Regulations)
-- for definitions, requirements, penalties, or amendments. Tracking these references
-- enables:
-- 1. Identifying legislation with incomplete analysis (depends on external references)
-- 2. Building a dependency graph between legislation
-- 3. Flagging when referenced legislation hasn't been analyzed yet
--
-- The column stores a JSON array of referenced legislation objects with:
-- - title: Name of the referenced Act/Regulation
-- - section: Optional specific section reference (e.g., "Section 4", "Schedule 1")
-- - reference_type: "definition" | "requirement" | "amendment" | "penalty"

ALTER TABLE legislation ADD COLUMN referenced_legislation TEXT DEFAULT '[]';
