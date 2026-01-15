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
    --retries N         Number of retry attempts for transient failures (default: 3)
    --retry-failed      Re-analyze previously failed legislation
    --workers N         Number of parallel workers (default: 1)
"""

import argparse
import json
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from datetime import datetime
from typing import Optional
from multiprocessing import Pool, cpu_count
from dataclasses import dataclass
import re
import os


class RetryableError(Exception):
    """
    Error that should trigger a retry (network issues, timeouts, rate limits).

    WHY: We want to distinguish between transient failures that may succeed on retry
    (network timeout, rate limit) vs permanent failures (invalid input, parsing errors).
    """
    pass


class NonRetryableError(Exception):
    """
    Error that should NOT be retried (invalid response, parsing failures).

    WHY: Some errors won't be fixed by retrying - bad input, malformed responses, etc.
    Retrying these wastes time and API calls.
    """
    pass

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "legislation.db"
CORPUS_PATH = PROJECT_ROOT / "data" / "corpus" / "corpus.jsonl"
CORPUS_INDEX_PATH = PROJECT_ROOT / "data" / "corpus" / "corpus_index.json"
PROMPT_PATH = PROJECT_ROOT / "analysis" / "prompts" / "cost_extraction.md"
SCHEMA_PATH = PROJECT_ROOT / "analysis" / "prompts" / "cost_schema.json"

# Global corpus index (loaded once at startup for O(1) lookups)
_corpus_index: Optional[dict] = None

# Token limit for Claude context (stay under 50% saturation)
MAX_TEXT_CHARS = 100_000  # ~25k tokens, well under the limit

# SQLite timeout for concurrent access (seconds)
# WHY: When multiple workers write to the database, locks may occur.
# A 30-second timeout prevents failures during brief contention.
DB_TIMEOUT = 30


@dataclass
class WorkerConfig:
    """
    Configuration passed to each worker process.

    WHY: Worker processes are forked and need their own database connections.
    This dataclass holds the configuration each worker needs to initialize.
    """
    db_path: Path
    max_retries: int
    prompt_template: str


# Global worker config (set by worker_init)
_worker_config: Optional[WorkerConfig] = None
_worker_conn: Optional[sqlite3.Connection] = None

# Validation constants
VALID_PARTIES = {'citizen', 'business', 'small_business', 'large_business', 'government', 'nonprofit'}
VALID_FREQUENCIES = {'one_time', 'per_transaction', 'daily', 'weekly', 'monthly', 'quarterly', 'annually', 'as_needed'}
VALID_TIME_UNITS = {'minutes', 'hours', 'days', 'weeks', 'months', 'years'}
VALID_CONFIDENCE = {'high', 'medium', 'low'}
VALID_REFERENCE_TYPES = {'definition', 'requirement', 'amendment', 'penalty'}


def load_schema() -> dict:
    """Load the JSON schema for validation."""
    with open(SCHEMA_PATH, 'r') as f:
        return json.load(f)


def validate_analysis(analysis: dict) -> list[str]:
    """
    Validate Claude's analysis output against expected schema.

    WHY: Claude may produce malformed or inconsistent responses. Validating ensures
    data integrity before writing to the database. Returns list of validation errors.
    """
    errors = []

    # Required top-level fields
    required_fields = ['legislation_summary', 'topics', 'has_compliance_costs',
                       'compliance_costs', 'has_enforcement_costs', 'referenced_legislation', 'confidence']
    for field in required_fields:
        if field not in analysis:
            errors.append(f"Missing required field: {field}")

    # Validate topics
    topics = analysis.get('topics', [])
    if not isinstance(topics, list):
        errors.append("topics must be a list")
    elif len(topics) < 1:
        errors.append("topics must have at least 1 item")
    elif len(topics) > 5:
        errors.append("topics must have at most 5 items")

    # Validate confidence
    confidence = analysis.get('confidence')
    if confidence and confidence not in VALID_CONFIDENCE:
        errors.append(f"Invalid confidence: {confidence} (must be one of {VALID_CONFIDENCE})")

    # Validate compliance costs
    compliance_costs = analysis.get('compliance_costs', [])
    if not isinstance(compliance_costs, list):
        errors.append("compliance_costs must be a list")
    else:
        for i, cost in enumerate(compliance_costs):
            prefix = f"compliance_costs[{i}]"

            # Party
            party = cost.get('party')
            if party and party not in VALID_PARTIES:
                errors.append(f"{prefix}.party '{party}' not in {VALID_PARTIES}")

            # Frequency
            frequency = cost.get('frequency')
            if frequency and frequency not in VALID_FREQUENCIES:
                errors.append(f"{prefix}.frequency '{frequency}' not in {VALID_FREQUENCIES}")

            # Time
            time_data = cost.get('time')
            if time_data:
                if not isinstance(time_data, dict):
                    errors.append(f"{prefix}.time must be an object or null")
                else:
                    unit = time_data.get('unit')
                    if unit and unit not in VALID_TIME_UNITS:
                        errors.append(f"{prefix}.time.unit '{unit}' not in {VALID_TIME_UNITS}")
                    amount = time_data.get('amount')
                    if amount is not None and (not isinstance(amount, (int, float)) or amount < 0):
                        errors.append(f"{prefix}.time.amount must be a non-negative number")

            # Money
            money_data = cost.get('money')
            if money_data:
                if not isinstance(money_data, dict):
                    errors.append(f"{prefix}.money must be an object or null")
                else:
                    amount = money_data.get('amount_aud')
                    if amount is not None and (not isinstance(amount, (int, float)) or amount < 0):
                        errors.append(f"{prefix}.money.amount_aud must be a non-negative number")

    # Validate enforcement cost
    enforcement = analysis.get('enforcement_cost')
    if enforcement:
        prefix = "enforcement_cost"
        frequency = enforcement.get('frequency')
        if frequency and frequency not in VALID_FREQUENCIES:
            errors.append(f"{prefix}.frequency '{frequency}' not in {VALID_FREQUENCIES}")

        time_data = enforcement.get('time')
        if time_data and isinstance(time_data, dict):
            unit = time_data.get('unit')
            if unit and unit not in VALID_TIME_UNITS:
                errors.append(f"{prefix}.time.unit '{unit}' not in {VALID_TIME_UNITS}")

    # Validate referenced_legislation
    referenced = analysis.get('referenced_legislation', [])
    if not isinstance(referenced, list):
        errors.append("referenced_legislation must be a list")
    else:
        for i, ref in enumerate(referenced):
            prefix = f"referenced_legislation[{i}]"

            # Title is required
            if not ref.get('title'):
                errors.append(f"{prefix}.title is required")

            # Reference type is required and must be valid
            ref_type = ref.get('reference_type')
            if not ref_type:
                errors.append(f"{prefix}.reference_type is required")
            elif ref_type not in VALID_REFERENCE_TYPES:
                errors.append(f"{prefix}.reference_type '{ref_type}' not in {VALID_REFERENCE_TYPES}")

    return errors


def load_prompt_template() -> str:
    """Load the cost extraction prompt."""
    with open(PROMPT_PATH, 'r') as f:
        return f.read()


def load_corpus_index() -> dict:
    """
    Load the corpus byte-offset index for O(1) lookups.

    WHY: The corpus is 8.8GB. Without an index, each lookup scans the entire file (O(n)).
    With the index, we seek directly to the record's byte position (O(1)).
    """
    global _corpus_index

    if _corpus_index is not None:
        return _corpus_index

    if not CORPUS_INDEX_PATH.exists():
        print(f"WARNING: Corpus index not found at {CORPUS_INDEX_PATH}")
        print("Run 'python analysis/scripts/build_corpus_index.py' to create it.")
        print("Falling back to linear scan (slow)...")
        return {}

    with open(CORPUS_INDEX_PATH, 'r', encoding='utf-8') as f:
        _corpus_index = json.load(f)

    print(f"Loaded corpus index with {len(_corpus_index):,} entries")
    return _corpus_index


def get_legislation_text(version_id: str) -> Optional[str]:
    """
    Retrieve the full text for a legislation from the corpus.

    WHY: The database only stores excerpts. We need the full text for analysis.
    Uses byte-offset index for O(1) lookup if available, falls back to linear scan.
    """
    index = load_corpus_index()

    # O(1) lookup using index
    if version_id in index:
        byte_offset = index[version_id]
        with open(CORPUS_PATH, 'r', encoding='utf-8') as f:
            f.seek(byte_offset)
            line = f.readline()
            record = json.loads(line)
            return record.get('text', '')

    # Fallback: linear scan (slow, but works without index)
    # This path should rarely be taken once index is built
    print(f"  WARNING: {version_id} not in index, using linear scan...")
    with open(CORPUS_PATH, 'r', encoding='utf-8') as f:
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


def cleanup_text(text: str) -> tuple[str, list[str]]:
    """
    Clean up text to handle encoding issues and other edge cases.

    WHY: The corpus contains a small number of documents with encoding issues
    (replacement characters from bad source encoding). These can confuse Claude
    or cause output issues. Cleaning the text ensures consistent analysis.

    Returns:
        (cleaned_text, warnings_list)
    """
    warnings = []
    original_len = len(text)

    # Remove Unicode replacement characters (encoding artifacts)
    # These appear when the source had invalid UTF-8 sequences
    if '\ufffd' in text:
        count = text.count('\ufffd')
        text = text.replace('\ufffd', '')
        warnings.append(f"Removed {count} encoding replacement character(s)")

    # Normalize line endings to \n
    if '\r\n' in text:
        text = text.replace('\r\n', '\n')
    if '\r' in text:
        text = text.replace('\r', '\n')

    # Remove null bytes (rare but can occur in corrupted data)
    if '\x00' in text:
        count = text.count('\x00')
        text = text.replace('\x00', '')
        warnings.append(f"Removed {count} null byte(s)")

    # Collapse excessive whitespace (more than 3 consecutive newlines)
    while '\n\n\n\n' in text:
        text = text.replace('\n\n\n\n', '\n\n\n')

    # Strip leading/trailing whitespace
    text = text.strip()

    # Warn if text is very short (might be empty after cleanup)
    if len(text) < 100:
        warnings.append(f"Very short text ({len(text)} chars)")

    return text, warnings


def call_claude(legislation_text: str, citation: str, prompt_template: str) -> dict:
    """
    Call Claude CLI to analyze legislation.

    Returns:
        Parsed JSON response from Claude

    Raises:
        RetryableError: For transient failures (timeouts, network issues, rate limits)
        NonRetryableError: For permanent failures (parsing errors, invalid responses)
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
    try:
        result = subprocess.run(
            ['claude', '-p', full_prompt, '--output-format', 'json'],
            capture_output=True,
            text=True,
            timeout=120  # 2 minute timeout
        )
    except subprocess.TimeoutExpired:
        raise RetryableError("Claude CLI timed out after 120 seconds")
    except OSError as e:
        raise RetryableError(f"Failed to execute Claude CLI: {e}")

    # Check for rate limiting or transient errors
    if result.returncode != 0:
        stderr = result.stderr.lower()
        # Rate limiting and network errors are retryable
        if 'rate' in stderr or 'limit' in stderr or 'timeout' in stderr or 'connection' in stderr:
            raise RetryableError(f"Claude CLI transient error: {result.stderr}")
        # Other CLI errors are not retryable
        raise NonRetryableError(f"Claude CLI error: {result.stderr}")

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
        raise NonRetryableError(f"Failed to parse Claude response as JSON: {e}\nResponse: {result.stdout[:500]}")


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

    # Update legislation analysis status, topics, and referenced_legislation
    topics = analysis.get('topics', [])
    referenced_legislation = analysis.get('referenced_legislation', [])
    cursor.execute(
        "UPDATE legislation SET analysis_status = 'complete', topics = ?, referenced_legislation = ? WHERE id = ?",
        (json.dumps(topics), json.dumps(referenced_legislation), legislation_id)
    )

    conn.commit()


