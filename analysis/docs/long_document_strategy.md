# Long Document Handling Strategy for Cost Extraction

## Executive Summary

This document outlines the strategy for handling legislation documents that exceed the current 100k character limit. The approach uses **intelligent section prioritization** combined with **multi-pass analysis** and **smart result merging** to extract costs from documents up to 5+ million characters while maintaining analysis quality.

## Problem Statement

- **Current approach**: Simple truncation at 100,000 characters
- **Impact**: 12.4% of documents lose content, some losing 98%+ of text
- **Risk**: Fee schedules and penalty provisions often appear in later sections/schedules that get truncated

### Document Size Distribution (from corpus analysis)

| Size Range | Percentage | Handling Strategy |
|------------|------------|-------------------|
| < 100k chars | 87.6% | Direct analysis (current approach) |
| 100k - 500k chars | ~10% | Section prioritization |
| 500k - 2M chars | ~2% | Multi-pass with prioritization |
| > 2M chars | < 0.5% | Aggressive filtering + multi-pass |

## Proposed Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     analyze_legislation.py                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐    ┌───────────────────┐    ┌──────────────┐ │
│  │   Document   │───▶│ Section Extractor │───▶│  Prioritizer │ │
│  │    Input     │    │   (parse_structure)│    │ (score_section)│
│  └──────────────┘    └───────────────────┘    └──────────────┘ │
│                                                       │         │
│                                                       ▼         │
│  ┌──────────────┐    ┌───────────────────┐    ┌──────────────┐ │
│  │    Merged    │◀───│  Result Merger    │◀───│   Chunk      │ │
│  │    Output    │    │  (merge_analyses) │    │  Assembler   │ │
│  └──────────────┘    └───────────────────┘    └──────────────┘ │
│         │                                            │         │
│         ▼                                            ▼         │
│  ┌──────────────┐                            ┌──────────────┐  │
│  │   Database   │                            │  Claude API  │  │
│  │   (costs)    │                            │   (chunks)   │  │
│  └──────────────┘                            └──────────────┘  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Strategy 1: Section Prioritization (Primary)

### Concept

Australian legislation follows predictable structural patterns. Instead of truncating blindly, we:
1. Parse the document structure into sections
2. Score each section for cost-relevance
3. Assemble a context-optimized prompt from highest-scoring sections
4. Always include structural context (title, definitions, key terms)

### Implementation

#### Step 1: Structure Parsing

```python
@dataclass
class Section:
    """A parsed section of legislation."""
    section_type: str  # 'part', 'division', 'section', 'schedule', 'definition'
    number: str        # '1', '2A', 'Schedule 1'
    title: str         # Section title if present
    content: str       # Full text content
    start_pos: int     # Character position in original
    end_pos: int
    parent: Optional[str]  # Parent section reference

def parse_legislation_structure(text: str) -> list[Section]:
    """
    Parse legislation into structural sections.

    Detects:
    - Part headers: "Part 1—Preliminary"
    - Division headers: "Division 2—Registration"
    - Section headers: "23 Application fees"
    - Schedule headers: "Schedule 1—Fees"
    - Definition sections: "In this Act:" blocks
    """
    sections = []

    # Pattern for Part headers
    part_pattern = r'^Part\s+(\d+[A-Z]?)[\s—\-]+(.+?)$'

    # Pattern for Division headers
    division_pattern = r'^Division\s+(\d+[A-Z]?)[\s—\-]+(.+?)$'

    # Pattern for numbered sections
    section_pattern = r'^(\d{1,3}[A-Z]{0,2})\s+([A-Z][^\n]+)'

    # Pattern for Schedules
    schedule_pattern = r'^Schedule\s+(\d+[A-Z]?)[\s—\-]*(.*)$'

    # Parse and create Section objects...
    return sections
```

#### Step 2: Section Scoring

