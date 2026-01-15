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
- [x] Document cost categories with examples in `specs/cost-model.md` (update if needed)

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
- [x] Implement retrieval by identifier (act name, jurisdiction, date)
  - Added date range filtering (dateFrom, dateTo) to listLegislation and countLegislation methods, with 5 new tests
- [x] Create chunking strategy for parallel processing
  - Created corpus byte-offset index for O(1) lookups (analysis/scripts/build_corpus_index.py). Index maps version_id -> byte offset, enabling direct seek instead of linear scan. Index size: 2.4MB for 43,344 legislation records.
- [x] Handle edge cases: malformed text, encoding issues, duplicates
  - **Investigation findings** (corpus analysis of 232,560 records):
    - Malformed JSON: 0 (corpus is clean)
    - Empty text: 0
    - Short text (<100 chars): 3 (valid legislation)
    - Encoding issues: 2 documents with 3 total replacement characters
    - Duplicate version_ids: 0
    - Duplicate citations: 72 (expected - different versions of same act)
  - **Implemented cleanup_text() function**:
    - Removes Unicode replacement characters (\ufffd)
    - Normalizes line endings
    - Removes null bytes
    - Collapses excessive whitespace
    - Skips documents with <50 chars after cleanup

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
- [x] Implement parallelization (multiple Claude instances)
  - Added `--workers N` flag for parallel processing
  - Uses Python multiprocessing.Pool for concurrent analysis
  - Each worker has its own SQLite connection with 30s timeout for locking
  - Workers pre-load corpus index for O(1) lookups
  - Backwards compatible: `--workers 1` (default) uses sequential mode
- [x] Add idempotency: skip already-analyzed documents
- [x] Implement retry logic for failed analyses
- [x] Add logging and progress reporting

### 3.3 Analysis Quality
- [ ] Handle long documents (chunking/summarization strategy)
- [ ] Handle documents referencing other legislation
- [x] Validate Claude outputs for consistency
- [x] Create test suite with known-cost legislation
  - Created `analysis/tests/test_cases.json` with 6 test cases:
    - Proclamations (no costs expected)
    - Defence Legislation Amendment (compliance + enforcement costs)
    - Employment Agents Registration Act (business compliance)
    - Human Reproductive Technology regulations (licensing)
  - Created `analysis/tests/validate_analysis.py` validation script:
    - Validates analysis output against expected outcomes
    - Checks compliance costs, enforcement costs, parties, indefinite costs
    - Usage: `python analysis/tests/validate_analysis.py [--run-analysis] [--verbose]`

---

## Priority 4: Website (Depends on: Database, Cost Model)

### 4.1 Next.js Setup
- [x] Initialize Next.js app in `app/` with TypeScript
  - Created Next.js 15 app with App Router
  - Configured TypeScript strict mode
- [x] Configure SQLite database connection (better-sqlite3)
  - Created `app/src/lib/db.ts` with singleton database connection
  - Database opened in read-only mode for web app
- [x] Set up shared types import from `src/lib/types/`
  - Types defined locally in db.ts (LegislationRow, CostRow)
- [x] Design basic layout component
  - Created `app/src/app/layout.tsx` with header, footer, navigation
- [x] Set up Tailwind or CSS modules for styling
  - Tailwind CSS 4 with @tailwindcss/postcss configured

### 4.2 Index Page
- [x] Create `/` route listing all legislation
  - `app/src/app/page.tsx` with server-side data fetching
- [x] Implement default sort by date
  - Sorted by date_enacted DESC
- [x] Add filtering by:
  - Jurisdiction (dropdown) - implemented
  - ~~Topic tags (multi-select)~~ - deferred
  - ~~Date range (date picker)~~ - deferred
  - Analysis status (complete only by default) - implemented
- [x] Add search by title/keyword
- [x] Implement pagination (50 items per page)
- [x] Handle empty states

### 4.3 Legislation Detail Page
- [x] Create `/legislation/[id]` dynamic route
  - `app/src/app/legislation/[id]/page.tsx`
