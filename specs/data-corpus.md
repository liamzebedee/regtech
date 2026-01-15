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

---

## Corpus Structure (Documented)

### Location
`data/corpus/corpus.jsonl` (8.8GB, 232,560 documents)

### Format
JSONL (one JSON object per line)

### Record Schema
```json
{
  "version_id": "string - Unique identifier (e.g., 'tasmanian_legislation:2008-10-08/sr-2008-119')",
  "type": "string - Document type (decision|secondary_legislation|primary_legislation|bill)",
  "jurisdiction": "string - Jurisdiction (new_south_wales|commonwealth|queensland|tasmania|western_australia|south_australia|norfolk_island)",
  "source": "string - Data source (e.g., 'nsw_caselaw', 'federal_court_of_australia')",
  "mime": "string - Content type (typically 'text/html')",
  "date": "string - Date in YYYY-MM-DD format",
  "citation": "string - Human-readable citation",
  "url": "string - Source URL",
  "when_scraped": "string - ISO 8601 timestamp",
  "text": "string - Full text content"
}
```

### Document Type Distribution
| Type | Count | Percentage |
|------|-------|------------|
| decision | 189,216 | 81.4% |
| secondary_legislation | 31,696 | 13.6% |
| primary_legislation | 9,059 | 3.9% |
| bill | 2,589 | 1.1% |

### Jurisdiction Distribution
| Jurisdiction | Count | Percentage |
|--------------|-------|------------|
| new_south_wales | 119,587 | 51.4% |
| commonwealth | 103,882 | 44.7% |
| queensland | 3,306 | 1.4% |
| tasmania | 2,552 | 1.1% |
| western_australia | 1,564 | 0.7% |
| south_australia | 1,350 | 0.6% |
| norfolk_island | 319 | 0.1% |

### Missing Jurisdictions
Victoria (VIC), Australian Capital Territory (ACT), and Northern Territory (NT) are NOT present in this corpus version.

### Notes
- The corpus is heavily weighted toward court decisions (81%) rather than legislation
- For cost analysis, focus on `primary_legislation` and `secondary_legislation` types (42,755 documents)
- The `version_id` field serves as the unique identifier for each document