def worker_init(config: WorkerConfig) -> None:
    """
    Initialize a worker process with its own database connection.

    WHY: Each worker process needs its own SQLite connection because connections
    are not thread/process safe. This is called once when each worker starts.
    """
    global _worker_config, _worker_conn
    _worker_config = config
    _worker_conn = sqlite3.connect(config.db_path, timeout=DB_TIMEOUT)

    # Pre-load the corpus index in this process
    load_corpus_index()

    pid = os.getpid()
    print(f"[Worker {pid}] Initialized with database connection")


def worker_process_item(leg: dict) -> dict:
    """
    Process a single legislation item in a worker process.

    WHY: This function is designed to be called by multiprocessing.Pool.map().
    It processes one legislation record and returns a result summary.

    Args:
        leg: Dictionary with id, title, citation, jurisdiction

    Returns:
        Dictionary with: id, success, analyzed, error, validation_warnings
    """
    global _worker_config, _worker_conn

    if _worker_config is None or _worker_conn is None:
        return {
            'id': leg['id'],
            'success': False,
            'error': 'Worker not initialized'
        }

    pid = os.getpid()
    result = {
        'id': leg['id'],
        'success': False,
        'analyzed': False,
        'error': None,
        'validation_warnings': 0
    }

    print(f"[Worker {pid}] Analyzing: {leg['id']}")
    print(f"[Worker {pid}]   Title: {leg['title']}")

    try:
        # Get full text from corpus
        text = get_legislation_text(leg['id'])
        if not text:
            result['error'] = "Could not find text in corpus"
            # Mark as failed
            _worker_conn.execute(
                "UPDATE legislation SET analysis_status = 'failed' WHERE id = ?",
                (leg['id'],)
            )
            _worker_conn.commit()
            print(f"[Worker {pid}]   ERROR: {result['error']}")
            return result

        # Clean up text (encoding issues, normalization)
        text, cleanup_warnings = cleanup_text(text)
        for warn in cleanup_warnings:
            print(f"[Worker {pid}]   WARNING: {warn}")

        # Skip if text is too short after cleanup
        if len(text) < 50:
            result['error'] = f"Text too short after cleanup ({len(text)} chars)"
            _worker_conn.execute(
                "UPDATE legislation SET analysis_status = 'failed' WHERE id = ?",
                (leg['id'],)
            )
            _worker_conn.commit()
            print(f"[Worker {pid}]   ERROR: {result['error']}")
            return result

        # Truncate if needed
        text, was_truncated = truncate_text(text)
        if was_truncated:
            print(f"[Worker {pid}]   WARNING: Text truncated to {MAX_TEXT_CHARS:,} chars")

        # Call Claude for analysis (with retry)
        print(f"[Worker {pid}]   Calling Claude...")
        analysis = analyze_with_retry(
            text,
            leg['citation'] or leg['title'],
            _worker_config.prompt_template,
            max_retries=_worker_config.max_retries
        )

        # Validate the response
        validation_errors = validate_analysis(analysis)
        if validation_errors:
            print(f"[Worker {pid}]   VALIDATION WARNINGS:")
            for err in validation_errors[:5]:
                print(f"[Worker {pid}]     - {err}")
            if len(validation_errors) > 5:
                print(f"[Worker {pid}]     ... and {len(validation_errors) - 5} more")
            result['validation_warnings'] = len(validation_errors)

        # Save results
        save_analysis_to_db(_worker_conn, leg['id'], analysis)

        # Print summary
        print(f"[Worker {pid}]   Topics: {', '.join(analysis.get('topics', []))}")
        print(f"[Worker {pid}]   Confidence: {analysis.get('confidence', 'unknown')}")
        print(f"[Worker {pid}]   Compliance costs: {len(analysis.get('compliance_costs', []))}")
        print(f"[Worker {pid}]   Has enforcement cost: {analysis.get('has_enforcement_costs', False)}")

        result['success'] = True
        result['analyzed'] = True

    except NonRetryableError as e:
        result['error'] = f"Non-retryable: {e}"
        print(f"[Worker {pid}]   ERROR (non-retryable): {e}")
        _worker_conn.execute(
            "UPDATE legislation SET analysis_status = 'failed' WHERE id = ?",
            (leg['id'],)
        )
        _worker_conn.commit()

    except (RetryableError, Exception) as e:
        result['error'] = str(e)
        print(f"[Worker {pid}]   ERROR: {e}")
        _worker_conn.execute(
            "UPDATE legislation SET analysis_status = 'failed' WHERE id = ?",
            (leg['id'],)
        )
        _worker_conn.commit()

    print(f"[Worker {pid}]   Done")
    return result


