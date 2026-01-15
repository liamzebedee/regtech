#!/usr/bin/env python3
"""
Legislation Cost Analyzer - Uses Claude to extract compliance/enforcement costs.

WHY: Manually analyzing 40,000+ pieces of legislation is impossible. Claude can
read legislation text and identify the parties affected and estimate the time/money
costs they bear. This enables systematic cost analysis at scale.

Usage:
    python analysis/scripts/analyze_legislation.py [--limit N] [--jurisdiction X]

Options:
    --limit N           Only analyze the first N pending records
    --jurisdiction X    Only analyze records from jurisdiction X
    --id ID             Analyze a specific legislation by ID
    --dry-run           Print what would be analyzed without calling Claude
    --parallel N        Run N parallel Claude instances (default: 1)
"""

import argparse
import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional
import re

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "legislation.db"
CORPUS_PATH = PROJECT_ROOT / "data" / "corpus" / "corpus.jsonl"
PROMPT_PATH = PROJECT_ROOT / "analysis" / "prompts" / "cost_extraction.md"
SCHEMA_PATH = PROJECT_ROOT / "analysis" / "prompts" / "cost_schema.json"

# Token limit for Claude context (stay under 50% saturation)
MAX_TEXT_CHARS = 100_000  # ~25k tokens, well under the limit


def load_prompt_template() -> str:
    """Load the cost extraction prompt."""
    with open(PROMPT_PATH, 'r') as f:
        return f.read()


def get_legislation_text(version_id: str) -> Optional[str]:
    """
    Retrieve the full text for a legislation from the corpus.

    WHY: The database only stores excerpts. We need the full text for analysis.
    """
    with open(CORPUS_PATH, 'r') as f:
        for line in f:
            record = json.loads(line)
            if record.get('version_id') == version_id:
                return record.get('text', '')
    return None


def truncate_text(text: str, max_chars: int = MAX_TEXT_CHARS) -> tuple[str, bool]:
    """
    Truncate text if it exceeds the limit.

    Returns:
        (truncated_text, was_truncated)
    """
    if len(text) <= max_chars:
        return text, False

    # Try to truncate at a section boundary
    truncated = text[:max_chars]

    # Look for a good break point (section header, paragraph)
    for pattern in [r'\n\d+\s+[A-Z]', r'\n\n', r'\.\n']:
        match = re.search(pattern, truncated[-1000:])
        if match:
            break_point = len(truncated) - 1000 + match.start()
            truncated = text[:break_point]
            break

    return truncated + "\n\n[TEXT TRUNCATED - Original length: {:,} characters]".format(len(text)), True


def call_claude(legislation_text: str, citation: str, prompt_template: str) -> dict:
    """
    Call Claude CLI to analyze legislation.

    Returns:
        Parsed JSON response from Claude
    """
    user_prompt = f"""Analyze the following Australian legislation and extract compliance and enforcement costs.

## Legislation Citation
{citation}

## Legislation Text
{legislation_text}

## Your Task
Using the schema and guidelines provided in the system prompt, analyze this legislation and return a JSON object with the cost analysis. Return ONLY valid JSON, no other text.
"""

    # Prepare the full prompt
    full_prompt = f"{prompt_template}\n\n---\n\n{user_prompt}"

    # Call Claude CLI
    # Using subprocess to call the claude CLI tool
    result = subprocess.run(
        ['claude', '-p', full_prompt, '--output-format', 'json'],
        capture_output=True,
        text=True,
        timeout=120  # 2 minute timeout
    )

    if result.returncode != 0:
        raise RuntimeError(f"Claude CLI error: {result.stderr}")

    # Parse the response
    try:
        # Claude CLI with --output-format json returns a wrapper object
        response_text = result.stdout.strip()
        wrapper = json.loads(response_text)

        # Extract the actual result from the wrapper
        if isinstance(wrapper, dict) and 'result' in wrapper:
            response_text = wrapper['result']
        else:
            response_text = result.stdout.strip()

        # The result may contain JSON wrapped in markdown code blocks
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
        raise RuntimeError(f"Failed to parse Claude response as JSON: {e}\nResponse: {result.stdout[:500]}")


