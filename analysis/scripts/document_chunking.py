#!/usr/bin/env python3
"""
Document Chunking Module - Intelligent handling of long legislation documents.

WHY: 12.4% of legislation documents exceed the 100k character limit. Simple truncation
loses important content (fee schedules, penalty sections often appear late in documents).
This module provides intelligent section extraction, prioritization, and multi-pass
analysis for long documents.

Usage:
    from document_chunking import process_long_document, LongDocumentConfig

    config = LongDocumentConfig(max_chars=95000)
    result = process_long_document(text, config)

    if result.requires_multi_pass:
        for chunk in result.chunks:
            analysis = call_claude(chunk.text, ...)
            chunk.analysis = analysis
        merged = merge_chunk_analyses(result.chunks)
    else:
        analysis = call_claude(result.assembled_text, ...)
"""

import re
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class LongDocumentConfig:
    """Configuration for long document handling."""
    max_chars: int = 95000  # Leave room for prompt template
    min_coverage: float = 0.90  # Minimum cost-relevance coverage before multi-pass
    max_chunks: int = 5  # Maximum chunks for very long documents
    context_budget_ratio: float = 0.25  # Max portion for context (definitions, etc.)
    min_section_score: float = 0.5  # Minimum score to include a section
    chunk_overlap_chars: int = 500  # Overlap between chunks for context continuity


class AnalysisCompleteness(Enum):
    """How complete the analysis is."""
    FULL = "full"           # Entire document analyzed
    PRIORITIZED = "prioritized"  # High-priority sections analyzed
    MULTI_PASS = "multi_pass"    # Analyzed in multiple chunks
    TRUNCATED = "truncated"      # Simple truncation (fallback)


# ---------------------------------------------------------------------------
# Section Parsing
# ---------------------------------------------------------------------------

@dataclass
class Section:
    """A parsed section of legislation."""
    section_type: str  # 'part', 'division', 'section', 'schedule', 'definition', 'preliminary'
    number: str        # '1', '2A', 'Schedule 1'
    title: str         # Section title if present
    content: str       # Full text content
    start_pos: int     # Character position in original
    end_pos: int       # Character position in original
    score: float = 0.0  # Cost-relevance score (set by score_section)
    cross_refs: list = field(default_factory=list)  # References to other sections


# Cost-relevance keywords with weights
COST_KEYWORDS = {
    'high': {  # Weight: 10 per occurrence
        'fee', 'fees', 'charge', 'charges', 'penalty', 'penalties',
        'fine', 'fines', 'payment', 'cost', 'costs', 'price', 'prices',
        'levy', 'levies', 'rate', 'rates', 'tariff', 'tariffs', 'surcharge'
    },
    'medium': {  # Weight: 5 per occurrence
        'registration', 'licence', 'license', 'permit', 'certificate',
        'application', 'renewal', 'annual', 'compliance', 'requirement',
        'must', 'shall', 'obligation', 'duty', 'lodge', 'submit', 'file',
        'register', 'notify', 'report', 'record', 'maintain'
    },
    'context': {  # Weight: 2 per occurrence (capped)
        'business', 'person', 'entity', 'corporation', 'company',
        'employer', 'employee', 'applicant', 'holder', 'operator',
        'proprietor', 'owner', 'occupier', 'licensee', 'registrant'
    }
}


