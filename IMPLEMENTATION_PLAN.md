# Implementation Plan

Australian Legislation Cost Analysis - A web application to analyze and display compliance/enforcement costs of Australian legislation.

## Architecture Overview

```
analysis/          # Data acquisition and LLM analysis scripts
app/               # Next.js website (TypeScript, React)
data/              # SQLite database + HuggingFace corpus
src/lib/           # Shared utilities (cost formatting, types, db access)
```

---

## Priority 1: Foundation (No Dependencies)

### 1.1 Data Corpus Acquisition
- [x] Install/verify `hf` CLI tool and authenticate
  - Verified `hf` CLI installed at `/home/liam/.local/bin/hf`
  - Dataset is public and not gated (no auth needed)
- [x] Clone dataset `isaacus/open-australian-legal-corpus` to `data/corpus/`
  - Download complete: `corpus.jsonl` is 8.8GB, 232,560 documents
- [x] Document corpus structure (file formats, metadata fields, directory organization)
  - Format: single JSONL file with fields: version_id, type, jurisdiction, source, mime, date, citation, url, when_scraped, text
- [x] Inventory the dataset: count of documents, size, jurisdictions present
  - Document types: decision (189,216), secondary_legislation (31,696), primary_legislation (9,059), bill (2,589)
  - Jurisdictions: new_south_wales (119,587), commonwealth (103,882), queensland (3,306), tasmania (2,552), western_australia (1,564), south_australia (1,350), norfolk_island (319)
  - Note: Victoria, ACT, and Northern Territory are NOT in this corpus
- [x] Identify document format (JSON? Parquet? JSONL?) and key fields
  - Format: single JSONL file (`corpus.jsonl`)

### 1.2 Cost Model Definition
- [x] Define TypeScript types in `src/lib/types/cost.ts`:
  - `Party` type: citizen, business, small_business, large_business, government, nonprofit, other
  - `TimeUnit`, `CostFrequency` types
  - `TimeCost`, `MoneyCost` interfaces
  - `ComplianceCost`, `EnforcementCost` interfaces
  - `CostEntry` interface linking costs to legislation
  - `AnalysisStatus`, `Jurisdiction` types (updated to match corpus: snake_case jurisdictions)
  - `DocumentType` enum: decision, secondary_legislation, primary_legislation, bill
  - `Legislation` interface
- [x] Define constants in `src/lib/types/constants.ts`:
  - `MINIMUM_WAGE_HOURLY_CENTS` = 2433 ($24.33/hour, July 2024)
  - `HOURLY_WAGE_BY_PARTY` for all party types
  - `TIME_TO_HOURS` conversion factors
  - Helper functions: `timeToHours`, `calculateAssumedTimeValue`, `formatMoneyCents`, `formatTime`
  - Factory functions: `createTimeCost`, `createMoneyCost`
- [x] All 23 tests passing for cost model utilities
- [ ] Document cost categories with examples in `specs/cost-model.md` (update if needed)

---

## Priority 2: Data Layer (Depends on: Cost Model)

### 2.1 Database Schema
- [x] Create SQLite database at `data/legislation.db`
  - Schema ready, file created on first use
- [x] Design and implement `legislation` table:
  - `id` (primary key, from corpus identifier)
  - `title`, `jurisdiction`, `date_enacted`, `date_repealed`
  - `text_path` (reference to full text in corpus)
  - `text_excerpt` (first N chars for preview)
  - `topics` (JSON array of tags)
  - `analysis_status` (pending | complete | failed)
  - `created_at`, `updated_at`
- [x] Design and implement `costs` table:
  - `id`, `legislation_id` (FK)
  - `cost_type` (compliance | enforcement)
  - `party` (who bears the cost)
  - `time_hours`, `time_unit`, `time_display` (pretty format)
  - `money_aud`, `money_display` (pretty format)
  - `assumed_time_value` (calculated)
  - `is_indefinite`, `indefinite_notes`
- [x] Create indexes on: date_enacted, jurisdiction, analysis_status, cost_type, party
- [x] Write database access utilities in `src/lib/db/`
  - `schema.ts`: initializeDatabase(), types for LegislationRow, CostRow
  - `repository.ts`: LegislationRepository class with upsert, list, filter, count, costs operations
- [x] All 24 database tests passing

### 2.2 Corpus Indexing
- [x] Build script to scan corpus and populate `legislation` table with metadata
  - Created `analysis/scripts/index_corpus.py` to scan corpus and populate `legislation` table
  - Successfully indexed 40,755 legislation documents (9,059 primary + 31,696 secondary)
  - Implemented filtering to exclude court decisions (not relevant for cost analysis)
  - Records span from 1830 to 2025
  - All records have analysis_status='pending' ready for pipeline
