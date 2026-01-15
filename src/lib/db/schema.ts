/**
 * SQLite Database Schema
 *
 * WHY: SQLite provides a single-file database that can be committed or deployed
 * with the app, avoiding external database dependencies. The schema is designed
 * to support efficient querying for browsing, filtering, and aggregation of
 * legislation and costs.
 */

import Database from 'better-sqlite3';
import type { AnalysisStatus, Jurisdiction } from '../types/cost';

/**
 * Initialize the database with required tables and indexes.
 * This function is idempotent - safe to call multiple times.
 */
export function initializeDatabase(dbPath: string): Database.Database {
  const db = new Database(dbPath);

  // Enable WAL mode for better concurrent read/write performance
  db.pragma('journal_mode = WAL');

  // Create legislation table
  db.exec(`
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
    )
  `);

  // Create costs table
  db.exec(`
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
    )
  `);

  // Create indexes for common query patterns
  db.exec(`
    CREATE INDEX IF NOT EXISTS idx_legislation_jurisdiction ON legislation(jurisdiction);
    CREATE INDEX IF NOT EXISTS idx_legislation_date_enacted ON legislation(date_enacted);
    CREATE INDEX IF NOT EXISTS idx_legislation_analysis_status ON legislation(analysis_status);
    CREATE INDEX IF NOT EXISTS idx_legislation_type ON legislation(type);
    CREATE INDEX IF NOT EXISTS idx_costs_legislation_id ON costs(legislation_id);
    CREATE INDEX IF NOT EXISTS idx_costs_cost_type ON costs(cost_type);
    CREATE INDEX IF NOT EXISTS idx_costs_party ON costs(party);
  `);

  // Create trigger to auto-update updated_at on legislation changes
  db.exec(`
    CREATE TRIGGER IF NOT EXISTS update_legislation_timestamp
    AFTER UPDATE ON legislation
    FOR EACH ROW
    BEGIN
      UPDATE legislation SET updated_at = datetime('now') WHERE id = OLD.id;
    END
  `);

  return db;
}

/**
 * Row type for legislation table (as stored in DB).
 */
export interface LegislationRow {
  id: string;
  title: string;
  jurisdiction: Jurisdiction;
  type: string;
  date_enacted: string | null;
  date_repealed: string | null;
  citation: string | null;
  source_url: string | null;
  text_path: string | null;
  text_excerpt: string | null;
  topics: string; // JSON array stored as string
  analysis_status: AnalysisStatus;
  created_at: string;
  updated_at: string;
  // Analysis metadata (added for long document handling)
  document_length: number | null;        // Original document length in characters
  analysis_coverage: number | null;      // Portion of cost-relevant content analyzed (0.0-1.0)
  analysis_chunks: number | null;        // Number of chunks used for analysis
  was_truncated: number | null;          // 1 if document was truncated, 0 otherwise
}

/**
 * Row type for costs table (as stored in DB).
 */
export interface CostRow {
  id: number;
  legislation_id: string;
  cost_type: 'compliance' | 'enforcement';
  party: string | null;
  time_hours: number | null;
  time_unit: string | null;
  time_display: string | null;
  money_cents: number | null;
  money_display: string | null;
  assumed_time_value_cents: number | null;
  assumed_time_value_display: string | null;
  frequency: string;
  is_indefinite: number; // SQLite uses 0/1 for boolean
  notes: string | null;
}

/**
 * Input type for inserting/updating legislation (subset of fields).
 */
export interface LegislationInput {
  id: string;
  title: string;
  jurisdiction: string;
  type?: string;
  dateEnacted?: string;
  dateRepealed?: string;
  citation?: string;
  sourceUrl?: string;
  textPath?: string;
  textExcerpt?: string;
  topics?: string[];
  analysisStatus?: AnalysisStatus;
  // Analysis metadata (for long document handling)
  documentLength?: number;
  analysisCoverage?: number;
  analysisChunks?: number;
  wasTruncated?: boolean;
}

/**
 * Input type for inserting costs.
 */
export interface CostInput {
  legislationId: string;
  costType: 'compliance' | 'enforcement';
  party?: string;
  timeHours?: number;
  timeUnit?: string;
  timeDisplay?: string;
  moneyCents?: number;
  moneyDisplay?: string;
  assumedTimeValueCents?: number;
  assumedTimeValueDisplay?: string;
  frequency?: string;
  isIndefinite?: boolean;
  notes?: string;
}
