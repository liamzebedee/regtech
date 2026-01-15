/**
 * Database Repository
 *
 * WHY: Centralized data access layer provides clean API for all database operations,
 * encapsulates SQL queries, and enables consistent error handling and type safety.
 */

import type Database from 'better-sqlite3';
import type {
  LegislationRow,
  CostRow,
  LegislationInput,
  CostInput,
} from './schema';
import type { AnalysisStatus, Jurisdiction } from '../types/cost';

/**
 * Repository for legislation and cost data operations.
 */
export class LegislationRepository {
  constructor(private db: Database.Database) {}

  /**
   * Insert or update a legislation record.
   */
  upsertLegislation(input: LegislationInput): void {
    const stmt = this.db.prepare(`
      INSERT INTO legislation (
        id, title, jurisdiction, type, date_enacted, date_repealed,
        citation, source_url, text_path, text_excerpt, topics, analysis_status
      ) VALUES (
        @id, @title, @jurisdiction, @type, @dateEnacted, @dateRepealed,
        @citation, @sourceUrl, @textPath, @textExcerpt, @topics, @analysisStatus
      )
      ON CONFLICT(id) DO UPDATE SET
        title = excluded.title,
        jurisdiction = excluded.jurisdiction,
        type = excluded.type,
        date_enacted = excluded.date_enacted,
        date_repealed = excluded.date_repealed,
        citation = excluded.citation,
        source_url = excluded.source_url,
        text_path = excluded.text_path,
        text_excerpt = excluded.text_excerpt,
        topics = excluded.topics,
        analysis_status = excluded.analysis_status
    `);

    stmt.run({
      id: input.id,
      title: input.title,
      jurisdiction: input.jurisdiction,
      type: input.type ?? 'other',
      dateEnacted: input.dateEnacted ?? null,
      dateRepealed: input.dateRepealed ?? null,
      citation: input.citation ?? null,
      sourceUrl: input.sourceUrl ?? null,
      textPath: input.textPath ?? null,
      textExcerpt: input.textExcerpt ?? null,
      topics: JSON.stringify(input.topics ?? []),
      analysisStatus: input.analysisStatus ?? 'pending',
    });
  }

  /**
   * Get legislation by ID.
   */
  getLegislationById(id: string): LegislationRow | undefined {
    const stmt = this.db.prepare<[string], LegislationRow>(
      'SELECT * FROM legislation WHERE id = ?'
    );
    return stmt.get(id);
  }

  /**
   * List all legislation with optional filtering.
   */
  listLegislation(options?: {
    jurisdiction?: Jurisdiction;
    status?: AnalysisStatus;
    topic?: string;
    search?: string;
    limit?: number;
    offset?: number;
    orderBy?: 'date_enacted' | 'title' | 'created_at';
    orderDir?: 'ASC' | 'DESC';
  }): LegislationRow[] {
    const conditions: string[] = [];
    const params: Record<string, unknown> = {};

    if (options?.jurisdiction) {
      conditions.push('jurisdiction = @jurisdiction');
      params.jurisdiction = options.jurisdiction;
    }

    if (options?.status) {
      conditions.push('analysis_status = @status');
      params.status = options.status;
    }

    if (options?.topic) {
      conditions.push('topics LIKE @topic');
      params.topic = `%"${options.topic}"%`;
    }

    if (options?.search) {
      conditions.push('title LIKE @search');
      params.search = `%${options.search}%`;
    }

    const where = conditions.length > 0 ? `WHERE ${conditions.join(' AND ')}` : '';
    const orderBy = options?.orderBy ?? 'date_enacted';
    const orderDir = options?.orderDir ?? 'DESC';
    const limit = options?.limit ?? 50;
    const offset = options?.offset ?? 0;

    const sql = `
      SELECT * FROM legislation
      ${where}
      ORDER BY ${orderBy} ${orderDir}
      LIMIT @limit OFFSET @offset
    `;

    const stmt = this.db.prepare<Record<string, unknown>, LegislationRow>(sql);
    return stmt.all({ ...params, limit, offset });
  }

  /**
   * Count legislation matching filters.
   */
  countLegislation(options?: {
    jurisdiction?: Jurisdiction;
    status?: AnalysisStatus;
    topic?: string;
    search?: string;
  }): number {
    const conditions: string[] = [];
    const params: Record<string, unknown> = {};

    if (options?.jurisdiction) {
      conditions.push('jurisdiction = @jurisdiction');
      params.jurisdiction = options.jurisdiction;
    }

    if (options?.status) {
      conditions.push('analysis_status = @status');
      params.status = options.status;
    }

    if (options?.topic) {
      conditions.push('topics LIKE @topic');
      params.topic = `%"${options.topic}"%`;
    }

    if (options?.search) {
      conditions.push('title LIKE @search');
      params.search = `%${options.search}%`;
    }

    const where = conditions.length > 0 ? `WHERE ${conditions.join(' AND ')}` : '';
    const sql = `SELECT COUNT(*) as count FROM legislation ${where}`;

    const stmt = this.db.prepare<Record<string, unknown>, { count: number }>(sql);
    const result = stmt.get(params);
    return result?.count ?? 0;
  }