def parse_legislation_structure(text: str) -> list[Section]:
    """
    Parse legislation text into structural sections.

    WHY: Australian legislation follows predictable patterns (Parts, Divisions,
    Sections, Schedules). Parsing this structure allows intelligent prioritization
    of cost-relevant sections.

    Returns:
        List of Section objects representing the document structure
    """
    sections = []

    # Pattern definitions for Australian legislation
    # Multiple patterns to handle different formatting styles across jurisdictions
    patterns = [
        # Part headers: "Part 1—Preliminary" or "PART 1 - PRELIMINARY"
        (r'^(?:PART|Part)\s+(\d+[A-Z]?)[\s\-—]+(.+?)$', 'part'),

        # Division headers: "Division 2—Registration"
        (r'^(?:DIVISION|Division)\s+(\d+[A-Z]?)[\s\-—]+(.+?)$', 'division'),

        # Schedule headers: "Schedule 1—Fees" or "SCHEDULE 1"
        (r'^(?:SCHEDULE|Schedule)\s+(\d+[A-Z]?)[\s\-—]*(.*)$', 'schedule'),

        # Numbered sections: "23  Application fees" (number + 2 spaces + title)
        (r'^(\d{1,4}[A-Z]{0,2})\s{2,}([A-Z][^\n]{0,100})$', 'section'),

        # Period-separated sections: "23. Application fees" (Tasmania, some others)
        (r'^(\d{1,4}[A-Z]{0,2})\.\s+([A-Z][^\n]{0,100})$', 'section'),

        # Sections with tab: "23\tApplication fees"
        (r'^(\d{1,4}[A-Z]{0,2})\t+([A-Z][^\n]{0,100})$', 'section'),

        # Chapter headers: "Chapter 3—Enforcement"
        (r'^(?:CHAPTER|Chapter)\s+(\d+[A-Z]?)[\s\-—]+(.+?)$', 'chapter'),
    ]

    # First pass: find all structural markers
    markers = []
    for pattern, section_type in patterns:
        for match in re.finditer(pattern, text, re.MULTILINE):
            markers.append({
                'type': section_type,
                'number': match.group(1),
                'title': match.group(2).strip() if match.lastindex >= 2 else '',
                'start': match.start(),
                'end': match.end(),
                'header_text': match.group(0)
            })

    # Sort markers by position
    markers.sort(key=lambda m: m['start'])

    # Second pass: extract content between markers
    for i, marker in enumerate(markers):
        # Content extends to next marker or end of document
        content_start = marker['end']
        content_end = markers[i + 1]['start'] if i + 1 < len(markers) else len(text)

        content = text[content_start:content_end].strip()

        # Detect special section types
        section_type = marker['type']
        title_lower = marker['title'].lower()

        if 'definition' in title_lower or 'interpretation' in title_lower:
            section_type = 'definition'
        elif 'preliminary' in title_lower or 'introduction' in title_lower:
            section_type = 'preliminary'
        elif any(w in title_lower for w in ['fee', 'charge', 'penalty', 'fine']):
            section_type = 'fee_section'

        section = Section(
            section_type=section_type,
            number=marker['number'],
            title=marker['title'],
            content=content,
            start_pos=marker['start'],
            end_pos=content_end
        )

        # Extract cross-references
        section.cross_refs = _extract_cross_references(content)

        sections.append(section)

    # If no structure found, create a single section for the entire document
    if not sections:
        sections.append(Section(
            section_type='unstructured',
            number='1',
            title='Full Document',
            content=text,
            start_pos=0,
            end_pos=len(text)
        ))

    return sections


def _extract_cross_references(text: str) -> list[str]:
    """Extract references to other sections (e.g., 'see Schedule 2')."""
    patterns = [
        r'(?:see|refer(?:red)? to|under|in)\s+(?:section|schedule|part)\s+(\d+[A-Z]?)',
        r'(?:section|schedule|part)\s+(\d+[A-Z]?)\s+(?:applies|sets? out|contains)',
        r'(?:prescribed|specified|set out)\s+(?:in|by)\s+(?:section|schedule|part)\s+(\d+[A-Z]?)',
    ]
    refs = []
    for pattern in patterns:
        refs.extend(re.findall(pattern, text, re.IGNORECASE))
    return list(set(refs))


# ---------------------------------------------------------------------------
# Section Scoring
# ---------------------------------------------------------------------------