def analyze_with_retry(legislation_text: str, citation: str, prompt_template: str,
                       max_retries: int = 3) -> dict:
    """
    Call Claude with retry logic for transient failures.

    WHY: Network issues and rate limits are common when processing thousands of documents.
    Automatic retry with exponential backoff improves reliability without manual intervention.

    Args:
        legislation_text: The text to analyze
        citation: Citation for the legislation
        prompt_template: The prompt template to use
        max_retries: Maximum retry attempts (default: 3)

    Returns:
        Parsed JSON response from Claude

    Raises:
        NonRetryableError: If the error is not retryable
        RetryableError: If all retry attempts failed
    """
    last_error = None

    for attempt in range(max_retries + 1):
        try:
            return call_claude(legislation_text, citation, prompt_template)
        except RetryableError as e:
            last_error = e
            if attempt < max_retries:
                # Exponential backoff: 2, 4, 8 seconds
                wait_time = 2 ** (attempt + 1)
                print(f"    Retry {attempt + 1}/{max_retries} after {wait_time}s: {e}")
                time.sleep(wait_time)
            else:
                print(f"    All {max_retries} retries exhausted")
        except NonRetryableError:
            # Don't retry non-retryable errors
            raise

    # If we get here, all retries failed
    raise RetryableError(f"All {max_retries} retry attempts failed. Last error: {last_error}")