- [x] Display: title, jurisdiction, dates, text excerpt
- [x] Display compliance costs:
  - Per-party breakdown
  - Time (pretty format, e.g., "2 hours")
  - Money (pretty format, e.g., "$500")
  - Assumed time value calculation shown
- [x] Display enforcement costs similarly
- [x] Show indefinite cost notes where applicable
- [x] Add "view full text" expandable section

### 4.4 Topic/Cluster Pages
- [x] Create `/topics` index page
- [x] Create `/topics/[topic]` page with filtered legislation
- [x] Implement topic aggregation (total cost by topic)

### 4.5 Polish
- [x] Responsive design (mobile-friendly)
- [x] Accessibility audit (keyboard nav, screen readers)
- [x] Loading states
- [x] Error boundaries

---

## Priority 5: Integration & Testing

### 5.1 End-to-End Flow
- [x] Verify: corpus -> analysis -> database -> website pipeline
- [ ] Run analysis on subset (100 documents) - requires Claude CLI
- [x] Test website with real data
- [x] Performance testing (index load < 2s) - actual: < 0.1s

### 5.2 Documentation
- [x] Update README with setup instructions
- [ ] Document analysis methodology
- [x] Add sample queries for database exploration
  - Expanded README.md sample queries section with 9 practical SQL examples:
    - Database status overview, high compliance costs, jurisdiction totals
    - Costs by party type, indefinite costs, topic-based filtering
    - Recent legislation, costs with both time and money, specific legislation lookup

---

## Work Log

### 2026-01-16 - Test Suite for Known-Cost Legislation (Priority 3.3)

**WHY:** Without ground truth validation, we can't measure analysis quality. The test suite provides known-cost legislation examples to validate the pipeline produces accurate results.

**Changes:**
- Created `analysis/tests/test_cases.json` with 6 test cases:
  - 2 proclamations (expected: no costs)
  - Defence Legislation Amendment (expected: business + citizen compliance, enforcement)
  - Local Government Order (expected: enforcement)
  - Employment Agents Registration Act (expected: business compliance)
  - Human Reproductive Technology regulations (expected: business compliance)
- Created `analysis/tests/validate_analysis.py` validation script
  - Validates has_compliance_costs, has_enforcement_costs
  - Validates min/max cost counts, expected parties
  - Validates indefinite cost flags
  - Usage: `python analysis/tests/validate_analysis.py [--run-analysis] [--verbose]`

**Test Results (on existing data):**
- 3/6 passing (analyzed legislation matches expectations)
- 3/6 pending (need Claude CLI to analyze)

**Files Created:**
- `analysis/tests/test_cases.json`
- `analysis/tests/validate_analysis.py`

---

### 2026-01-16 - Edge Case Handling Complete (Priority 2.2)

**WHY:** Before running large-scale analysis on 40,000+ documents, edge cases need to be handled to prevent failures and ensure data quality.

**Investigation Results (232,560 corpus records):**
- Malformed JSON: 0 (corpus is clean)
- Empty text: 0
- Short text (<100 chars): 3 (valid legislation)
- Encoding issues: 2 documents with 3 total replacement characters
- Duplicate version_ids: 0
- Duplicate citations: 72 (expected - different versions of same act)

**Changes:**
- Added `cleanup_text()` function to `analysis/scripts/analyze_legislation.py`
- Removes Unicode replacement characters, normalizes line endings, removes null bytes
- Skips documents with <50 chars after cleanup
- Integrated cleanup into both worker and sequential processing paths

**Files Modified:**
- `analysis/scripts/analyze_legislation.py` - added cleanup_text() and integration

---

### 2026-01-16 - Analysis Pipeline Parallelization Complete (Priority 3.2)

**WHY:** With 40,000+ pending legislation records, sequential analysis would take weeks. Parallelization enables multiple Claude instances to analyze different legislation simultaneously, dramatically reducing total analysis time.