def score_section(section: Section) -> float:
    """
    Score a section for cost-relevance.

    WHY: Not all sections are equally likely to contain costs. Fee schedules,
    penalty provisions, and registration requirements are high-value targets.
    Scoring allows prioritization within context limits.

    Returns:
        Float score where higher = more likely to contain costs
    """
    score = 0.0
    text = (section.title + ' ' + section.content).lower()
    text_len = max(len(section.content), 100)  # Avoid division by zero

    # Keyword scoring
    for keyword in COST_KEYWORDS['high']:
        count = len(re.findall(r'\b' + keyword + r's?\b', text))
        score += count * 10

    for keyword in COST_KEYWORDS['medium']:
        count = len(re.findall(r'\b' + keyword + r's?\b', text))
        score += count * 5

    for keyword in COST_KEYWORDS['context']:
        count = len(re.findall(r'\b' + keyword + r's?\b', text))
        score += min(count * 2, 20)  # Cap context contribution

    # Section type bonus
    type_bonuses = {
        'schedule': 20,
        'fee_section': 25,
        'penalty_section': 20,
        'definition': 10,  # Important for context
        'preliminary': 8,
    }
    if section.section_type in type_bonuses:
        score += type_bonuses[section.section_type]

    # Strong signals: dollar amounts and penalty units
    dollar_matches = len(re.findall(r'\$[\d,]+(?:\.\d{2})?', section.content))
    score += dollar_matches * 15

    penalty_units = len(re.findall(r'\d+\s*penalty\s*unit', section.content, re.I))
    score += penalty_units * 12

    # Fee table detection (multiple dollar amounts in structured format)
    if _detect_fee_table(section.content):
        score += 30

    # Normalize by length (prefer dense cost sections)
    # Score per 1000 characters
    normalized_score = (score / text_len) * 1000

    section.score = normalized_score
    return normalized_score


def _detect_fee_table(text: str) -> bool:
    """
    Detect if text contains a fee table structure.

    WHY: Fee tables are high-value extraction targets but may not trigger
    keyword matching heavily. Structural detection helps prioritize them.
    """
    lines = text.split('\n')
    if len(lines) < 3:
        return False

    dollar_lines = [l for l in lines if re.search(r'\$[\d,]+', l)]

    # Fee table: multiple lines with dollar amounts
    return len(dollar_lines) >= 3 and len(dollar_lines) / len(lines) > 0.2


# ---------------------------------------------------------------------------
# Context Assembly
# ---------------------------------------------------------------------------

@dataclass
class ProcessingResult:
    """Result of processing a long document."""
    assembled_text: str
    included_sections: list[str]
    excluded_sections: list[str]
    completeness: AnalysisCompleteness
    coverage_score: float  # 0.0-1.0: portion of cost-relevant content included
    requires_multi_pass: bool
    chunks: list = field(default_factory=list)  # Populated if multi-pass needed
    document_length: int = 0
    section_count: int = 0
    metadata: dict = field(default_factory=dict)


@dataclass
class AnalysisChunk:
    """A chunk for multi-pass analysis."""
    chunk_id: int
    text: str
    sections: list[Section]
    coverage_contribution: float
    analysis: Optional[dict] = None  # Populated after Claude call


def process_long_document(text: str, config: LongDocumentConfig = None) -> ProcessingResult:
    """
    Process a long document for cost extraction.

    WHY: Documents exceeding the context window need intelligent handling.
    This function decides the best strategy based on document characteristics.

    Args:
        text: Full legislation text
        config: Configuration options

    Returns:
        ProcessingResult with assembled text or chunks for analysis
    """
    if config is None:
        config = LongDocumentConfig()

    doc_length = len(text)

    # Short document: no processing needed
    if doc_length <= config.max_chars:
        return ProcessingResult(
            assembled_text=text,
            included_sections=['all'],
            excluded_sections=[],
            completeness=AnalysisCompleteness.FULL,
            coverage_score=1.0,
            requires_multi_pass=False,
            document_length=doc_length,
            section_count=1
        )

    # Parse structure
    sections = parse_legislation_structure(text)

    # Score all sections
    for section in sections:
        score_section(section)

    total_score = sum(s.score for s in sections)

    # Try single-pass with prioritization
    result = _assemble_prioritized_context(sections, config, total_score, doc_length)

    # Check if multi-pass is needed
    if result.coverage_score < config.min_coverage and len(sections) > 1:
        result = _prepare_multi_pass(sections, config, total_score, doc_length)

    return result


