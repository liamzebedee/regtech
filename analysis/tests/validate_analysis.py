#!/usr/bin/env python3
"""
Analysis Quality Validation - Tests that cost analysis produces expected results.

WHY: Without ground truth validation, we can't know if the analysis pipeline is producing
accurate results. This script tests analysis output against known-cost legislation where
the expected outcomes are documented.

Usage:
    python analysis/tests/validate_analysis.py [--run-analysis] [--verbose]

Options:
    --run-analysis   Run analysis on test cases before validation (requires Claude CLI)
    --verbose        Show detailed output for each test case
    --db PATH        Path to database (default: data/legislation.db)
"""

import argparse
import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Optional


PROJECT_ROOT = Path(__file__).parent.parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "legislation.db"
TEST_CASES_PATH = Path(__file__).parent / "test_cases.json"


@dataclass
class ValidationResult:
    """Result of validating a single test case."""
    test_id: str
    test_name: str
    passed: bool
    errors: list[str]
    warnings: list[str]


def load_test_cases() -> list[dict]:
    """Load test cases from JSON file."""
    with open(TEST_CASES_PATH, 'r') as f:
        data = json.load(f)
    return data.get('test_cases', [])


def get_analysis_for_legislation(conn: sqlite3.Connection, legislation_id: str) -> Optional[dict]:
    """
    Get the analysis results for a piece of legislation from the database.

    Returns None if legislation not found or not analyzed.
    """
    cursor = conn.cursor()

    # Get legislation record
    cursor.execute(
        "SELECT id, title, analysis_status FROM legislation WHERE id = ?",
        (legislation_id,)
    )
    leg_row = cursor.fetchone()
    if not leg_row:
        return None

    leg_id, title, status = leg_row

    if status != 'complete':
        return {'id': leg_id, 'title': title, 'status': status, 'costs': []}

    # Get costs
    cursor.execute(
        """SELECT cost_type, party, time_hours, time_display, money_cents,
                  money_display, is_indefinite, notes
           FROM costs WHERE legislation_id = ?""",
        (legislation_id,)
    )

    costs = []
    for row in cursor.fetchall():
        costs.append({
            'cost_type': row[0],
            'party': row[1],
            'time_hours': row[2],
            'time_display': row[3],
            'money_cents': row[4],
            'money_display': row[5],
            'is_indefinite': bool(row[6]),
            'notes': row[7]
        })

    return {
        'id': leg_id,
        'title': title,
        'status': status,
        'costs': costs
    }


def validate_test_case(conn: sqlite3.Connection, test_case: dict, verbose: bool = False) -> ValidationResult:
    """
    Validate a single test case against the database.

    Returns a ValidationResult with pass/fail status and any errors.
    """
    test_id = test_case['id']
    test_name = test_case.get('name', test_id)
    expected = test_case.get('expected', {})
    errors = []
    warnings = []

    # Get analysis from database
    analysis = get_analysis_for_legislation(conn, test_id)

    if analysis is None:
        errors.append(f"Legislation not found in database")
        return ValidationResult(test_id, test_name, False, errors, warnings)

    if analysis['status'] != 'complete':
        errors.append(f"Analysis not complete (status: {analysis['status']})")
        return ValidationResult(test_id, test_name, False, errors, warnings)

    costs = analysis['costs']
    compliance_costs = [c for c in costs if c['cost_type'] == 'compliance']
    enforcement_costs = [c for c in costs if c['cost_type'] == 'enforcement']

    # Validate has_compliance_costs
    if 'has_compliance_costs' in expected:
        actual_has = len(compliance_costs) > 0
        if actual_has != expected['has_compliance_costs']:
            errors.append(
                f"has_compliance_costs: expected {expected['has_compliance_costs']}, got {actual_has} "
                f"({len(compliance_costs)} compliance costs)"
            )

    # Validate has_enforcement_costs
    if 'has_enforcement_costs' in expected:
        actual_has = len(enforcement_costs) > 0
        if actual_has != expected['has_enforcement_costs']:
            errors.append(
                f"has_enforcement_costs: expected {expected['has_enforcement_costs']}, got {actual_has} "
                f"({len(enforcement_costs)} enforcement costs)"
            )

    # Validate min/max compliance costs
    if 'min_compliance_costs' in expected:
        if len(compliance_costs) < expected['min_compliance_costs']:
            errors.append(
                f"min_compliance_costs: expected at least {expected['min_compliance_costs']}, "
                f"got {len(compliance_costs)}"
            )

    if 'max_compliance_costs' in expected:
        if len(compliance_costs) > expected['max_compliance_costs']:
            errors.append(
                f"max_compliance_costs: expected at most {expected['max_compliance_costs']}, "
                f"got {len(compliance_costs)}"
            )

    # Validate expected_parties
    if 'expected_parties' in expected:
        actual_parties = set(c['party'] for c in compliance_costs if c['party'])
        expected_parties = set(expected['expected_parties'])
        missing_parties = expected_parties - actual_parties
        if missing_parties:
            errors.append(
                f"expected_parties: missing {missing_parties}, found {actual_parties}"
            )

    # Validate should_have_indefinite
    if 'should_have_indefinite' in expected:
        has_indefinite = any(c['is_indefinite'] for c in costs)
        if has_indefinite != expected['should_have_indefinite']:
            errors.append(
                f"should_have_indefinite: expected {expected['should_have_indefinite']}, got {has_indefinite}"
            )

    passed = len(errors) == 0
    return ValidationResult(test_id, test_name, passed, errors, warnings)


def run_analysis_for_case(test_id: str, db_path: Path) -> bool:
    """Run analysis for a specific test case."""
    print(f"  Running analysis for {test_id}...")
    result = subprocess.run(
        ['python', str(PROJECT_ROOT / 'analysis' / 'scripts' / 'analyze_legislation.py'),
         '--id', test_id, '--db', str(db_path)],
        capture_output=True,
        text=True
    )
    return result.returncode == 0


def main():
    parser = argparse.ArgumentParser(description="Validate analysis quality against test cases")
    parser.add_argument('--run-analysis', action='store_true',
                        help="Run analysis on test cases before validation")
    parser.add_argument('--verbose', '-v', action='store_true',
                        help="Show detailed output")
    parser.add_argument('--db', type=Path, default=DEFAULT_DB_PATH,
                        help="Database path")
    args = parser.parse_args()

    # Load test cases
    test_cases = load_test_cases()
    print(f"Loaded {len(test_cases)} test cases")
    print()

    # Connect to database
    conn = sqlite3.connect(args.db)

    # Optionally run analysis first
    if args.run_analysis:
        print("Running analysis on test cases...")
        for case in test_cases:
            # Check if already analyzed
            analysis = get_analysis_for_legislation(conn, case['id'])
            if analysis and analysis['status'] == 'complete':
                print(f"  Skipping {case['id']} (already analyzed)")
                continue
            run_analysis_for_case(case['id'], args.db)
        print()

    # Validate each test case
    results = []
    for case in test_cases:
        result = validate_test_case(conn, case, args.verbose)
        results.append(result)

        # Print result
        status = "PASS" if result.passed else "FAIL"
        print(f"[{status}] {result.test_name}")

        if args.verbose or not result.passed:
            for error in result.errors:
                print(f"       ERROR: {error}")
            for warning in result.warnings:
                print(f"       WARNING: {warning}")

    conn.close()

    # Summary
    print()
    print("=" * 60)
    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)
    print(f"Passed: {passed}/{len(results)}")
    print(f"Failed: {failed}/{len(results)}")

    # Exit with error if any failed
    if failed > 0:
        sys.exit(1)


if __name__ == '__main__':
    main()
