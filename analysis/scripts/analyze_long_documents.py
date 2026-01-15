#!/usr/bin/env python3
"""
Long Document Analysis Extension - Integrates chunking with existing analysis pipeline.

WHY: This module extends analyze_legislation.py to handle documents that exceed
the context window using intelligent section prioritization and multi-pass analysis.

This file demonstrates the integration approach. The key functions should be
incorporated into analyze_legislation.py or imported from there.

Usage:
    # Standalone testing
    python analysis/scripts/analyze_long_documents.py --id "some_id" --db data/legislation.db

    # Integration into existing script (modify analyze_legislation.py)
    from analyze_long_documents import analyze_with_chunking
"""

import argparse
import json
import sqlite3
import subprocess
import sys
import time
import re
from pathlib import Path
from datetime import datetime
from typing import Optional
from dataclasses import dataclass

# Import from the same directory
from document_chunking import (
    process_long_document,
    merge_chunk_analyses,
    LongDocumentConfig,
    AnalysisCompleteness,
    AnalysisChunk,
    get_document_stats
)

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "legislation.db"
CORPUS_PATH = PROJECT_ROOT / "data" / "corpus" / "corpus.jsonl"
CORPUS_INDEX_PATH = PROJECT_ROOT / "data" / "corpus" / "corpus_index.json"
PROMPT_PATH = PROJECT_ROOT / "analysis" / "prompts" / "cost_extraction.md"

# Global corpus index
_corpus_index: Optional[dict] = None

# Configuration
MAX_TEXT_CHARS = 95000  # Leave room for prompt
CHUNK_CONFIG = LongDocumentConfig(
    max_chars=MAX_TEXT_CHARS,
    min_coverage=0.85,
    max_chunks=5,
    context_budget_ratio=0.25,
    min_section_score=0.5
)


class RetryableError(Exception):
    """Error that should trigger a retry."""
    pass


class NonRetryableError(Exception):
    """Error that should NOT be retried."""
    pass


def load_corpus_index() -> dict:
    """Load the corpus byte-offset index."""
    global _corpus_index
    if _corpus_index is not None:
        return _corpus_index

    if not CORPUS_INDEX_PATH.exists():
        return {}

    with open(CORPUS_INDEX_PATH, 'r', encoding='utf-8') as f:
        _corpus_index = json.load(f)
    return _corpus_index


def get_legislation_text(version_id: str) -> Optional[str]:
    """Retrieve full text from corpus."""
    index = load_corpus_index()

    if version_id in index:
        byte_offset = index[version_id]
        with open(CORPUS_PATH, 'r', encoding='utf-8') as f:
            f.seek(byte_offset)
            line = f.readline()
            record = json.loads(line)
            return record.get('text', '')

    return None


def load_prompt_template() -> str:
    """Load the cost extraction prompt."""
    with open(PROMPT_PATH, 'r') as f:
        return f.read()


def call_claude(text: str, citation: str, prompt_template: str,
                chunk_context: Optional[str] = None) -> dict:
    """
    Call Claude CLI for analysis.

    Args:
        text: Legislation text to analyze
        citation: Citation for context
        prompt_template: Base prompt
        chunk_context: Optional context about multi-pass (e.g., "Chunk 1 of 3")

    Returns:
        Parsed JSON response
    """
    user_prompt = f"""Analyze the following Australian legislation and extract compliance and enforcement costs.

## Legislation Citation
{citation}

{chunk_context or ''}

## Legislation Text
{text}

## Your Task
Using the schema and guidelines provided in the system prompt, analyze this legislation and return a JSON object with the cost analysis. Return ONLY valid JSON, no other text.
"""

    full_prompt = f"{prompt_template}\n\n---\n\n{user_prompt}"

    try:
        result = subprocess.run(
            ['claude', '-p', full_prompt, '--output-format', 'json'],
            capture_output=True,
            text=True,
            timeout=180  # 3 minute timeout for large docs
        )
    except subprocess.TimeoutExpired:
        raise RetryableError("Claude CLI timed out")
    except OSError as e:
        raise RetryableError(f"Failed to execute Claude CLI: {e}")

    if result.returncode != 0:
        stderr = result.stderr.lower()
        if 'rate' in stderr or 'limit' in stderr or 'timeout' in stderr:
            raise RetryableError(f"Transient error: {result.stderr}")
        raise NonRetryableError(f"CLI error: {result.stderr}")

    try:
        response_text = result.stdout.strip()
        wrapper = json.loads(response_text)

        if isinstance(wrapper, dict) and 'result' in wrapper:
            response_text = wrapper['result']

        # Handle markdown code blocks
        if '```json' in response_text:
            match = re.search(r'```json\s*(.*?)\s*```', response_text, re.DOTALL)
            if match:
                response_text = match.group(1)
        elif '```' in response_text:
            match = re.search(r'```\s*(.*?)\s*```', response_text, re.DOTALL)
            if match:
                response_text = match.group(1)

        return json.loads(response_text)
    except json.JSONDecodeError as e:
        raise NonRetryableError(f"Failed to parse JSON: {e}")


