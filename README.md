# Australian Legislation Cost Analysis

Analyze compliance and enforcement costs of Australian legislation using AI-powered extraction from the Open Australian Legal Corpus.

## Overview

This project extracts and displays the costs of complying with Australian legislation, including:

- **Compliance costs**: Time and money required for citizens, businesses, and other parties to comply
- **Enforcement costs**: Government resources required to enforce legislation
- **Indefinite costs**: Liability transfers, burden of proof shifts, and other non-quantifiable impacts

## Prerequisites

- Node.js 20+
- Python 3.8+
- Claude CLI (for running analyses)
- ~10GB disk space (for corpus data)

## Quick Start

### 1. Install Dependencies

```bash
# Root project (types, database utilities)
npm install

# Website application
cd app && npm install && cd ..
```

### 2. Download the Corpus

The corpus is downloaded from HuggingFace using the `hf` CLI:

```bash
# Install hf CLI if needed
pip install huggingface_hub

# Download corpus (8.8GB)
hf download isaacus/open-australian-legal-corpus --local-dir data/corpus --repo-type dataset
```

### 3. Index the Corpus

Populate the database with legislation metadata:

```bash
python analysis/scripts/index_corpus.py
```

This indexes ~40,755 pieces of legislation (primary and secondary) from the corpus.

### 4. Run Analysis (requires Claude CLI)

Analyze legislation to extract cost data:

```bash
# Analyze 10 pieces of legislation
python analysis/scripts/analyze_legislation.py --limit 10

# Analyze specific jurisdiction
python analysis/scripts/analyze_legislation.py --jurisdiction commonwealth --limit 50

# Analyze specific legislation by ID
python analysis/scripts/analyze_legislation.py --id "commonwealth:act-1901-001"
```

### 5. Start the Website

```bash
cd app
npm run dev
```

Visit http://localhost:3000 to browse legislation and costs.

## Project Structure

```
law/
├── analysis/           # Data acquisition and LLM analysis scripts
│   ├── prompts/        # Claude prompt templates and schemas
│   └── scripts/        # Python scripts for indexing and analysis
├── app/                # Next.js website (TypeScript, React)
│   └── src/
│       ├── app/        # App router pages
│       ├── components/ # React components
│       └── lib/        # Database connection
├── data/               # SQLite database + HuggingFace corpus
│   ├── corpus/         # Downloaded corpus (corpus.jsonl)
│   └── legislation.db  # SQLite database
├── src/lib/            # Shared utilities
│   ├── types/          # TypeScript types for cost model
│   └── db/             # Database schema and repository
└── specs/              # Project specifications
```

## Running Tests

```bash
# Run all tests (47 tests)
npm test

# Run tests in watch mode
npm run test:watch

# Build TypeScript
npm run build
```

## Database

The SQLite database (`data/legislation.db`) contains:

- **legislation** table: Metadata for 40,755 pieces of legislation
- **costs** table: Extracted compliance and enforcement costs

### Sample Queries

```sql
-- Database status overview
SELECT analysis_status, COUNT(*) as count
FROM legislation
GROUP BY analysis_status;

-- Find legislation with high compliance costs (>$1000)
SELECT l.title, l.jurisdiction, c.party,
       c.money_cents / 100.0 as cost_aud,
       c.time_display
FROM legislation l
JOIN costs c ON l.id = c.legislation_id
WHERE c.cost_type = 'compliance' AND c.money_cents > 100000
ORDER BY c.money_cents DESC;

-- Total compliance costs by jurisdiction
SELECT l.jurisdiction,
       COUNT(DISTINCT l.id) as legislation_count,
       SUM(c.money_cents) / 100.0 as total_cost_aud
FROM legislation l
JOIN costs c ON l.id = c.legislation_id
WHERE c.cost_type = 'compliance'
GROUP BY l.jurisdiction;

-- Find indefinite costs (liability transfers, burden of proof)
SELECT l.title, c.party, c.notes
FROM legislation l
JOIN costs c ON l.id = c.legislation_id
WHERE c.is_indefinite = 1;

-- Costs by party type
SELECT c.party,
       COUNT(*) as cost_count,
       SUM(c.money_cents) / 100.0 as total_money_aud,
       SUM(c.time_hours) as total_hours
FROM costs c
WHERE c.cost_type = 'compliance'
GROUP BY c.party
ORDER BY total_money_aud DESC;

-- Legislation by topic
SELECT l.title, l.topics, l.jurisdiction
FROM legislation l
WHERE l.topics != '[]' AND l.analysis_status = 'complete'
ORDER BY l.date_enacted DESC;

-- Recent legislation (2020+)
SELECT title, jurisdiction, date_enacted, analysis_status
FROM legislation
WHERE date_enacted >= '2020-01-01'
ORDER BY date_enacted DESC
LIMIT 20;

-- Legislation with both time and money costs
SELECT l.title, c.party, c.time_display, c.money_display
FROM legislation l
JOIN costs c ON l.id = c.legislation_id
WHERE c.time_hours IS NOT NULL AND c.money_cents IS NOT NULL;

-- All costs for a specific legislation
SELECT *
FROM costs
WHERE legislation_id = 'federal_register_of_legislation:C2014A00095';
```

## Corpus Details

Source: [Open Australian Legal Corpus](https://huggingface.co/datasets/isaacus/open-australian-legal-corpus)

| Statistic | Value |
|-----------|-------|
| Total documents | 232,560 |
| Legislation (primary + secondary) | 42,755 |
| File size | 8.8GB |
| Format | JSONL |

### Jurisdictions Covered

- Commonwealth (federal)
- New South Wales
- Queensland
- Tasmania
- Western Australia
- South Australia
- Norfolk Island

**Note**: Victoria, ACT, and Northern Territory are not present in this corpus version.

## Cost Model

Costs are categorized by:

- **Party**: Who bears the cost (citizen, business, small_business, large_business, government, nonprofit)
- **Type**: Compliance or enforcement
- **Dimensions**:
  - Time (hours, with assumed monetary value based on wage rates)
  - Money (AUD, stored in cents)
  - Indefinite (non-quantifiable impacts with explanatory notes)

See `specs/cost-model.md` for detailed specification.

## License

This project analyzes public legislation data from the Open Australian Legal Corpus.