```python
# Keywords that indicate cost-relevant sections
COST_KEYWORDS = {
    # High relevance (weight: 10)
    'high': [
        'fee', 'fees', 'charge', 'charges', 'penalty', 'penalties',
        'fine', 'fines', 'payment', 'cost', 'costs', 'price',
        'levy', 'levies', 'rate', 'rates', 'tariff'
    ],
    # Medium relevance (weight: 5)
    'medium': [
        'registration', 'licence', 'license', 'permit', 'certificate',
        'application', 'renewal', 'annual', 'compliance', 'requirement',
        'must', 'shall', 'obligation', 'duty', 'lodge', 'submit', 'file'
    ],
    # Context relevance (weight: 2)
    'context': [
        'business', 'person', 'entity', 'corporation', 'company',
        'employer', 'employee', 'applicant', 'holder', 'operator'
    ]
}

# Section types with inherent relevance
SECTION_TYPE_SCORES = {
    'schedule': 15,      # Schedules often contain fee tables
    'penalty_section': 12,
    'fee_section': 12,
    'registration': 8,
    'compliance': 8,
    'definition': 5,     # Needed for context
    'part': 3,
    'division': 2,
    'section': 1,
}

def score_section(section: Section) -> float:
    """
    Score a section for cost-relevance.

    Returns a float score where higher = more likely to contain costs.
    """
    score = 0.0
    text_lower = (section.title + ' ' + section.content).lower()

    # Keyword scoring
    for keyword in COST_KEYWORDS['high']:
        score += text_lower.count(keyword) * 10
    for keyword in COST_KEYWORDS['medium']:
        score += text_lower.count(keyword) * 5
    for keyword in COST_KEYWORDS['context']:
        score += min(text_lower.count(keyword) * 2, 20)  # Cap context contribution

    # Section type bonus
    if 'schedule' in section.section_type.lower():
        score += SECTION_TYPE_SCORES['schedule']
    if any(w in section.title.lower() for w in ['fee', 'charge', 'penalty']):
        score += SECTION_TYPE_SCORES['fee_section']

    # Dollar amount detection (strong signal)
    dollar_matches = len(re.findall(r'\$[\d,]+', section.content))
    score += dollar_matches * 15

    # Penalty unit detection
    penalty_units = len(re.findall(r'\d+\s*penalty\s*unit', section.content, re.I))
    score += penalty_units * 12

    # Normalize by length (prefer dense cost sections)
    if len(section.content) > 100:
        score = score / (len(section.content) / 1000)  # Score per 1000 chars

    return score
```

#### Step 3: Context Assembly

```python
def assemble_analysis_context(
    sections: list[Section],
    max_chars: int = 95000,  # Leave room for prompt
    always_include: list[str] = ['definition', 'preliminary']
) -> tuple[str, list[str], bool]:
    """
    Assemble the optimal text for analysis.

    Returns:
        (assembled_text, included_sections, is_complete)
    """
    # Always include certain sections for context
    context_sections = []
    priority_sections = []

    for section in sections:
        if any(t in section.section_type.lower() for t in always_include):
            context_sections.append(section)
        else:
            priority_sections.append(section)

    # Score and sort remaining sections
    scored = [(score_section(s), s) for s in priority_sections]
    scored.sort(key=lambda x: x[0], reverse=True)

    # Build context, starting with required sections
    assembled = []
    included = []
    current_length = 0

    # Add context sections first
    for section in context_sections:
        if current_length + len(section.content) < max_chars * 0.3:  # Max 30% for context
            assembled.append(f"\n## {section.title}\n{section.content}")
            included.append(section.number)
            current_length += len(section.content)

    # Add scored sections by priority
    for score, section in scored:
        if current_length + len(section.content) < max_chars:
            assembled.append(f"\n## {section.title or section.number}\n{section.content}")
            included.append(section.number)
            current_length += len(section.content)

    # Determine if analysis is complete
    total_scored = sum(s[0] for s in scored)
    included_scored = sum(s[0] for s in scored if s[1].number in included)
    coverage = included_scored / total_scored if total_scored > 0 else 1.0

    is_complete = coverage > 0.95  # 95%+ of cost-relevant content included

    return '\n'.join(assembled), included, is_complete
```

## Strategy 2: Multi-Pass Analysis (For Extreme Cases)

### When to Use

- Document > 500k characters after section prioritization
- High-value sections exceed context window
- Coverage < 80% after first pass

### Approach