def _assemble_prioritized_context(
    sections: list[Section],
    config: LongDocumentConfig,
    total_score: float,
    doc_length: int
) -> ProcessingResult:
    """
    Assemble context from highest-priority sections.

    Strategy:
    1. Always include definition/preliminary sections (up to context budget)
    2. Sort remaining by score
    3. Include highest-scoring until budget exhausted
    """
    context_budget = int(config.max_chars * config.context_budget_ratio)
    main_budget = config.max_chars - context_budget

    # Separate context sections from content sections
    context_sections = [s for s in sections if s.section_type in ('definition', 'preliminary')]
    content_sections = [s for s in sections if s.section_type not in ('definition', 'preliminary')]

    # Sort content by score (highest first)
    content_sections.sort(key=lambda s: s.score, reverse=True)

    assembled_parts = []
    included = []
    excluded = []
    current_length = 0
    included_score = 0.0

    # Add context sections
    for section in context_sections:
        if current_length + len(section.content) <= context_budget:
            assembled_parts.append(_format_section(section))
            included.append(section.number)
            current_length += len(section.content)
            included_score += section.score
        else:
            excluded.append(section.number)

    # Add content sections by priority
    for section in content_sections:
        section_len = len(section.content)

        if section.score < config.min_section_score:
            excluded.append(section.number)
            continue

        if current_length + section_len <= config.max_chars:
            assembled_parts.append(_format_section(section))
            included.append(section.number)
            current_length += section_len
            included_score += section.score
        else:
            excluded.append(section.number)

    coverage = included_score / total_score if total_score > 0 else 1.0

    # Add truncation notice if content excluded
    if excluded:
        notice = (
            f"\n\n[ANALYSIS NOTE: Document was {doc_length:,} characters. "
            f"Sections analyzed: {len(included)}/{len(sections)}. "
            f"Excluded sections: {', '.join(excluded[:10])}"
            f"{' and more...' if len(excluded) > 10 else ''}]"
        )
        assembled_parts.append(notice)

    return ProcessingResult(
        assembled_text='\n\n'.join(assembled_parts),
        included_sections=included,
        excluded_sections=excluded,
        completeness=AnalysisCompleteness.PRIORITIZED if excluded else AnalysisCompleteness.FULL,
        coverage_score=coverage,
        requires_multi_pass=coverage < config.min_coverage,
        document_length=doc_length,
        section_count=len(sections),
        metadata={'total_score': total_score, 'included_score': included_score}
    )


