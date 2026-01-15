#!/usr/bin/env python3
"""
Corpus Indexer - Populates the legislation SQLite database from the JSONL corpus.

WHY: The raw corpus is a single 8.8GB JSONL file. This script extracts metadata
and creates database records that enable efficient querying, filtering, and
analysis pipeline processing.

Usage:
    python analysis/scripts/index_corpus.py [--limit N] [--types primary,secondary]

Options:
    --limit N     Only process the first N records (for testing)
    --types       Comma-separated list of document types to include
                  Default: primary_legislation,secondary_legislation
    --all-types   Include all document types (including decisions and bills)
    --db PATH     Path to SQLite database (default: data/legislation.db)
    --corpus PATH Path to corpus JSONL file (default: data/corpus/corpus.jsonl)
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from datetime import datetime
from typing import Iterator, Optional

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
DEFAULT_CORPUS_PATH = PROJECT_ROOT / "data" / "corpus" / "corpus.jsonl"
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "legislation.db"

# Text excerpt length (first N characters for preview)
EXCERPT_LENGTH = 500


def create_tables(conn: sqlite3.Connection) -> None:
    """Create database tables if they don't exist."""
    conn.executescript("""
        PRAGMA journal_mode = WAL;

        CREATE TABLE IF NOT EXISTS legislation (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            jurisdiction TEXT NOT NULL,
            type TEXT NOT NULL DEFAULT 'other',
            date_enacted TEXT,
            date_repealed TEXT,
            citation TEXT,
            source_url TEXT,
            text_path TEXT,
            text_excerpt TEXT,
            topics TEXT NOT NULL DEFAULT '[]',
            analysis_status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS costs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            legislation_id TEXT NOT NULL,
            cost_type TEXT NOT NULL CHECK (cost_type IN ('compliance', 'enforcement')),
            party TEXT,
            time_hours REAL,
            time_unit TEXT,
            time_display TEXT,
            money_cents INTEGER,
            money_display TEXT,
            assumed_time_value_cents INTEGER,
            assumed_time_value_display TEXT,
            frequency TEXT NOT NULL DEFAULT 'one_time',
            is_indefinite INTEGER NOT NULL DEFAULT 0,
            notes TEXT,
            FOREIGN KEY (legislation_id) REFERENCES legislation(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_legislation_jurisdiction ON legislation(jurisdiction);
        CREATE INDEX IF NOT EXISTS idx_legislation_date_enacted ON legislation(date_enacted);
        CREATE INDEX IF NOT EXISTS idx_legislation_analysis_status ON legislation(analysis_status);
        CREATE INDEX IF NOT EXISTS idx_legislation_type ON legislation(type);
        CREATE INDEX IF NOT EXISTS idx_costs_legislation_id ON costs(legislation_id);
        CREATE INDEX IF NOT EXISTS idx_costs_cost_type ON costs(cost_type);
        CREATE INDEX IF NOT EXISTS idx_costs_party ON costs(party);

        CREATE TRIGGER IF NOT EXISTS update_legislation_timestamp
        AFTER UPDATE ON legislation
        FOR EACH ROW
        BEGIN
            UPDATE legislation SET updated_at = datetime('now') WHERE id = OLD.id;
        END;
    """)