```python
@dataclass
class ChunkAnalysis:
    """Result from analyzing a single chunk."""
    chunk_id: int
    sections_analyzed: list[str]
    compliance_costs: list[dict]
    enforcement_cost: Optional[dict]
    topics: list[str]
    confidence: str
    coverage_score: float

def analyze_in_chunks(
    text: str,
    max_chunk_chars: int = 90000,
    overlap_chars: int = 2000
) -> list[ChunkAnalysis]:
    """
    Analyze a very long document in multiple passes.

    For documents > 500k chars:
    1. Parse into sections
    2. Group high-priority sections into chunks
    3. Analyze each chunk separately
    4. Return all chunk results for merging
    """
    sections = parse_legislation_structure(text)
    scored_sections = [(score_section(s), s) for s in sections]
    scored_sections.sort(key=lambda x: x[0], reverse=True)

    # Group into chunks, keeping related sections together
    chunks = []
    current_chunk = []
    current_size = 0

    for score, section in scored_sections:
        if score < 1.0:  # Skip very low relevance sections
            continue

        if current_size + len(section.content) > max_chunk_chars:
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = [section]
            current_size = len(section.content)
        else:
            current_chunk.append(section)
            current_size += len(section.content)

    if current_chunk:
        chunks.append(current_chunk)

    # Analyze each chunk
    results = []
    for i, chunk in enumerate(chunks):
        chunk_text = '\n\n'.join(s.content for s in chunk)
        section_ids = [s.number for s in chunk]

        # Call Claude for this chunk
        analysis = call_claude_for_chunk(chunk_text, chunk_number=i+1, total_chunks=len(chunks))

        results.append(ChunkAnalysis(
            chunk_id=i,
            sections_analyzed=section_ids,
            compliance_costs=analysis.get('compliance_costs', []),
            enforcement_cost=analysis.get('enforcement_cost'),
            topics=analysis.get('topics', []),
            confidence=analysis.get('confidence', 'low'),
            coverage_score=sum(score_section(s) for s in chunk) / sum(s[0] for s in scored_sections)
        ))

    return results
```

## Strategy 3: Result Merging

### The Challenge

When analyzing in chunks, we may get:
- Duplicate costs (same fee mentioned in multiple sections)
- Partial costs (time in one chunk, money in another)
- Conflicting confidence levels

### Merging Algorithm

