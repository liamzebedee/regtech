# Analysis Pipeline

## Purpose

Use Claude CLI to analyze legislation text and extract structured cost data. The pipeline must be parallelizable, resumable, and produce consistent results across the entire corpus.

## Acceptance Criteria

- Each piece of legislation is analyzed by Claude (Sonnet model) to produce:
  - Compliance costs (per party: time, money, or indefinite)
  - Enforcement costs (state's burden: time, money, or indefinite)
  - Notes explaining the cost reasoning
- Analysis is parallelizable (multiple Claude instances can work on different legislation simultaneously)
- Context window is managed to stay under 50% saturation (~64k tokens)
- Results are written to the SQLite database as they complete
- The pipeline is idempotent (re-running skips already-analyzed legislation)
- Failed analyses are logged and can be retried
- Start with small, simple legislation to validate the approach before scaling

## Edge Cases

- Legislation too long for a single context window (must be chunked or summarized)
- Claude produces inconsistent or hallucinated cost figures
- Rate limiting or API failures during large batch runs
- Legislation that references other legislation (dependencies unclear without cross-referencing)
- Very old legislation with archaic language
- Legislation that has been repealed or superseded

## Dependencies

- Data corpus must be available locally
- Cost model must be defined so Claude knows what to extract
- Database schema must exist to receive results
- Claude CLI must be installed and configured
