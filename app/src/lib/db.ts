/**
 * Database Connection for Next.js
 *
 * WHY: Centralized database access for the web application.
 * Uses the same schema and repository as the analysis pipeline.
 */

import Database from "better-sqlite3";
import path from "path";

// Singleton database connection
let db: Database.Database | null = null;

/**
 * Get or create database connection.
 * Database file is located at data/legislation.db relative to project root.
 *
 * WHY using process.cwd(): __dirname doesn't work reliably in Next.js RSC.
 * process.cwd() returns the project root when running from /app directory.
 */
export function getDatabase(): Database.Database {
  if (!db) {
    // Support DATABASE_PATH env var for flexibility, otherwise use relative path
    // When running from /app, cwd is /app, so we go up one level to project root
    const projectRoot = process.cwd().endsWith("/app")
      ? path.resolve(process.cwd(), "..")
      : process.cwd();
    const dbPath = process.env.DATABASE_PATH || path.join(projectRoot, "data", "legislation.db");
    db = new Database(dbPath, { readonly: true });
    // Enable WAL mode for better concurrent reads
    db.pragma("journal_mode = WAL");
  }
  return db;
}

/**
 * Close database connection (for cleanup).
 */
export function closeDatabase(): void {
  if (db) {
    db.close();
    db = null;
  }
}

// Types matching the database schema
export interface LegislationRow {
  id: string;
  title: string;
  jurisdiction: string;
  type: string;
  date_enacted: string | null;
  date_repealed: string | null;
  citation: string | null;
  source_url: string | null;
  text_path: string | null;
  text_excerpt: string | null;
  topics: string;
  analysis_status: string;
  created_at: string;
  updated_at: string;
}

export interface CostRow {
  id: number;
  legislation_id: string;
  cost_type: string;
  party: string | null;
  time_hours: number | null;
  time_unit: string | null;
  time_display: string | null;
  money_cents: number | null;
  money_display: string | null;
  assumed_time_value_cents: number | null;
  assumed_time_value_display: string | null;
  frequency: string;
  is_indefinite: number;
  notes: string | null;
  created_at: string;
}
