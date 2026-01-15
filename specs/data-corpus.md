# Data Corpus

## Purpose

Acquire and manage the Open Australian Legal Corpus from HuggingFace so that legislation text is available locally for analysis. Without the raw legal text, no cost analysis can occur.

## Acceptance Criteria

- The dataset `isaacus/open-australian-legal-corpus` is cloned locally using the `hf` CLI tool
- The corpus structure is documented (file formats, metadata fields, directory organization)
- Legislation can be queried/retrieved by identifier (e.g., act name, jurisdiction, date)
- The data is indexed in a way that supports parallel processing (divisible into independent chunks)

## Edge Cases

- Dataset may be very large; storage and download time considerations
- Dataset structure may change between versions on HuggingFace
- Some legislation may have malformed or missing text
- Character encoding issues in older legislation
- Duplicate entries or superseded versions of the same law

## Dependencies

- `hf` CLI tool installed and authenticated
- Sufficient disk space for the corpus
- Understanding of the dataset's schema/structure before designing the analysis pipeline