- [ ] Implement retrieval by identifier (act name, jurisdiction, date)
- [ ] Create chunking strategy for parallel processing (e.g., by jurisdiction, by year)
- [ ] Handle edge cases: malformed text, encoding issues, duplicates

---

## Priority 3: Analysis Pipeline (Depends on: Corpus, Cost Model, Database)

### 3.1 Claude Analysis Design
- [x] Design prompt template for cost extraction in `analysis/prompts/`
  - Created `analysis/prompts/cost_extraction.md` with system prompt, output schema, guidelines, and 3 examples
- [x] Define output schema (JSON structure Claude should return)
  - Created `analysis/prompts/cost_schema.json` for response validation
- [x] Test prompt with 3-5 simple, short legislation samples
  - Tested with proclamations (no costs) and Defence Legislation Amendment (Woomera)
- [x] Iterate on prompt based on output quality
  - Successfully extracts compliance/enforcement costs, party identification, time/money costs, indefinite flags
- [ ] Document effective prompt patterns

### 3.2 Pipeline Implementation
- [x] Create `analysis/analyze.py` (or .sh) orchestrator script
  - Created `analysis/scripts/analyze_legislation.py` with Claude CLI integration
- [x] Implement work queue: select legislation where `analysis_status = 'pending'`
  - Supports filtering by jurisdiction, limit, specific ID
- [x] Implement single-document analysis function:
  - Retrieves legislation text from corpus JSONL
  - Calls Claude CLI with JSON output parsing
  - Writes to database with progress reporting
  - Updates `analysis_status`
- [ ] Implement parallelization (multiple Claude instances)
- [x] Add idempotency: skip already-analyzed documents
- [ ] Implement retry logic for failed analyses
- [x] Add logging and progress reporting

### 3.3 Analysis Quality
- [ ] Handle long documents (chunking/summarization strategy)
- [ ] Handle documents referencing other legislation
- [ ] Validate Claude outputs for consistency
- [ ] Create test suite with known-cost legislation

---

## Priority 4: Website (Depends on: Database, Cost Model)

### 4.1 Next.js Setup
- [ ] Initialize Next.js app in `app/` with TypeScript
- [ ] Configure SQLite database connection (better-sqlite3)
- [ ] Set up shared types import from `src/lib/types/`
- [ ] Design basic layout component
- [ ] Set up Tailwind or CSS modules for styling

### 4.2 Index Page
- [ ] Create `/` route listing all legislation
- [ ] Implement default sort by date
- [ ] Add filtering by:
  - Jurisdiction (dropdown)
  - Topic tags (multi-select)
  - Date range (date picker)
  - Analysis status (complete only by default)
- [ ] Add search by title/keyword
- [ ] Implement pagination (50 items per page)
- [ ] Handle empty states

### 4.3 Legislation Detail Page
- [ ] Create `/legislation/[id]` dynamic route
- [ ] Display: title, jurisdiction, dates, text excerpt
- [ ] Display compliance costs:
  - Per-party breakdown
  - Time (pretty format, e.g., "2 hours")
  - Money (pretty format, e.g., "$500")
  - Assumed time value calculation shown
- [ ] Display enforcement costs similarly
- [ ] Show indefinite cost notes where applicable
- [ ] Add "view full text" expandable section

### 4.4 Topic/Cluster Pages
- [ ] Create `/topics` index page
- [ ] Create `/topics/[topic]` page with filtered legislation
- [ ] Implement topic aggregation (total cost by topic)

### 4.5 Polish
- [ ] Responsive design (mobile-friendly)
- [ ] Accessibility audit (keyboard nav, screen readers)
- [ ] Loading states
- [ ] Error boundaries

---

## Priority 5: Integration & Testing

### 5.1 End-to-End Flow
- [ ] Verify: corpus -> analysis -> database -> website pipeline
- [ ] Run analysis on subset (100 documents)
- [ ] Test website with real data
- [ ] Performance testing (index load < 2s)

### 5.2 Documentation
- [ ] Update README with setup instructions
- [ ] Document analysis methodology
- [ ] Add sample queries for database exploration

---

## Work Log

### 2026-01-15 - Analysis Pipeline Complete

**Priority 3.1 - Claude Analysis Design:**
- Created prompt template `analysis/prompts/cost_extraction.md` with:
  - System prompt explaining the task
  - Output schema for JSON responses
  - Guidelines for cost estimation
  - 3 examples (registration requirement, burden of proof reversal, declarative legislation)
- Created JSON schema `analysis/prompts/cost_schema.json` for response validation
- Tested with sample legislation:
  - Correctly identified no costs for procedural legislation (proclamations)
  - Successfully extracted 4 compliance costs + enforcement costs from Defence Legislation Amendment (Woomera)
  - Party identification working (citizen, business)
  - Time and money costs extracted correctly
  - Indefinite cost flags working for liability exposure