**Changes:**
- Added `--workers N` flag to `analysis/scripts/analyze_legislation.py` (default: 1)
- Implemented Python multiprocessing.Pool for concurrent processing
- Each worker process has its own SQLite connection with 30-second timeout for lock handling
- Workers pre-load the corpus byte-offset index for O(1) lookups
- Added WorkerConfig dataclass for passing configuration to worker processes
- Added worker_init() and worker_process_item() functions for multiprocessing compatibility
- Backwards compatible: `--workers 1` uses original sequential mode

**Usage:**
```bash
# Analyze 100 documents using 4 parallel workers
python analysis/scripts/analyze_legislation.py --limit 100 --workers 4
```

**Files Modified:**
- `analysis/scripts/analyze_legislation.py` - added parallelization support

---

### 2026-01-16 - Corpus Indexing and Date Range Filtering Complete

**WHY:** The analysis pipeline was severely bottlenecked by linear scans through an 8.8GB corpus file. By creating a byte-offset index, legislation lookups now run in constant time (~0.24ms) instead of potentially minutes. Date range filtering enables refined legislation discovery for the website.

**Byte-Offset Index (Priority 2.2):**
- Created `analysis/scripts/build_corpus_index.py` to scan corpus.jsonl and build index
- Index maps version_id -> byte offset for O(1) random access
- Index size: 2.4MB for 43,344 legislation records (12.7x compression vs full corpus)
- Updated `analysis/scripts/analyze_legislation.py` to use index via `load_corpus_index()` and `get_legislation_text()` - seeks directly to byte offset instead of linear scan
- Performance: lookup time reduced from potentially minutes (worst case: full scan of 8.8GB) to ~0.24ms average

**Date Range Filtering (Priority 2.2):**
- Added `dateFrom` and `dateTo` parameters to `listLegislation()` and `countLegislation()` in `app/src/lib/db/repository.ts`
- Enables filtering legislation by enacted date range on website
- Added 5 new tests for date range filtering (52 total tests now)

**Files Modified:**
- `analysis/scripts/analyze_legislation.py` - integrated byte-offset index lookups
- `app/src/lib/db/repository.ts` - added date range filtering

**Files Created:**
- `analysis/scripts/build_corpus_index.py` - corpus indexing script

---

### 2026-01-16 - README, Retry Logic, and Validation Complete

**README.md Created:**
- Project overview and architecture
- Prerequisites (Node.js, Python, Claude CLI, Hugging Face CLI)
- Quick start guide with numbered steps
- Project structure documentation
- Tests and database queries sections
- Corpus details and cost model summary

**Retry Logic Implemented (Priority 3.2):**
- `RetryableError` and `NonRetryableError` exception classes
- `analyze_with_retry()` function with exponential backoff (2, 4, 8 seconds)
- `--retries` flag to configure max attempts (default: 3)
- `--retry-failed` flag to re-analyze failed legislation
- Distinguishes transient errors (timeout, rate limit) from permanent errors

**Output Validation Implemented (Priority 3.3):**
- `validate_analysis()` function validates Claude responses
- Checks required fields, party enums, frequency enums, time units, numeric amounts
- Validation warnings logged but don't block saving (for data quality tracking)

**Files Modified:**
- `analysis/scripts/analyze_legislation.py` - added retry logic and validation
- `README.md` - created with comprehensive documentation

---

### 2026-01-16 - End-to-End Flow Verified (Priority 5.1)

**WHY:** Before scaling the analysis pipeline, the complete data flow must be validated to ensure each component integrates correctly. This prevents wasted effort analyzing thousands of documents only to discover integration issues.

**Verification Results:**
- Corpus -> Analysis -> Database pipeline: 7 legislation items successfully analyzed with cost extraction
- Database -> Website display: All cost types (compliance/enforcement), parties (citizen/business), time/money values, and indefinite cost notes render correctly
- Performance: Index page loads in < 0.1s (requirement: < 2s)
- Topics page shows "No topics found" because existing 7 analyzed items predate topic extraction - this is expected and documented

**Current Database State:**
- 40,755 legislation records (9,059 primary + 31,696 secondary)
- 7 completed analyses with cost data
- 40,748 pending analysis