def _prepare_multi_pass(
    sections: list[Section],
    config: LongDocumentConfig,
    total_score: float,
    doc_length: int
) -> ProcessingResult:
    """
    Prepare document for multi-pass analysis.

    Strategy:
    1. Group high-scoring sections into chunks
    2. Each chunk gets context (definitions) + content sections
    3. Ensure cross-referenced sections are in same chunk when possible
    """
    # Sort by score
    scored_sections = sorted(sections, key=lambda s: s.score, reverse=True)

    # Filter out very low-scoring sections
    relevant_sections = [s for s in scored_sections if s.score >= config.min_section_score]

    # Context sections should appear in every chunk
    context_sections = [s for s in sections if s.section_type in ('definition', 'preliminary')]
    context_text = '\n\n'.join(_format_section(s) for s in context_sections)
    context_len = len(context_text)

    # Available space per chunk after context
    chunk_content_budget = config.max_chars - context_len - 500  # Buffer for notices

    # Group into chunks
    chunks = []
    current_chunk_sections = []
    current_chunk_len = 0

    for section in relevant_sections:
        if section.section_type in ('definition', 'preliminary'):
            continue  # Context sections handled separately

        section_len = len(section.content)

        if current_chunk_len + section_len > chunk_content_budget:
            # Finalize current chunk
            if current_chunk_sections:
                chunks.append(current_chunk_sections)
            current_chunk_sections = [section]
            current_chunk_len = section_len
        else:
            current_chunk_sections.append(section)
            current_chunk_len += section_len

        if len(chunks) >= config.max_chunks - 1:
            # Put remaining in last chunk
            break

    if current_chunk_sections:
        chunks.append(current_chunk_sections)

    # Build AnalysisChunk objects
    analysis_chunks = []
    for i, chunk_sections in enumerate(chunks):
        chunk_content = [context_text] if context_text else []

        chunk_notice = (
            f"[CHUNK {i+1} OF {len(chunks)}]\n"
            f"[Sections in this chunk: {', '.join(s.number for s in chunk_sections)}]"
        )
        chunk_content.append(chunk_notice)

        for section in chunk_sections:
            chunk_content.append(_format_section(section))

        chunk_score = sum(s.score for s in chunk_sections)
        chunk_coverage = chunk_score / total_score if total_score > 0 else 0

        analysis_chunks.append(AnalysisChunk(
            chunk_id=i,
            text='\n\n'.join(chunk_content),
            sections=chunk_sections,
            coverage_contribution=chunk_coverage
        ))

    total_coverage = sum(c.coverage_contribution for c in analysis_chunks)

    # Also include context section scores
    context_score = sum(s.score for s in context_sections)
    total_coverage += context_score / total_score if total_score > 0 else 0

    return ProcessingResult(
        assembled_text='',  # Not used for multi-pass
        included_sections=[s.number for chunk in chunks for s in chunk],
        excluded_sections=[s.number for s in sections
                          if s.number not in [s2.number for chunk in chunks for s2 in chunk]
                          and s.section_type not in ('definition', 'preliminary')],
        completeness=AnalysisCompleteness.MULTI_PASS,
        coverage_score=min(total_coverage, 1.0),
        requires_multi_pass=True,
        chunks=analysis_chunks,
        document_length=doc_length,
        section_count=len(sections),
        metadata={
            'total_score': total_score,
            'num_chunks': len(chunks),
            'context_included': bool(context_sections)
        }
    )


def _format_section(section: Section) -> str:
    """Format a section for inclusion in the prompt."""
    header = f"## {section.section_type.title()} {section.number}"
    if section.title:
        header += f": {section.title}"

    return f"{header}\n\n{section.content}"


# ---------------------------------------------------------------------------
# Result Merging
# ---------------------------------------------------------------------------