```python
def merge_chunk_analyses(
    analyses: list[ChunkAnalysis],
    legislation_id: str
) -> dict:
    """
    Merge multiple chunk analyses into a single coherent result.

    Deduplication strategy:
    1. Group costs by (party, description_similarity, frequency)
    2. For duplicates, keep the one with most complete data
    3. Merge topics from all chunks
    4. Take lowest confidence as overall confidence
    """
    merged = {
        'legislation_id': legislation_id,
        'compliance_costs': [],
        'enforcement_cost': None,
        'topics': set(),
        'confidence': 'high',
        'analysis_metadata': {
            'chunks_analyzed': len(analyses),
            'total_coverage': sum(a.coverage_score for a in analyses),
            'sections_analyzed': []
        }
    }

    # Collect all costs
    all_compliance_costs = []
    all_enforcement_costs = []

    for analysis in analyses:
        all_compliance_costs.extend(analysis.compliance_costs)
        if analysis.enforcement_cost:
            all_enforcement_costs.append(analysis.enforcement_cost)
        merged['topics'].update(analysis.topics)
        merged['analysis_metadata']['sections_analyzed'].extend(analysis.sections_analyzed)

        # Confidence: take the lowest
        confidence_order = ['low', 'medium', 'high']
        if confidence_order.index(analysis.confidence) < confidence_order.index(merged['confidence']):
            merged['confidence'] = analysis.confidence

    # Deduplicate compliance costs
    merged['compliance_costs'] = deduplicate_costs(all_compliance_costs)

    # Merge enforcement costs (usually just one, but may have details from multiple chunks)
    if all_enforcement_costs:
        merged['enforcement_cost'] = merge_enforcement_costs(all_enforcement_costs)

    merged['topics'] = list(merged['topics'])[:5]  # Cap at 5 topics

    return merged


def deduplicate_costs(costs: list[dict]) -> list[dict]:
    """
    Remove duplicate costs based on similarity.

    Two costs are considered duplicates if:
    - Same party
    - Same frequency
    - Similar description (> 70% word overlap)
    - Similar amounts (within 20%)
    """
    if not costs:
        return []

    unique_costs = []

    for cost in costs:
        is_duplicate = False

        for existing in unique_costs:
            if is_similar_cost(cost, existing):
                # Merge: keep the more complete one
                existing = merge_cost_details(existing, cost)
                is_duplicate = True
                break

        if not is_duplicate:
            unique_costs.append(cost)

    return unique_costs


def is_similar_cost(cost1: dict, cost2: dict) -> bool:
    """Check if two costs are likely duplicates."""
    # Must have same party and frequency
    if cost1.get('party') != cost2.get('party'):
        return False
    if cost1.get('frequency') != cost2.get('frequency'):
        return False

    # Check description similarity
    desc1 = set(cost1.get('description', '').lower().split())
    desc2 = set(cost2.get('description', '').lower().split())

    if not desc1 or not desc2:
        return False

    overlap = len(desc1 & desc2) / max(len(desc1), len(desc2))
    if overlap < 0.7:
        return False

    # Check amount similarity if both have amounts
    money1 = cost1.get('money', {}).get('amount_aud') if cost1.get('money') else None
    money2 = cost2.get('money', {}).get('amount_aud') if cost2.get('money') else None

    if money1 and money2:
        ratio = min(money1, money2) / max(money1, money2)
        if ratio < 0.8:  # More than 20% difference
            return False

    return True


def merge_cost_details(primary: dict, secondary: dict) -> dict:
    """Merge two similar costs, keeping the most complete data."""
    # Keep primary as base
    merged = primary.copy()

    # Fill in missing fields from secondary
    if not merged.get('time') and secondary.get('time'):
        merged['time'] = secondary['time']
    if not merged.get('money') and secondary.get('money'):
        merged['money'] = secondary['money']
    if not merged.get('description') and secondary.get('description'):
        merged['description'] = secondary['description']

    # Prefer more detailed notes
    if secondary.get('indefinite_notes') and len(secondary.get('indefinite_notes', '')) > len(merged.get('indefinite_notes', '')):
        merged['indefinite_notes'] = secondary['indefinite_notes']

    return merged
```

## Database Schema Changes

### New Fields Required

```sql
-- Add to legislation table
ALTER TABLE legislation ADD COLUMN analysis_coverage REAL DEFAULT 1.0;
-- How much of the document was analyzed (0.0-1.0)

ALTER TABLE legislation ADD COLUMN analysis_chunks INTEGER DEFAULT 1;
-- Number of chunks used for analysis

ALTER TABLE legislation ADD COLUMN document_length INTEGER;
-- Original document length in characters

ALTER TABLE legislation ADD COLUMN truncated INTEGER DEFAULT 0;
-- Whether document was truncated (1) or fully analyzed (0)
```

### Updated Analysis Status Values

```
analysis_status:
  - 'pending'     : Not yet analyzed
  - 'complete'    : Fully analyzed (100% coverage or single-pass)
  - 'partial'     : Analyzed but with < 95% coverage
  - 'failed'      : Analysis failed
```

## Implementation Plan

### Phase 1: Section Extraction (Week 1)

1. Implement `parse_legislation_structure()` function
2. Add unit tests with sample legislation
3. Benchmark parsing performance on corpus

### Phase 2: Prioritization (Week 1-2)

1. Implement `score_section()` with keyword matching
2. Tune scoring weights using sample of analyzed legislation
3. Implement `assemble_analysis_context()`

### Phase 3: Multi-Pass Analysis (Week 2)

1. Implement chunk grouping logic
2. Modify `call_claude()` to support chunk context
3. Implement `merge_chunk_analyses()`

### Phase 4: Database & Integration (Week 3)

1. Add new database columns
2. Update `save_analysis_to_db()` for new metadata
3. Update progress reporting

### Phase 5: Testing & Tuning (Week 3-4)

1. Run on sample of long documents
2. Compare results with truncation approach
3. Tune parameters (chunk size, overlap, scoring weights)