**Remaining:**
- Run analysis on 100+ documents to validate at scale (requires Claude CLI)
- Documentation (README, methodology)

---

### 2026-01-16 - Responsive Design and Accessibility Complete (Priority 4.5)

**WHY:** The website spec requires a responsive, mobile-friendly design and accessibility for screen readers and keyboard navigation. These are essential for inclusive user experience and modern web standards compliance.

**Responsive Design Changes:**
- Created `app/src/components/MobileNav.tsx` - hamburger menu navigation drawer for mobile screens
- Added responsive breakpoints throughout: typography scales (`text-xl sm:text-2xl`), padding (`p-3 sm:p-4`), grid columns (`grid-cols-1 sm:grid-cols-2 md:grid-cols-4`)
- Header uses desktop nav (hidden on mobile) + mobile nav hamburger (hidden on desktop)
- Pagination stacks vertically on mobile, horizontal on desktop
- Form inputs full-width on mobile, constrained on larger screens

**Accessibility Changes:**
- Added skip-to-main-content link for keyboard users (visible on focus)
- Added form labels (visually hidden but available to screen readers)
- Added ARIA attributes throughout: `aria-label`, `aria-labelledby`, `aria-live`, `aria-expanded`, `aria-controls`, `aria-current`, `role`
- Added focus-visible ring styling for keyboard navigation feedback
- Added reduced-motion media query support
- Added minimum touch target sizing (44px) for touch devices
- Updated ExpandableText component with `aria-expanded` and `aria-controls`
- Used semantic HTML elements: `<nav>`, `<article>`, `<section>`, `<time>`, `<ul>`/`<li>`

**Files Modified:**
- `app/src/app/layout.tsx` - skip link, mobile nav, focus styling
- `app/src/app/globals.css` - sr-only, focus-visible, touch targets, reduced motion
- `app/src/app/page.tsx` - form labels, ARIA attributes, responsive design
- `app/src/app/topics/page.tsx` - ARIA attributes, responsive design
- `app/src/app/topics/[topic]/page.tsx` - ARIA attributes, responsive design
- `app/src/app/legislation/[id]/page.tsx` - ARIA attributes, responsive design
- `app/src/components/ExpandableText.tsx` - aria-expanded, aria-controls, focus styling

**Files Created:**
- `app/src/components/MobileNav.tsx` - mobile navigation drawer component

**Build Status:**
- All 47 root tests passing
- Production build successful with no ESLint warnings

---

### 2026-01-15 - Loading States and Error Boundaries Added (Priority 4.5)

**WHY:** Production apps need graceful error handling and loading feedback. Without these, errors crash the entire page and users see blank screens during loads.

**Changes:**
- Created `app/src/app/error.tsx` - global error boundary with retry button and dev-only stack trace
- Created `app/src/app/loading.tsx` - loading spinner shown during server component loading

**Features:**
- Error boundary catches React errors, shows user-friendly message
- Retry button allows recovery without page refresh
- Loading state provides immediate visual feedback during navigation

---

### 2026-01-15 - Expandable Text Section Added

**WHY:** Legislation text can be thousands of lines long. Showing full text on page load would hurt performance and user experience. An expandable section shows a preview first and expands on demand.

**Changes:**
- Created `app/src/components/ExpandableText.tsx` client component
- Updated legislation detail page to use ExpandableText
- Shows first 30 lines with gradient fade, "Show all X lines" button
- Includes link to official source for full canonical text

**Also fixed:** Database path resolution for Next.js RSC environment - switched from `__dirname` to `process.cwd()` based detection.

---

### 2026-01-15 - Topic/Cluster Pages Complete (Priority 4.4)

**WHY:** The website spec requires browsing legislation by topic. Topic pages enable users to explore subject areas (e.g., all taxation legislation) and see cumulative costs in that domain.

**Changes:**
- Created `/topics` index page showing all topics with counts, grouped by category
- Created `/topics/[topic]` detail page with legislation filtered by topic
- Implemented topic aggregation: total compliance costs, enforcement costs, and parties affected
- Added `dynamic = "force-dynamic"` to topic pages since they require database access

