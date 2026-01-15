# Analysis Methodology

## Overview

This document describes the methodology for extracting compliance and enforcement costs from Australian legislation using AI-powered analysis.

## Why AI-Powered Analysis?

**Problem**: The Open Australian Legal Corpus contains 40,755 pieces of legislation (primary and secondary). Manual analysis of each document would require:
- Reading and understanding complex legal text
- Identifying parties affected by each requirement
- Estimating time and monetary costs
- Tracking indefinite costs like liability transfers

At even 30 minutes per document, manual analysis would require 20,000+ hours of expert time.

**Solution**: Claude (Sonnet model) can read legislation text and extract structured cost information. The model:
- Understands legal terminology and structure
- Identifies compliance requirements and affected parties
- Estimates reasonable time/money costs for typical cases
- Recognizes indefinite costs (burden of proof shifts, liability exposure)

## Analysis Pipeline

### 1. Document Selection

The pipeline processes legislation in the following priority:
1. Documents with `analysis_status = 'pending'`
2. Optionally, previously failed documents with `--retry-failed`

Filtering options:
- By jurisdiction (e.g., `--jurisdiction commonwealth`)
- By specific ID (e.g., `--id "federal_register:..."`)
- By limit (e.g., `--limit 100`)

### 2. Text Retrieval

Full legislation text is retrieved from the corpus using a byte-offset index:
- Index maps `version_id` to file position for O(1) lookup
- Eliminates linear scanning of 8.8GB corpus file
- Lookup time: ~0.24ms average

### 3. Text Preprocessing

Before analysis, text is cleaned:
- Unicode replacement characters removed (encoding artifacts)
- Line endings normalized
- Null bytes removed
- Excessive whitespace collapsed

Documents under 50 characters after cleanup are skipped as invalid.

### 4. Context Management

To stay within Claude's context window:
- Text is truncated at 100,000 characters (~25k tokens)
- Truncation occurs at section/paragraph boundaries when possible
- Long documents (>100k chars) receive a truncation notice

For very long documents (>500k chars), the chunking strategy in `analysis/docs/long_document_strategy.md` is used.

### 5. Cost Extraction

Claude analyzes the text using a structured prompt that requests:

**Topics** (2-5 tags):
- Categorizes the legislation (e.g., `taxation`, `workplace-safety`)
- Uses predefined vocabulary for consistency

**Compliance Costs** (per affected party):
- Party type: citizen, business, small_business, large_business, government, nonprofit
- Time cost: hours/days required for compliance activities
- Money cost: direct fees, required purchases, insurance
- Frequency: one_time, annually, per_transaction, etc.
- Indefinite flag: for non-quantifiable burdens

**Enforcement Costs** (state's burden):
- Time and money to administer/enforce
- Per-transaction or ongoing costs

**External References**:
- Other legislation referenced (Acts, Regulations)
- Reference type: definition, requirement, amendment, penalty

### 6. Validation

Claude's output is validated before storage:
- Required fields present (topics, compliance_costs, confidence)
- Party values match allowed enum
- Frequency values match allowed enum
- Time units match allowed enum
- Monetary amounts are non-negative numbers

Validation warnings are logged but don't block storage.

### 7. Storage

Results are stored in SQLite:
- Costs table: one row per cost entry (party, type, amounts)
- Legislation table: updated with topics, references, status

## Quality Assurance

### Conservative Estimation

The prompt instructs Claude to:
- Focus on typical cases, not extremes
- Express uncertainty in confidence levels
- Use notes to explain reasoning
- Set costs to null if truly unknown

### Confidence Levels

Each analysis includes a confidence rating:
- **High**: Clear requirements with explicit costs
- **Medium**: Costs inferred from context
- **Low**: Significant uncertainty or missing information

### Test Suite

A validation test suite (`analysis/tests/`) contains:
- Known-cost legislation with expected outcomes
- Validates against ground truth
- Catches regressions in prompt quality

### Manual Review

High-value analyses should be spot-checked:
- Complex legislation with many parties
- High-cost legislation
- Low-confidence results

## Limitations

### Truncation

Documents over 100,000 characters are truncated. This may miss:
- Fee schedules in later sections
- Penalty provisions in schedules
- Amendments to early provisions

The long document strategy mitigates this for critical documents.

### Historical Legislation

Older legislation may have:
- Archaic language Claude interprets differently
- Costs in historical currency (not inflation-adjusted)
- References to repealed legislation

### Cross-References

Legislation that heavily references other Acts may have incomplete analysis if the referenced legislation isn't available in context.

### Estimation Uncertainty

All time/money estimates are approximations for typical cases. Actual compliance costs vary by:
- Business size and complexity
- Existing systems and processes
- Geographic location
- Frequency of relevant activities

## Parallelization

The pipeline supports parallel analysis:
- `--workers N` spawns N parallel worker processes
- Each worker has its own database connection
- SQLite write contention handled with 30-second timeout
- Workers pre-load corpus index for fast lookups

Recommended: 4-8 workers on typical hardware.

## Retry Logic

Transient failures are automatically retried:
- Exponential backoff: 2s, 4s, 8s delays
- Retryable: timeouts, rate limits, network errors
- Non-retryable: parsing errors, invalid responses

Failed analyses are marked `analysis_status = 'failed'` and can be retried later with `--retry-failed`.