def analyze_with_chunking(
    text: str,
    citation: str,
    prompt_template: str,
    max_retries: int = 3
) -> tuple[dict, dict]:
    """
    Analyze legislation with intelligent chunking for long documents.

    This is the main entry point that replaces the simple truncation approach.

    Args:
        text: Full legislation text (any length)
        citation: Citation for context
        prompt_template: Base prompt
        max_retries: Retry attempts per chunk

    Returns:
        Tuple of (analysis_result, metadata)
        - analysis_result: Dict matching cost_schema.json
        - metadata: Dict with document_length, chunks_used, coverage, etc.
    """
    # Process the document
    result = process_long_document(text, CHUNK_CONFIG)

    metadata = {
        'document_length': result.document_length,
        'section_count': result.section_count,
        'completeness': result.completeness.value,
        'coverage': result.coverage_score,
        'chunks_used': 1,
        'sections_included': result.included_sections,
        'sections_excluded': result.excluded_sections
    }

    if not result.requires_multi_pass:
        # Single-pass analysis
        print(f"    Single-pass analysis ({result.document_length:,} chars, "
              f"{result.coverage_score:.0%} coverage)")

        analysis = _call_with_retry(
            result.assembled_text, citation, prompt_template, max_retries
        )

        # Add note if document was truncated
        if result.completeness == AnalysisCompleteness.PRIORITIZED:
            existing_notes = analysis.get('analysis_notes', '') or ''
            analysis['analysis_notes'] = (
                f"{existing_notes} [Document was {result.document_length:,} chars; "
                f"analyzed {len(result.included_sections)} priority sections]"
            ).strip()

        return analysis, metadata

    # Multi-pass analysis
    print(f"    Multi-pass analysis ({len(result.chunks)} chunks, "
          f"{result.document_length:,} chars)")
    metadata['chunks_used'] = len(result.chunks)

    for chunk in result.chunks:
        print(f"      Processing chunk {chunk.chunk_id + 1}/{len(result.chunks)} "
              f"({len(chunk.text):,} chars, {chunk.coverage_contribution:.0%} coverage)")

        chunk_context = (
            f"## Analysis Context\n"
            f"This is **chunk {chunk.chunk_id + 1} of {len(result.chunks)}** of a large document.\n"
            f"Sections in this chunk: {', '.join(s.number for s in chunk.sections)}\n"
            f"Focus on costs mentioned in these sections only."
        )

        try:
            chunk.analysis = _call_with_retry(
                chunk.text, citation, prompt_template, max_retries, chunk_context
            )
        except (RetryableError, NonRetryableError) as e:
            print(f"      ERROR on chunk {chunk.chunk_id + 1}: {e}")
            chunk.analysis = None

    # Merge results
    analysis = merge_chunk_analyses(result.chunks)

    # Add metadata note
    existing_notes = analysis.get('analysis_notes', '') or ''
    analysis['analysis_notes'] = (
        f"{existing_notes} [Document analyzed in {len(result.chunks)} chunks; "
        f"total coverage: {result.coverage_score:.0%}]"
    ).strip()

    return analysis, metadata


def _call_with_retry(
    text: str,
    citation: str,
    prompt_template: str,
    max_retries: int,
    chunk_context: Optional[str] = None
) -> dict:
    """Call Claude with retry logic."""
    last_error = None

    for attempt in range(max_retries + 1):
        try:
            return call_claude(text, citation, prompt_template, chunk_context)
        except RetryableError as e:
            last_error = e
            if attempt < max_retries:
                wait_time = 2 ** (attempt + 1)
                print(f"      Retry {attempt + 1}/{max_retries} after {wait_time}s")
                time.sleep(wait_time)
        except NonRetryableError:
            raise

    raise RetryableError(f"All retries failed: {last_error}")