**Files Created:**
- `app/src/app/topics/page.tsx` - Topics index page
- `app/src/app/topics/[topic]/page.tsx` - Topic detail page

**Features:**
- Topics grouped into categories (Business, Environment, Social, Safety, Legal, Other)
- Statistics panel showing legislation count, total costs, parties affected
- Pagination for topics with many entries
- Empty state with instructions when no topics exist

**Note:** Topics pages show "No topics found" until legislation is analyzed with the new prompt that extracts topics. Re-run analysis to populate topics.

---

### 2026-01-15 - Topics Extraction Added to Analysis Pipeline

**WHY:** The website spec requires topic/cluster pages for browsing legislation by topic, but the analysis pipeline wasn't extracting topics. Without topic data, topic pages would be empty. This change enables future topic pages and makes the data more useful for filtering and aggregation.

**Changes:**
- Updated `analysis/prompts/cost_extraction.md` to request 2-5 topic tags per legislation
- Added predefined topic vocabulary (taxation, environmental, workplace-safety, etc.)
- Updated `analysis/prompts/cost_schema.json` to require topics array in response
- Updated `analysis/scripts/analyze_legislation.py` to save topics to database
- Topics are saved as JSON array in the `legislation.topics` column

**Topic categories available:**
- Business: `taxation`, `business-registration`, `financial-services`, `licensing`, `trade`, `insurance`
- Environment: `environmental`, `agriculture`, `mining`, `energy`, `land-use`
- Social: `healthcare`, `education`, `public-health`, `employment`, `civil-rights`
- Safety: `workplace-safety`, `food-safety`, `consumer-protection`, `transport`, `construction`
- Legal: `criminal-justice`, `privacy`, `corporate-governance`, `competition`, `intellectual-property`

**Impact:** Re-running analysis on legislation will now populate topics. Existing 7 analyzed records have empty topics - they would need re-analysis to get topics.

**Next priority:** Implement Topic/Cluster Pages (Priority 4.4) now that topic data will be available.

---

### 2026-01-15 - Website Foundation Complete

**Priority 4.1 - Next.js Setup:**
- Initialized Next.js 15 app in `app/` directory with App Router
- Configured TypeScript with strict mode
- Set up Tailwind CSS 4 with @tailwindcss/postcss
- Created database connection in `app/src/lib/db.ts` using better-sqlite3
- Created root layout with navigation header and footer

**Priority 4.2 - Index Page:**
- Created index page at `app/src/app/page.tsx`
- Implemented legislation listing with server-side data fetching
- Added filtering by jurisdiction and search by title
- Implemented pagination (50 items per page)
- Shows only analyzed legislation by default (analysis_status = 'complete')
- Empty state handling for no results

**Priority 4.3 - Legislation Detail Page:**
- Created detail page at `app/src/app/legislation/[id]/page.tsx`
- Displays title, jurisdiction, type, citation, dates
- Shows compliance costs per-party with time, money, and assumed time value
- Shows enforcement costs similarly
- Highlights indefinite costs with explanatory notes
- Shows text excerpt if available
- Proper 404 handling for non-existent legislation

**Build Status:**
- All ESLint checks pass
- Production build successful
- 47 root tests still passing

**Files Created:**
- `app/package.json` - Next.js dependencies
- `app/tsconfig.json` - TypeScript config
- `app/next.config.ts` - Next.js config with better-sqlite3 external
- `app/postcss.config.mjs` - PostCSS with Tailwind
- `app/src/app/layout.tsx` - Root layout
- `app/src/app/page.tsx` - Index page
- `app/src/app/not-found.tsx` - 404 page
- `app/src/app/globals.css` - Global styles
- `app/src/app/legislation/[id]/page.tsx` - Detail page
- `app/src/lib/db.ts` - Database connection

**Next priority:** Priority 4.4 - Topic/Cluster Pages, then Priority 4.5 - Polish

---

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
