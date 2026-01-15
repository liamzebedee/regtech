#!/usr/bin/env python3
"""
Build a byte-offset index of the corpus JSONL file for O(1) lookups.

WHY: The corpus is 8.8GB with 232,560 records. Without an index, retrieving a single
document requires scanning the entire file (O(n)). With a byte-offset index, we can
seek directly to any record's position (O(1)). This is critical for:
1. Analysis pipeline efficiency - each lookup takes milliseconds instead of minutes
2. Parallelization - multiple workers can read from the same file without conflicts
3. Website performance - if we ever need to fetch full text on demand

The index maps version_id -> byte offset in the JSONL file.
"""

import json
import sys
from pathlib import Path
from typing import Optional

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
CORPUS_PATH = PROJECT_ROOT / "data" / "corpus" / "corpus.jsonl"
INDEX_PATH = PROJECT_ROOT / "data" / "corpus" / "corpus_index.json"


def build_index(
    corpus_path: Path = CORPUS_PATH,
    index_path: Path = INDEX_PATH,
    filter_types: Optional[set] = None
) -> dict:
    """
    Build a byte-offset index of the corpus JSONL file.

    Args:
        corpus_path: Path to the JSONL file
        index_path: Path where the index will be saved
        filter_types: If provided, only index documents of these types

    Returns:
        Dict mapping version_id to byte offset

    WHY separate filter_types: The corpus contains 189k court decisions that we don't
    need for cost analysis. Filtering them out saves index space and lookup time.
    """
    index = {}
    total_records = 0
    indexed_records = 0
    errors = 0

    print(f"Building index from: {corpus_path}")
    print(f"Filter types: {filter_types or 'all'}")

    with open(corpus_path, 'r', encoding='utf-8') as f:
        while True:
            # Record the byte position BEFORE reading the line
            byte_offset = f.tell()
            line = f.readline()

            if not line:
                break  # EOF

            total_records += 1

            try:
                # Only parse the fields we need for filtering
                record = json.loads(line)
                version_id = record.get('version_id')
                doc_type = record.get('type')

                if not version_id:
                    errors += 1
                    if errors <= 10:
                        print(f"  Warning: Missing version_id at offset {byte_offset}")
                    continue

                # Filter by type if specified
                if filter_types and doc_type not in filter_types:
                    continue

                index[version_id] = byte_offset
                indexed_records += 1

            except json.JSONDecodeError as e:
                errors += 1
                if errors <= 10:
                    print(f"  Warning: JSON decode error at offset {byte_offset}: {e}")
                continue

            # Progress reporting
            if total_records % 50000 == 0:
                print(f"  Processed {total_records:,} records, indexed {indexed_records:,}...")

    # Save the index
    print(f"\nSaving index to: {index_path}")
    with open(index_path, 'w', encoding='utf-8') as f:
        json.dump(index, f, indent=None, separators=(',', ':'))

    # Calculate file size
    index_size_mb = index_path.stat().st_size / (1024 * 1024)

    print(f"\nIndex built successfully:")
    print(f"  Total records scanned: {total_records:,}")
    print(f"  Records indexed: {indexed_records:,}")
    print(f"  Errors: {errors:,}")
    print(f"  Index file size: {index_size_mb:.1f} MB")

    return index


def load_index(index_path: Path = INDEX_PATH) -> dict:
    """
    Load the corpus index from disk.

    WHY cache this: The index is ~5MB and loading it once at startup is much
    faster than rebuilding or loading per-lookup.
    """
    if not index_path.exists():
        raise FileNotFoundError(
            f"Corpus index not found at {index_path}. "
            "Run 'python analysis/scripts/build_corpus_index.py' first."
        )

    with open(index_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_text_by_offset(corpus_path: Path, byte_offset: int) -> str:
    """
    Retrieve the text field from a JSONL record at a specific byte offset.

    WHY seek + read: This is O(1) - we jump directly to the record position
    regardless of file size. No scanning required.
    """
    with open(corpus_path, 'r', encoding='utf-8') as f:
        f.seek(byte_offset)
        line = f.readline()
        record = json.loads(line)
        return record.get('text', '')


def get_record_by_offset(corpus_path: Path, byte_offset: int) -> dict:
    """
    Retrieve the full record from a JSONL at a specific byte offset.

    WHY expose full record: Sometimes we need more than just text - e.g.,
    jurisdiction, date, citation for display or validation.
    """
    with open(corpus_path, 'r', encoding='utf-8') as f:
        f.seek(byte_offset)
        line = f.readline()
        return json.loads(line)


def main():
    """Build the corpus index with default filtering."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Build a byte-offset index of the corpus JSONL file"
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help="Index all document types (default: only legislation)"
    )
    parser.add_argument(
        '--corpus',
        type=Path,
        default=CORPUS_PATH,
        help="Path to corpus JSONL file"
    )
    parser.add_argument(
        '--output',
        type=Path,
        default=INDEX_PATH,
        help="Path for output index file"
    )
    args = parser.parse_args()

    # Default: only index legislation (not court decisions)
    # This reduces index size and improves lookup relevance
    if args.all:
        filter_types = None
    else:
        filter_types = {'primary_legislation', 'secondary_legislation', 'bill'}

    build_index(
        corpus_path=args.corpus,
        index_path=args.output,
        filter_types=filter_types
    )


if __name__ == '__main__':
    main()