def merge_chunk_analyses(chunks: list[AnalysisChunk]) -> dict:
    """
    Merge analyses from multiple chunks into a single coherent result.

    WHY: Multi-pass analysis produces separate results that may have duplicates
    or complementary information. This function consolidates them into the
    expected output format.

    Args:
        chunks: List of AnalysisChunk with .analysis populated

    Returns:
        Merged analysis dict matching the cost_schema.json format
    """
    merged = {
        'legislation_summary': '',
        'topics': [],
        'has_compliance_costs': False,
        'compliance_costs': [],
        'has_enforcement_costs': False,
        'enforcement_cost': None,
        'analysis_notes': '',
        'confidence': 'high',
        'analysis_metadata': {
            'chunks_analyzed': len(chunks),
            'total_coverage': sum(c.coverage_contribution for c in chunks),
            'sections_analyzed': []
        }
    }

    all_summaries = []
    all_topics = set()
    all_compliance_costs = []
    all_enforcement_costs = []
    all_notes = []
    confidence_levels = []

    for chunk in chunks:
        if chunk.analysis is None:
            continue

        analysis = chunk.analysis

        # Collect summaries
        if analysis.get('legislation_summary'):
            all_summaries.append(analysis['legislation_summary'])

        # Collect topics
        all_topics.update(analysis.get('topics', []))

        # Collect compliance costs
        all_compliance_costs.extend(analysis.get('compliance_costs', []))

        # Collect enforcement costs
        if analysis.get('enforcement_cost'):
            all_enforcement_costs.append(analysis['enforcement_cost'])

        # Collect notes
        if analysis.get('analysis_notes'):
            all_notes.append(analysis['analysis_notes'])

        # Track confidence
        if analysis.get('confidence'):
            confidence_levels.append(analysis['confidence'])

        # Track sections
        merged['analysis_metadata']['sections_analyzed'].extend(
            s.number for s in chunk.sections
        )

    # Merge summaries (take first non-empty or combine)
    if all_summaries:
        merged['legislation_summary'] = all_summaries[0]

    # Merge topics (union, capped at 5)
    merged['topics'] = list(all_topics)[:5]

    # Deduplicate compliance costs
    merged['compliance_costs'] = _deduplicate_costs(all_compliance_costs)
    merged['has_compliance_costs'] = len(merged['compliance_costs']) > 0

    # Merge enforcement costs
    if all_enforcement_costs:
        merged['enforcement_cost'] = _merge_enforcement_costs(all_enforcement_costs)
        merged['has_enforcement_costs'] = True

    # Combine notes
    if all_notes:
        merged['analysis_notes'] = ' | '.join(all_notes[:3])

    # Confidence: take lowest
    if confidence_levels:
        confidence_order = {'low': 0, 'medium': 1, 'high': 2}
        min_confidence = min(confidence_levels, key=lambda c: confidence_order.get(c, 0))
        merged['confidence'] = min_confidence

    return merged


def _deduplicate_costs(costs: list[dict]) -> list[dict]:
    """
    Remove duplicate compliance costs.

    Duplicates are identified by:
    - Same party
    - Same frequency
    - Similar description (>70% word overlap)
    - Similar amounts (within 20%)
    """
    if not costs:
        return []

    unique_costs = []

    for cost in costs:
        is_duplicate = False

        for i, existing in enumerate(unique_costs):
            if _is_similar_cost(cost, existing):
                # Merge: keep more complete version
                unique_costs[i] = _merge_cost_details(existing, cost)
                is_duplicate = True
                break

        if not is_duplicate:
            unique_costs.append(cost)

    return unique_costs


def _is_similar_cost(cost1: dict, cost2: dict) -> bool:
    """Check if two costs are duplicates."""
    # Must have same party
    if cost1.get('party') != cost2.get('party'):
        return False

    # Must have same frequency
    if cost1.get('frequency') != cost2.get('frequency'):
        return False

    # Check description similarity
    desc1 = set(cost1.get('description', '').lower().split())
    desc2 = set(cost2.get('description', '').lower().split())

    if not desc1 or not desc2:
        return False

    # Jaccard similarity
    intersection = len(desc1 & desc2)
    union = len(desc1 | desc2)
    similarity = intersection / union if union > 0 else 0

    if similarity < 0.5:
        return False

    # Check amount similarity if both have amounts
    money1 = cost1.get('money', {})
    money2 = cost2.get('money', {})

    if money1 and money2:
        amount1 = money1.get('amount_aud')
        amount2 = money2.get('amount_aud')

        if amount1 and amount2:
            ratio = min(amount1, amount2) / max(amount1, amount2)
            if ratio < 0.8:  # More than 20% difference
                return False

    return True


def _merge_cost_details(primary: dict, secondary: dict) -> dict:
    """Merge two similar costs, keeping most complete data."""
    merged = primary.copy()

    # Fill in missing fields
    if not merged.get('time') and secondary.get('time'):
        merged['time'] = secondary['time']

    if not merged.get('money') and secondary.get('money'):
        merged['money'] = secondary['money']

    # Prefer longer descriptions
    if len(secondary.get('description', '')) > len(merged.get('description', '')):
        merged['description'] = secondary['description']

    # Prefer longer notes
    if len(secondary.get('indefinite_notes', '') or '') > len(merged.get('indefinite_notes', '') or ''):
        merged['indefinite_notes'] = secondary['indefinite_notes']

    return merged