def save_analysis_to_db(
    conn: sqlite3.Connection,
    legislation_id: str,
    analysis: dict,
    metadata: dict
) -> None:
    """
    Save analysis results to database with metadata.

    This extends the original save function to include:
    - document_length
    - analysis_coverage
    - analysis_chunks
    - was_truncated
    """
    cursor = conn.cursor()

    # Delete existing costs
    cursor.execute('DELETE FROM costs WHERE legislation_id = ?', (legislation_id,))

    # Insert compliance costs
    for cost in analysis.get('compliance_costs', []):
        time_data = cost.get('time')
        money_data = cost.get('money')

        cursor.execute('''
            INSERT INTO costs (
                legislation_id, cost_type, party,
                time_hours, time_unit, time_display,
                money_cents, money_display,
                frequency, is_indefinite, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            legislation_id,
            'compliance',
            cost.get('party'),
            time_data.get('amount') if time_data else None,
            time_data.get('unit') if time_data else None,
            f"{time_data['amount']} {time_data['unit']}" if time_data else None,
            int(money_data['amount_aud'] * 100) if money_data and money_data.get('amount_aud') else None,
            f"${money_data['amount_aud']:,.2f}" if money_data and money_data.get('amount_aud') else None,
            cost.get('frequency', 'one_time'),
            1 if cost.get('is_indefinite') else 0,
            cost.get('description', '')
        ))

    # Insert enforcement cost
    enforcement = analysis.get('enforcement_cost')
    if enforcement:
        time_data = enforcement.get('time')
        money_data = enforcement.get('money')

        cursor.execute('''
            INSERT INTO costs (
                legislation_id, cost_type, party,
                time_hours, time_unit, time_display,
                money_cents, money_display,
                frequency, is_indefinite, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            legislation_id,
            'enforcement',
            None,
            time_data.get('amount') if time_data else None,
            time_data.get('unit') if time_data else None,
            f"{time_data['amount']} {time_data['unit']}" if time_data else None,
            int(money_data['amount_aud'] * 100) if money_data and money_data.get('amount_aud') else None,
            f"${money_data['amount_aud']:,.2f}" if money_data and money_data.get('amount_aud') else None,
            enforcement.get('frequency', 'one_time'),
            1 if enforcement.get('is_indefinite') else 0,
            enforcement.get('description', '')
        ))

    # Determine analysis status
    coverage = metadata.get('coverage', 1.0)
    status = 'complete' if coverage >= 0.95 else 'partial'

    # Update legislation record with metadata
    topics = analysis.get('topics', [])
    cursor.execute('''
        UPDATE legislation SET
            analysis_status = ?,
            topics = ?,
            document_length = ?,
            analysis_coverage = ?,
            analysis_chunks = ?,
            was_truncated = ?
        WHERE id = ?
    ''', (
        status,
        json.dumps(topics),
        metadata.get('document_length'),
        metadata.get('coverage'),
        metadata.get('chunks_used'),
        1 if coverage < 1.0 else 0,
        legislation_id
    ))

    conn.commit()


# ---------------------------------------------------------------------------
# Standalone CLI for testing
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Analyze long legislation with chunking")
    parser.add_argument('--id', required=True, help="Legislation ID to analyze")
    parser.add_argument('--db', type=Path, default=DEFAULT_DB_PATH, help="Database path")
    parser.add_argument('--dry-run', action='store_true', help="Show stats without analyzing")
    parser.add_argument('--verbose', '-v', action='store_true', help="Verbose output")
    args = parser.parse_args()

    # Load corpus index
    load_corpus_index()

    # Get legislation text
    text = get_legislation_text(args.id)
    if not text:
        print(f"ERROR: Could not find text for {args.id}")
        sys.exit(1)

    print(f"Legislation: {args.id}")
    print(f"Text length: {len(text):,} characters")

    # Get stats
    stats = get_document_stats(text)
    print(f"\nDocument stats:")
    print(f"  Sections: {stats['section_count']}")
    print(f"  Total score: {stats['total_score']:.1f}")
    print(f"  High-value sections: {stats['high_value_sections']}")
    print(f"  Dollar amounts: {stats['dollar_amounts']}")
    print(f"  Penalty units: {stats['penalty_units']}")
    print(f"  Has fee tables: {stats['has_fee_tables']}")
    print(f"  Section types: {', '.join(stats['section_types'])}")

    # Process document
    result = process_long_document(text, CHUNK_CONFIG)
    print(f"\nProcessing result:")
    print(f"  Completeness: {result.completeness.value}")
    print(f"  Coverage: {result.coverage_score:.1%}")
    print(f"  Requires multi-pass: {result.requires_multi_pass}")
    print(f"  Included sections: {len(result.included_sections)}")
    print(f"  Excluded sections: {len(result.excluded_sections)}")

    if result.requires_multi_pass:
        print(f"  Chunks needed: {len(result.chunks)}")
        for chunk in result.chunks:
            print(f"    Chunk {chunk.chunk_id}: {len(chunk.text):,} chars, "
                  f"{len(chunk.sections)} sections")

    if args.dry_run:
        print("\n[Dry run - skipping Claude analysis]")
        return

    # Run analysis
    print("\nRunning analysis...")
    prompt_template = load_prompt_template()

    try:
        analysis, metadata = analyze_with_chunking(text, args.id, prompt_template)

        print(f"\nAnalysis complete:")
        print(f"  Topics: {', '.join(analysis.get('topics', []))}")
        print(f"  Compliance costs: {len(analysis.get('compliance_costs', []))}")
        print(f"  Has enforcement cost: {analysis.get('has_enforcement_costs', False)}")
        print(f"  Confidence: {analysis.get('confidence', 'unknown')}")
        print(f"  Chunks used: {metadata.get('chunks_used', 1)}")
        print(f"  Coverage: {metadata.get('coverage', 1.0):.1%}")

        if args.verbose:
            print(f"\nFull analysis:")
            print(json.dumps(analysis, indent=2))

        # Save to database
        conn = sqlite3.connect(args.db)
        save_analysis_to_db(conn, args.id, analysis, metadata)
        conn.close()
        print(f"\nResults saved to database")

    except Exception as e:
        print(f"\nERROR: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