## Modified Prompt for Chunk Analysis

When analyzing chunks, use this modified prompt prefix:

```markdown
## Analysis Context

You are analyzing **chunk {chunk_num} of {total_chunks}** of this legislation.

**Sections in this chunk:**
{section_list}

**Instructions for chunk analysis:**
1. Extract costs ONLY from the sections provided
2. Do not speculate about costs in sections you haven't seen
3. If a cost references another section not provided, note this in the description
4. Set confidence to 'low' if critical context seems missing

Previous chunks have analyzed: {previous_sections}
```

## Performance Considerations

### API Cost Optimization

| Document Size | Chunks | Estimated Tokens | Cost (Sonnet) |
|---------------|--------|------------------|---------------|
| < 100k chars | 1 | ~25k | ~$0.08 |
| 100k-300k chars | 1 (prioritized) | ~25k | ~$0.08 |
| 300k-1M chars | 2-3 | ~50-75k | ~$0.16-0.24 |
| > 1M chars | 3-5 | ~75-125k | ~$0.24-0.40 |

### Processing Time

- Section parsing: < 1 second for most documents
- Scoring: < 100ms per document
- Each Claude call: ~30-60 seconds
- Total for large document: 2-5 minutes

## Edge Cases

### 1. Legislation with No Clear Structure

**Problem**: Some older legislation lacks clear section markers.

**Solution**: Fall back to sentence-level chunking with overlap. Use paragraph boundaries as natural break points.

```python
def fallback_chunking(text: str, chunk_size: int = 90000, overlap: int = 5000) -> list[str]:
    """Simple chunking for unstructured documents."""
    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size

        # Find paragraph boundary
        if end < len(text):
            # Look for paragraph break
            para_break = text.rfind('\n\n', start + chunk_size - overlap, end)
            if para_break > start:
                end = para_break

        chunks.append(text[start:end])
        start = end - overlap if end < len(text) else len(text)

    return chunks
```

### 2. Fee Schedules as Tables

**Problem**: Fee schedules in PDFs may be converted to poorly-formatted text.

**Solution**: Detect table patterns and preserve structure:

```python
def detect_fee_table(text: str) -> bool:
    """Detect if section contains a fee table."""
    # Pattern: multiple lines with dollar amounts aligned
    lines = text.split('\n')
    dollar_lines = [l for l in lines if re.search(r'\$[\d,]+', l)]

    return len(dollar_lines) >= 3 and len(dollar_lines) / len(lines) > 0.3
```

### 3. Cross-References Between Sections

**Problem**: "Fee as prescribed in Schedule 2" - context split across chunks.

**Solution**: When extracting schedules, note cross-references:

```python
def extract_cross_references(section: Section) -> list[str]:
    """Find references to other sections."""
    patterns = [
        r'(?:see|refer to|in|under)\s+(?:section|schedule|part)\s+(\d+[A-Z]?)',
        r'(?:section|schedule|part)\s+(\d+[A-Z]?)\s+(?:applies|sets out)',
    ]
    refs = []
    for pattern in patterns:
        refs.extend(re.findall(pattern, section.content, re.I))
    return refs
```

## Success Metrics

1. **Coverage**: % of cost-relevant content analyzed (target: > 95% for all documents)
2. **Accuracy**: Validated against manual review sample (target: > 90% agreement)
3. **Efficiency**: API cost per document (target: < $0.50 average)
4. **Speed**: Processing time per document (target: < 5 minutes for any size)

## Appendix: Scoring Weight Calibration

Initial weights based on corpus analysis:

| Signal | Weight | Rationale |
|--------|--------|-----------|
| Dollar amount ($X) | 15 | Direct cost indicator |
| "penalty unit" | 12 | Standard penalty measure |
| Schedule section | 15 | Often contains fee tables |
| "fee"/"charge" keyword | 10 | High relevance |
| "registration"/"licence" | 5 | Common compliance context |
| Definition section | 5 (fixed) | Context required |

Weights should be tuned based on:
- False positive rate (sections scored high but no costs)
- False negative rate (costs found in low-scored sections)
- Coverage efficiency (cost-weighted content in assembled context)