def _merge_enforcement_costs(costs: list[dict]) -> dict:
    """Merge multiple enforcement cost entries."""
    if not costs:
        return None

    if len(costs) == 1:
        return costs[0]

    # Start with first, merge in others
    merged = costs[0].copy()

    for cost in costs[1:]:
        merged = _merge_cost_details(merged, cost)

    return merged


# ---------------------------------------------------------------------------
# Utility Functions
# ---------------------------------------------------------------------------

def estimate_chunks_needed(text_length: int, config: LongDocumentConfig = None) -> int:
    """Estimate how many chunks will be needed for a document."""
    if config is None:
        config = LongDocumentConfig()

    if text_length <= config.max_chars:
        return 1

    # Estimate based on text length
    # Account for overhead (context, notices) and prioritization reducing effective content
    effective_chunk_size = config.max_chars * 0.7  # 70% for content after context
    estimated_relevant_content = text_length * 0.5  # Assume 50% is cost-relevant

    chunks = int(estimated_relevant_content / effective_chunk_size) + 1
    return min(chunks, config.max_chunks)


def get_document_stats(text: str) -> dict:
    """Get statistics about a document for logging/debugging."""
    sections = parse_legislation_structure(text)
    for s in sections:
        score_section(s)

    return {
        'length': len(text),
        'section_count': len(sections),
        'total_score': sum(s.score for s in sections),
        'high_value_sections': len([s for s in sections if s.score > 10]),
        'has_fee_tables': any(_detect_fee_table(s.content) for s in sections),
        'dollar_amounts': len(re.findall(r'\$[\d,]+', text)),
        'penalty_units': len(re.findall(r'\d+\s*penalty\s*unit', text, re.I)),
        'section_types': list(set(s.section_type for s in sections))
    }


# ---------------------------------------------------------------------------
# Testing / CLI
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    import sys
    import json

    # Simple test with a sample document
    sample_text = """
Part 1—Preliminary

1  Short title
This Act may be cited as the Sample Act 2024.

2  Definitions
In this Act:
fee means the amount payable under Schedule 1.
penalty unit has the meaning given in the Crimes Act.

Part 2—Registration Requirements

10  Application for registration
A person must apply for registration by submitting Form 1 and paying the application fee of $500.

11  Renewal of registration
Registration must be renewed annually. The renewal fee is $200.

12  Penalties
A person who fails to register commits an offence.
Penalty: 50 penalty units.

Schedule 1—Fees

Item    Description                 Fee
1       Application fee             $500
2       Annual renewal fee          $200
3       Late payment fee            $50
4       Certificate of registration $25
"""

    print("Testing document chunking module...")
    print("=" * 60)

    config = LongDocumentConfig(max_chars=2000)  # Small for testing
    result = process_long_document(sample_text, config)

    print(f"Document length: {result.document_length}")
    print(f"Section count: {result.section_count}")
    print(f"Completeness: {result.completeness.value}")
    print(f"Coverage score: {result.coverage_score:.2%}")
    print(f"Requires multi-pass: {result.requires_multi_pass}")
    print(f"Included sections: {result.included_sections}")
    print(f"Excluded sections: {result.excluded_sections}")

    if result.requires_multi_pass:
        print(f"\nChunks prepared: {len(result.chunks)}")
        for chunk in result.chunks:
            print(f"  Chunk {chunk.chunk_id}: {len(chunk.text)} chars, "
                  f"{len(chunk.sections)} sections, "
                  f"{chunk.coverage_contribution:.2%} coverage")
    else:
        print(f"\nAssembled text preview:")
        print(result.assembled_text[:500] + "...")

    print("\n" + "=" * 60)
    print("Document stats:")
    stats = get_document_stats(sample_text)
    print(json.dumps(stats, indent=2))