  /**
   * Update analysis status for a legislation.
   */
  updateAnalysisStatus(id: string, status: AnalysisStatus): void {
    const stmt = this.db.prepare(
      'UPDATE legislation SET analysis_status = ? WHERE id = ?'
    );
    stmt.run(status, id);
  }

  /**
   * Get legislation pending analysis.
   */
  getPendingLegislation(limit = 100): LegislationRow[] {
    const stmt = this.db.prepare<[number], LegislationRow>(`
      SELECT * FROM legislation
      WHERE analysis_status = 'pending'
      ORDER BY created_at ASC
      LIMIT ?
    `);
    return stmt.all(limit);
  }

  /**
   * Insert a cost record.
   */
  insertCost(input: CostInput): number {
    const stmt = this.db.prepare(`
      INSERT INTO costs (
        legislation_id, cost_type, party, time_hours, time_unit, time_display,
        money_cents, money_display, assumed_time_value_cents, assumed_time_value_display,
        frequency, is_indefinite, notes
      ) VALUES (
        @legislationId, @costType, @party, @timeHours, @timeUnit, @timeDisplay,
        @moneyCents, @moneyDisplay, @assumedTimeValueCents, @assumedTimeValueDisplay,
        @frequency, @isIndefinite, @notes
      )
    `);

    const result = stmt.run({
      legislationId: input.legislationId,
      costType: input.costType,
      party: input.party ?? null,
      timeHours: input.timeHours ?? null,
      timeUnit: input.timeUnit ?? null,
      timeDisplay: input.timeDisplay ?? null,
      moneyCents: input.moneyCents ?? null,
      moneyDisplay: input.moneyDisplay ?? null,
      assumedTimeValueCents: input.assumedTimeValueCents ?? null,
      assumedTimeValueDisplay: input.assumedTimeValueDisplay ?? null,
      frequency: input.frequency ?? 'one_time',
      isIndefinite: input.isIndefinite ? 1 : 0,
      notes: input.notes ?? null,
    });

    return Number(result.lastInsertRowid);
  }

  /**
   * Get all costs for a legislation.
   */
  getCostsByLegislationId(legislationId: string): CostRow[] {
    const stmt = this.db.prepare<[string], CostRow>(
      'SELECT * FROM costs WHERE legislation_id = ?'
    );
    return stmt.all(legislationId);
  }

  /**
   * Get compliance costs for a legislation.
   */
  getComplianceCosts(legislationId: string): CostRow[] {
    const stmt = this.db.prepare<[string], CostRow>(
      "SELECT * FROM costs WHERE legislation_id = ? AND cost_type = 'compliance'"
    );
    return stmt.all(legislationId);
  }

  /**
   * Get enforcement cost for a legislation.
   */
  getEnforcementCost(legislationId: string): CostRow | undefined {
    const stmt = this.db.prepare<[string], CostRow>(
      "SELECT * FROM costs WHERE legislation_id = ? AND cost_type = 'enforcement' LIMIT 1"
    );
    return stmt.get(legislationId);
  }

  /**
   * Delete all costs for a legislation (for re-analysis).
   */
  deleteCostsByLegislationId(legislationId: string): void {
    const stmt = this.db.prepare('DELETE FROM costs WHERE legislation_id = ?');
    stmt.run(legislationId);
  }

  /**
   * Get all unique topics from legislation.
   */
  getAllTopics(): string[] {
    const stmt = this.db.prepare<[], { topics: string }>(
      "SELECT DISTINCT topics FROM legislation WHERE topics != '[]'"
    );
    const rows = stmt.all();

    // Parse JSON arrays and flatten to unique set
    const topicSet = new Set<string>();
    for (const row of rows) {
      try {
        const topics = JSON.parse(row.topics) as string[];
        topics.forEach(t => topicSet.add(t));
      } catch {
        // Ignore malformed JSON
      }
    }

    return Array.from(topicSet).sort();
  }

  /**
   * Get aggregated cost statistics by topic.
   */
  getCostStatsByTopic(): Array<{
    topic: string;
    legislationCount: number;
    totalMoneyCents: number;
    totalTimeHours: number;
  }> {
    // This is more complex, requires aggregation across JSON topics
    // For now, return empty - implement when needed
    return [];
  }

  /**
   * Close the database connection.
   */
  close(): void {
    this.db.close();
  }
}