def get_pending_legislation(conn: sqlite3.Connection, limit: int = 10,
                            jurisdiction: Optional[str] = None,
                            legislation_id: Optional[str] = None,
                            retry_failed: bool = False) -> list[dict]:
    """
    Get legislation pending analysis.

    Args:
        conn: Database connection
        limit: Maximum records to return
        jurisdiction: Optional jurisdiction filter
        legislation_id: Optional specific ID to analyze
        retry_failed: If True, include previously failed analyses
    """
    cursor = conn.cursor()

    if legislation_id:
        cursor.execute(
            'SELECT id, title, citation, jurisdiction FROM legislation WHERE id = ?',
            (legislation_id,)
        )
    elif retry_failed:
        # Include failed analyses for retry
        status_filter = "IN ('pending', 'failed')"
        if jurisdiction:
            cursor.execute(
                f'''SELECT id, title, citation, jurisdiction FROM legislation
                   WHERE analysis_status {status_filter} AND jurisdiction = ?
                   LIMIT ?''',
                (jurisdiction, limit)
            )
        else:
            cursor.execute(
                f'''SELECT id, title, citation, jurisdiction FROM legislation
                   WHERE analysis_status {status_filter}
                   LIMIT ?''',
                (limit,)
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
    parser.add_argument('--retries', type=int, default=3, help="Number of retry attempts for transient failures")
    parser.add_argument('--retry-failed', action='store_true', help="Re-analyze previously failed legislation")
    parser.add_argument('--workers', type=int, default=1,
                        help=f"Number of parallel workers (default: 1, max recommended: {cpu_count()})")
    args = parser.parse_args()

    # Validate workers
    if args.workers < 1:
        print("ERROR: --workers must be at least 1")
        sys.exit(1)
    if args.workers > cpu_count() * 2:
        print(f"WARNING: Using {args.workers} workers exceeds 2x CPU count ({cpu_count()})")
        print("This may cause resource contention. Consider reducing --workers.")

    # Load prompt template
    prompt_template = load_prompt_template()

    # Connect to database
    conn = sqlite3.connect(args.db)

    # Get pending legislation
    pending = get_pending_legislation(
        conn,
        limit=args.limit,
        jurisdiction=args.jurisdiction,
        legislation_id=args.id,
        retry_failed=args.retry_failed
    )

    if not pending:
        if args.retry_failed:
            print("No pending or failed legislation to analyze.")
        else:
            print("No pending legislation to analyze.")
        conn.close()
        return

    print(f"Found {len(pending)} legislation to analyze")
    if args.retry_failed:
        print("(including previously failed analyses)")
    print()

    if args.dry_run:
        for leg in pending:
            print(f"Would analyze: {leg['id']}")
            print(f"  Title: {leg['title']}")
            print(f"  Jurisdiction: {leg['jurisdiction']}")
            print()
        print(f"Would use {args.workers} worker(s)")
        conn.close()
        return

    # Close main connection - workers will open their own
    conn.close()

    # Process legislation
    analyzed = 0
    errors = 0
    validation_warnings = 0

    if args.workers > 1:
        # Parallel processing with multiprocessing Pool
        print(f"Starting {args.workers} parallel workers...")
        print()

        # Create worker configuration
        config = WorkerConfig(
            db_path=args.db,
            max_retries=args.retries,
            prompt_template=prompt_template
        )

        # Use fork start method for faster worker init (Unix only)
        # Workers share the corpus index loaded in the main process
        with Pool(
            processes=args.workers,
            initializer=worker_init,
            initargs=(config,)
        ) as pool:
            # Process all items in parallel using imap for ordered results
            # This allows us to see progress as items complete
            results = pool.map(worker_process_item, pending)

        # Aggregate results
        for result in results:
            if result.get('analyzed'):
                analyzed += 1
            if result.get('error'):
                errors += 1
            validation_warnings += result.get('validation_warnings', 0)

    else:
        # Sequential processing (original behavior for backwards compatibility)
        # Re-open connection for single-worker mode
        conn = sqlite3.connect(args.db, timeout=DB_TIMEOUT)

        for leg in pending:
            print(f"Analyzing: {leg['id']}")
            print(f"  Title: {leg['title']}")

            try:
                # Get full text from corpus
                text = get_legislation_text(leg['id'])
                if not text:
                    print(f"  ERROR: Could not find text in corpus")
                    conn.execute(
                        "UPDATE legislation SET analysis_status = 'failed' WHERE id = ?",
                        (leg['id'],)
                    )
                    conn.commit()
                    errors += 1
                    continue

                # Clean up text (encoding issues, normalization)
                text, cleanup_warnings = cleanup_text(text)
                for warn in cleanup_warnings:
                    print(f"  WARNING: {warn}")

                # Skip if text is too short after cleanup
                if len(text) < 50:
                    print(f"  ERROR: Text too short after cleanup ({len(text)} chars)")
                    conn.execute(
                        "UPDATE legislation SET analysis_status = 'failed' WHERE id = ?",
                        (leg['id'],)
                    )
                    conn.commit()
                    errors += 1
                    continue

                # Truncate if needed
                text, was_truncated = truncate_text(text)
                if was_truncated:
                    print(f"  WARNING: Text truncated to {MAX_TEXT_CHARS:,} chars")

                # Call Claude for analysis (with retry)
                print(f"  Calling Claude...")
                analysis = analyze_with_retry(text, leg['citation'] or leg['title'],
                                              prompt_template, max_retries=args.retries)

                # Validate the response
                validation_errors_list = validate_analysis(analysis)
                if validation_errors_list:
                    print(f"  VALIDATION WARNINGS:")
                    for err in validation_errors_list[:5]:  # Show first 5
                        print(f"    - {err}")
                    if len(validation_errors_list) > 5:
                        print(f"    ... and {len(validation_errors_list) - 5} more")
                    validation_warnings += 1
                    # Still save the analysis - warnings don't block, just inform

                # Save results
                save_analysis_to_db(conn, leg['id'], analysis)

                # Print summary
                print(f"  Topics: {', '.join(analysis.get('topics', []))}")
                print(f"  Confidence: {analysis.get('confidence', 'unknown')}")
                print(f"  Compliance costs: {len(analysis.get('compliance_costs', []))}")
                print(f"  Has enforcement cost: {analysis.get('has_enforcement_costs', False)}")

                analyzed += 1

            except NonRetryableError as e:
                print(f"  ERROR (non-retryable): {e}")
                # Mark as failed - won't retry
                conn.execute(
                    "UPDATE legislation SET analysis_status = 'failed' WHERE id = ?",
                    (leg['id'],)
                )
                conn.commit()
                errors += 1

            except (RetryableError, Exception) as e:
                print(f"  ERROR: {e}")
                # Mark as failed - may be retried with --retry-failed
                conn.execute(
                    "UPDATE legislation SET analysis_status = 'failed' WHERE id = ?",
                    (leg['id'],)
                )
                conn.commit()
                errors += 1

            print()

        conn.close()

    # Summary
    print()
    print("=" * 50)
    print(f"Workers: {args.workers}")
    print(f"Analyzed: {analyzed}")
    print(f"Errors: {errors}")
    if validation_warnings:
        print(f"Validation warnings: {validation_warnings}")

    # Show database stats
    conn = sqlite3.connect(args.db, timeout=DB_TIMEOUT)
    cursor = conn.cursor()
    cursor.execute("SELECT analysis_status, COUNT(*) FROM legislation GROUP BY analysis_status")
    print("\nDatabase status:")
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[1]:,}")
    conn.close()


if __name__ == '__main__':
    main()