**Priority 3.2 - Pipeline Implementation:**
- Created `analysis/scripts/analyze_legislation.py` orchestrator script with:
  - Retrieval of legislation text from corpus JSONL
  - Claude CLI integration with JSON output parsing
  - Database integration for saving results
  - Progress reporting and error handling
  - Support for filtering by jurisdiction, limit, specific ID

**Successfully tested analysis:**
- 7 pieces of legislation analyzed
- No errors in final run
- Cost data correctly stored in database

**Next priority:** Priority 3.3 - Analysis Quality (chunking for long documents, validation)

---

### 2026-01-15 - Corpus Indexing Complete

**Priority 2.2 - Corpus Indexing:**
- Created `analysis/scripts/index_corpus.py` to scan corpus and populate `legislation` table
- Successfully indexed 40,755 legislation documents (9,059 primary + 31,696 secondary)
- Implemented filtering to exclude court decisions (not relevant for cost analysis)
- Records span from 1830 to 2025
- All records have analysis_status='pending' ready for pipeline

**Database now contains:**
- 32,143 commonwealth (79%)
- 2,552 tasmania
- 2,216 new_south_wales
- 1,564 western_australia
- 1,067 south_australia
- 1,000 queensland
- 213 norfolk_island

**Next priority:** Priority 3 - Analysis Pipeline (need to design Claude prompts for cost extraction)

---

### 2026-01-15 (continued)

**Priority 1.1 - Data Corpus Acquisition:**
- Download completed: `corpus.jsonl` is 8.8GB, 232,560 documents
- Document format confirmed as JSONL with fields: version_id, type, jurisdiction, source, mime, date, citation, url, when_scraped, text
- Inventory completed:
  - Document types: decision (189,216), secondary_legislation (31,696), primary_legislation (9,059), bill (2,589)
  - Jurisdictions: new_south_wales (119,587), commonwealth (103,882), queensland (3,306), tasmania (2,552), western_australia (1,564), south_australia (1,350), norfolk_island (319)
  - Note: Victoria, ACT, and Northern Territory are NOT in this corpus

**Priority 1.2 - Cost Model Definition:**
- Updated types to match actual corpus format:
  - Jurisdiction type now uses snake_case (new_south_wales, commonwealth, etc.)
  - DocumentType enum added (decision, secondary_legislation, primary_legislation, bill)

**Priority 2.1 - Database Schema:**
- Created SQLite database at `data/legislation.db` (schema ready, file created on first use)
- Implemented `legislation` table with all required fields
- Implemented `costs` table with all required fields
- Created indexes on jurisdiction, date_enacted, analysis_status, cost_type, party
- Created database access utilities in `src/lib/db/`:
  - `schema.ts`: initializeDatabase(), types for LegislationRow, CostRow
  - `repository.ts`: LegislationRepository class with upsert, list, filter, count, costs operations
- All 24 database tests passing

---

### 2026-01-15 (initial)

**Priority 1.1 - Data Corpus Acquisition:**
- Verified `hf` CLI tool is installed at `/home/liam/.local/bin/hf`
- Confirmed dataset `isaacus/open-australian-legal-corpus` is public and not gated (no auth needed)
- Initiated download of `corpus.jsonl` (in progress)
- Identified document format: single JSONL file (`corpus.jsonl`)

**Priority 1.2 - Cost Model Definition:**
- Created TypeScript types in `src/lib/types/cost.ts`:
  - `Party` type with citizen, business, small_business, large_business, government, nonprofit, other
  - `TimeUnit`, `CostFrequency` types
  - `TimeCost`, `MoneyCost` interfaces
  - `ComplianceCost`, `EnforcementCost` interfaces
  - `CostEntry` interface linking costs to legislation
  - `AnalysisStatus`, `Jurisdiction` types
  - `Legislation` interface
- Created constants in `src/lib/types/constants.ts`:
  - `MINIMUM_WAGE_HOURLY_CENTS` = 2433 ($24.33/hour, July 2024)
  - `HOURLY_WAGE_BY_PARTY` for all party types
  - `TIME_TO_HOURS` conversion factors
  - Helper functions: `timeToHours`, `calculateAssumedTimeValue`, `formatMoneyCents`, `formatTime`
  - Factory functions: `createTimeCost`, `createMoneyCost`
- All 23 tests passing for cost model utilities

**Technical Setup:**
- Created `package.json` with TypeScript 5.7, Vitest 3.0
- Created `tsconfig.json` with strict mode
- TypeScript compiles without errors

---

## Notes

- **Start small**: Begin with simple, short legislation to validate the approach before scaling
- **Context management**: Keep Claude at < 50% context saturation (~64k tokens)
- **Python/Bash only**: Use only Python or Bash for analysis scripts per initial requirements
- **Self-improving loops**: Consider implementing loop.sh pattern for sustained analysis work