def read_corpus(path: Path, types: set[str], limit: Optional[int] = None) -> Iterator[dict]:
    """
    Stream records from the corpus JSONL file.

    Args:
        path: Path to the corpus.jsonl file
        types: Set of document types to include (empty = all)
        limit: Maximum number of records to yield

    Yields:
        Parsed JSON records matching the type filter
    """
    count = 0
    with open(path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            if limit and count >= limit:
                break

            try:
                record = json.loads(line)

                # Filter by type if specified
                if types and record.get('type') not in types:
                    continue

                count += 1
                yield record

            except json.JSONDecodeError as e:
                print(f"Warning: Malformed JSON at line {line_num}: {e}", file=sys.stderr)
                continue


def extract_title_from_citation(citation: str) -> str:
    """Extract a readable title from the citation field."""
    if not citation:
        return "Unknown"
    # Citation is usually in the form "Title (Jurisdiction)" or just "Title"
    # Remove trailing jurisdiction parenthetical if present
    if '(' in citation and citation.endswith(')'):
        return citation.rsplit('(', 1)[0].strip()
    return citation


def create_text_excerpt(text: str, max_length: int = EXCERPT_LENGTH) -> str:
    """Create a text excerpt for preview purposes."""
    if not text:
        return ""
    # Clean up whitespace and truncate
    text = ' '.join(text.split())
    if len(text) <= max_length:
        return text
    # Truncate at word boundary if possible
    truncated = text[:max_length]
    if ' ' in truncated:
        truncated = truncated.rsplit(' ', 1)[0]
    return truncated + "..."


def index_record(conn: sqlite3.Connection, record: dict) -> bool:
    """
    Insert or update a single legislation record.

    Returns:
        True if record was inserted, False if updated
    """
    version_id = record.get('version_id', '')
    if not version_id:
        return False

    citation = record.get('citation', '')
    title = extract_title_from_citation(citation) or version_id

    # Map corpus fields to database schema
    data = {
        'id': version_id,
        'title': title,
        'jurisdiction': record.get('jurisdiction', 'unknown'),
        'type': record.get('type', 'other'),
        'date_enacted': record.get('date'),  # Corpus uses 'date' field
        'citation': citation,
        'source_url': record.get('url', ''),
        'text_excerpt': create_text_excerpt(record.get('text', '')),
        'topics': '[]',  # Topics will be extracted by analysis pipeline
        'analysis_status': 'pending',
    }

    conn.execute("""
        INSERT INTO legislation (
            id, title, jurisdiction, type, date_enacted, citation,
            source_url, text_excerpt, topics, analysis_status
        ) VALUES (
            :id, :title, :jurisdiction, :type, :date_enacted, :citation,
            :source_url, :text_excerpt, :topics, :analysis_status
        )
        ON CONFLICT(id) DO UPDATE SET
            title = excluded.title,
            jurisdiction = excluded.jurisdiction,
            type = excluded.type,
            date_enacted = excluded.date_enacted,
            citation = excluded.citation,
            source_url = excluded.source_url,
            text_excerpt = excluded.text_excerpt
    """, data)

    return True


def main():
    parser = argparse.ArgumentParser(description="Index corpus into SQLite database")
    parser.add_argument('--limit', type=int, help="Limit number of records to process")
    parser.add_argument('--types', default='primary_legislation,secondary_legislation',
                        help="Comma-separated document types to include")
    parser.add_argument('--all-types', action='store_true',
                        help="Include all document types")
    parser.add_argument('--db', type=Path, default=DEFAULT_DB_PATH,
                        help="Path to SQLite database")
    parser.add_argument('--corpus', type=Path, default=DEFAULT_CORPUS_PATH,
                        help="Path to corpus JSONL file")
    args = parser.parse_args()

    # Parse document types filter
    if args.all_types:
        types_filter = set()
    else:
        types_filter = set(t.strip() for t in args.types.split(','))

    # Verify corpus exists
    if not args.corpus.exists():
        print(f"Error: Corpus file not found: {args.corpus}", file=sys.stderr)
        sys.exit(1)

    # Create database directory if needed
    args.db.parent.mkdir(parents=True, exist_ok=True)

    # Connect to database
    conn = sqlite3.connect(args.db)
    create_tables(conn)

    print(f"Indexing corpus: {args.corpus}")
    print(f"Database: {args.db}")
    print(f"Types filter: {types_filter or 'all'}")
    if args.limit:
        print(f"Limit: {args.limit} records")
    print()

    # Process records
    start_time = datetime.now()
    indexed = 0
    errors = 0

    try:
        for record in read_corpus(args.corpus, types_filter, args.limit):
            try:
                if index_record(conn, record):
                    indexed += 1

                    # Progress reporting
                    if indexed % 1000 == 0:
                        elapsed = (datetime.now() - start_time).total_seconds()
                        rate = indexed / elapsed if elapsed > 0 else 0
                        print(f"  Indexed {indexed:,} records ({rate:.1f}/sec)")
                        conn.commit()  # Periodic commit for large imports

            except Exception as e:
                errors += 1
                if errors <= 10:
                    print(f"Warning: Error indexing record: {e}", file=sys.stderr)
                elif errors == 11:
                    print("Warning: Suppressing further error messages...", file=sys.stderr)

    except KeyboardInterrupt:
        print("\nInterrupted by user")

    # Final commit
    conn.commit()

    # Summary
    elapsed = (datetime.now() - start_time).total_seconds()
    print()
    print(f"Indexing complete!")
    print(f"  Records indexed: {indexed:,}")
    print(f"  Errors: {errors}")
    print(f"  Time: {elapsed:.1f} seconds")
    print(f"  Rate: {indexed / elapsed:.1f} records/second" if elapsed > 0 else "")

    # Verify database
    cursor = conn.execute("SELECT COUNT(*) FROM legislation")
    total = cursor.fetchone()[0]
    print(f"  Total records in database: {total:,}")

    conn.close()


if __name__ == '__main__':
    main()