def save_analysis_to_db(conn: sqlite3.Connection, legislation_id: str, analysis: dict) -> None:
    """
    Save the cost analysis results to the database.
    """
    cursor = conn.cursor()

    # Delete any existing costs for this legislation (for re-analysis)
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
            int(money_data['amount_aud'] * 100) if money_data and money_data.get('amount_aud') is not None else None,  # Convert to cents
            f"${money_data['amount_aud']:,.2f}" if money_data and money_data.get('amount_aud') is not None else None,
            cost.get('frequency', 'one_time'),
            1 if cost.get('is_indefinite') else 0,
            cost.get('description', '') + (f"\n\n{cost.get('indefinite_notes', '')}" if cost.get('indefinite_notes') else '')
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
            None,  # Enforcement is always the state
            time_data.get('amount') if time_data else None,
            time_data.get('unit') if time_data else None,
            f"{time_data['amount']} {time_data['unit']}" if time_data else None,
            int(money_data['amount_aud'] * 100) if money_data and money_data.get('amount_aud') is not None else None,
            f"${money_data['amount_aud']:,.2f}" if money_data and money_data.get('amount_aud') is not None else None,
            enforcement.get('frequency', 'one_time'),
            1 if enforcement.get('is_indefinite') else 0,
            enforcement.get('description', '') + (f"\n\n{enforcement.get('indefinite_notes', '')}" if enforcement.get('indefinite_notes') else '')
        ))

    # Update legislation analysis status
    cursor.execute(
        "UPDATE legislation SET analysis_status = 'complete' WHERE id = ?",
        (legislation_id,)
    )

    conn.commit()


def get_pending_legislation(conn: sqlite3.Connection, limit: int = 10,
                            jurisdiction: Optional[str] = None,
                            legislation_id: Optional[str] = None) -> list[dict]:
    """Get legislation pending analysis."""
    cursor = conn.cursor()

    if legislation_id:
        cursor.execute(
            'SELECT id, title, citation, jurisdiction FROM legislation WHERE id = ?',
            (legislation_id,)
        )
    elif jurisdiction:
        cursor.execute(
            '''SELECT id, title, citation, jurisdiction FROM legislation
               WHERE analysis_status = 'pending' AND jurisdiction = ?
               LIMIT ?''',
            (jurisdiction, limit)
        )
    else:
        cursor.execute(
            '''SELECT id, title, citation, jurisdiction FROM legislation
               WHERE analysis_status = 'pending'
               LIMIT ?''',
            (limit,)
        )

    return [
        {'id': row[0], 'title': row[1], 'citation': row[2], 'jurisdiction': row[3]}
        for row in cursor.fetchall()
    ]


def main():
    parser = argparse.ArgumentParser(description="Analyze legislation using Claude")
    parser.add_argument('--limit', type=int, default=10, help="Number of records to analyze")
    parser.add_argument('--jurisdiction', help="Filter by jurisdiction")
    parser.add_argument('--id', help="Analyze specific legislation by ID")
    parser.add_argument('--dry-run', action='store_true', help="Show what would be analyzed")
    parser.add_argument('--db', type=Path, default=DEFAULT_DB_PATH, help="Database path")
    args = parser.parse_args()

    # Load prompt template
    prompt_template = load_prompt_template()

    # Connect to database
    conn = sqlite3.connect(args.db)

    # Get pending legislation
    pending = get_pending_legislation(
        conn,
        limit=args.limit,
        jurisdiction=args.jurisdiction,
        legislation_id=args.id
    )

    if not pending:
        print("No pending legislation to analyze.")
        conn.close()
        return

    print(f"Found {len(pending)} legislation to analyze")
    print()

    if args.dry_run:
        for leg in pending:
            print(f"Would analyze: {leg['id']}")
            print(f"  Title: {leg['title']}")
            print(f"  Jurisdiction: {leg['jurisdiction']}")
            print()
        conn.close()
        return

    # Process each legislation
    analyzed = 0
    errors = 0

    for leg in pending:
        print(f"Analyzing: {leg['id']}")
        print(f"  Title: {leg['title']}")

        try:
            # Get full text from corpus
            text = get_legislation_text(leg['id'])
            if not text:
                print(f"  ERROR: Could not find text in corpus")
                errors += 1
                continue

            # Truncate if needed
            text, was_truncated = truncate_text(text)
            if was_truncated:
                print(f"  WARNING: Text truncated to {MAX_TEXT_CHARS:,} chars")

            # Call Claude for analysis
            print(f"  Calling Claude...")
            analysis = call_claude(text, leg['citation'] or leg['title'], prompt_template)

            # Save results
            save_analysis_to_db(conn, leg['id'], analysis)

            # Print summary
            print(f"  Confidence: {analysis.get('confidence', 'unknown')}")
            print(f"  Compliance costs: {len(analysis.get('compliance_costs', []))}")
            print(f"  Has enforcement cost: {analysis.get('has_enforcement_costs', False)}")

            analyzed += 1

        except Exception as e:
            print(f"  ERROR: {e}")
            # Mark as failed
            conn.execute(
                "UPDATE legislation SET analysis_status = 'failed' WHERE id = ?",
                (leg['id'],)
            )
            conn.commit()
            errors += 1

        print()

    # Summary
    print("=" * 50)
    print(f"Analyzed: {analyzed}")
    print(f"Errors: {errors}")

    # Show database stats
    cursor = conn.cursor()
    cursor.execute("SELECT analysis_status, COUNT(*) FROM legislation GROUP BY analysis_status")
    print("\nDatabase status:")
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[1]:,}")

    conn.close()


if __name__ == '__main__':
    main()
