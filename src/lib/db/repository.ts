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
   *
   * WHY including analysis metadata: Long document handling requires tracking
   * document length, chunking, and coverage to identify partial analyses.
   */
  upsertLegislation(input: LegislationInput): void {
    const stmt = this.db.prepare(`
      INSERT INTO legislation (
        id, title, jurisdiction, type, date_enacted, date_repealed,
        citation, source_url, text_path, text_excerpt, topics, referenced_legislation,
        analysis_status, document_length, analysis_coverage, analysis_chunks, was_truncated
      ) VALUES (
        @id, @title, @jurisdiction, @type, @dateEnacted, @dateRepealed,
        @citation, @sourceUrl, @textPath, @textExcerpt, @topics, @referencedLegislation,
        @analysisStatus, @documentLength, @analysisCoverage, @analysisChunks, @wasTruncated
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
        referenced_legislation = excluded.referenced_legislation,
        analysis_status = excluded.analysis_status,
        document_length = excluded.document_length,
        analysis_coverage = excluded.analysis_coverage,
        analysis_chunks = excluded.analysis_chunks,
        was_truncated = excluded.was_truncated
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
      referencedLegislation: JSON.stringify(input.referencedLegislation ?? []),
      analysisStatus: input.analysisStatus ?? 'pending',
      documentLength: input.documentLength ?? null,
      analysisCoverage: input.analysisCoverage ?? null,
      analysisChunks: input.analysisChunks ?? null,
      wasTruncated: input.wasTruncated ? 1 : 0,
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
   *
   * WHY dateFrom/dateTo: The spec requires "Legislation can be queried/retrieved
   * by identifier (e.g., act name, jurisdiction, date)". Date range filtering
   * enables temporal analysis (e.g., "all legislation from 2020-2023").
   */
  listLegislation(options?: {
    jurisdiction?: Jurisdiction;
    status?: AnalysisStatus;
    topic?: string;
    search?: string;
    dateFrom?: string;  // YYYY-MM-DD format
    dateTo?: string;    // YYYY-MM-DD format
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

    if (options?.dateFrom) {
      conditions.push('date_enacted >= @dateFrom');
      params.dateFrom = options.dateFrom;
    }

    if (options?.dateTo) {
      conditions.push('date_enacted <= @dateTo');
      params.dateTo = options.dateTo;
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
    dateFrom?: string;  // YYYY-MM-DD format
    dateTo?: string;    // YYYY-MM-DD format
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

    if (options?.dateFrom) {
      conditions.push('date_enacted >= @dateFrom');
      params.dateFrom = options.dateFrom;
    }

    if (options?.dateTo) {
      conditions.push('date_enacted <= @dateTo');
      params.dateTo = options.dateTo;
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
   *
   * WHY: The spec requires "support comparison/aggregation across legislation
   * (e.g., total cost by topic area)". This enables users to see which policy
   * areas have the highest regulatory burden.
   *
   * Implementation: Since topics are stored as JSON arrays, we can't aggregate
   * directly in SQL. We fetch all relevant data and aggregate in JavaScript.
   */
  getCostStatsByTopic(): Array<{
    topic: string;
    legislationCount: number;
    totalMoneyCents: number;
    totalTimeHours: number;
  }> {
    // Query all legislation with their topics and associated costs
    const stmt = this.db.prepare<[], {
      topics: string;
      total_money_cents: number | null;
      total_time_hours: number | null;
    }>(`
      SELECT
        l.topics,
        SUM(c.money_cents) as total_money_cents,
        SUM(c.time_hours) as total_time_hours
      FROM legislation l
      LEFT JOIN costs c ON l.id = c.legislation_id
      WHERE l.topics != '[]' AND l.analysis_status = 'complete'
      GROUP BY l.id, l.topics
    `);
    const rows = stmt.all();

    // Aggregate by topic
    const topicStats = new Map<string, {
      legislationIds: Set<string>;
      totalMoneyCents: number;
      totalTimeHours: number;
    }>();

    for (const row of rows) {
      let topics: string[];
      try {
        topics = JSON.parse(row.topics) as string[];
      } catch {
        continue;
      }

      for (const topic of topics) {
        if (!topicStats.has(topic)) {
          topicStats.set(topic, {
            legislationIds: new Set(),
            totalMoneyCents: 0,
            totalTimeHours: 0,
          });
        }
        const stats = topicStats.get(topic)!;
        // Use a unique identifier from the query (topics string serves as proxy for now)
        stats.legislationIds.add(row.topics);
        stats.totalMoneyCents += row.total_money_cents ?? 0;
        stats.totalTimeHours += row.total_time_hours ?? 0;
      }
    }

    // Convert to array and sort by legislation count descending
    return Array.from(topicStats.entries())
      .map(([topic, stats]) => ({
        topic,
        legislationCount: stats.legislationIds.size,
        totalMoneyCents: Math.round(stats.totalMoneyCents),
        totalTimeHours: Math.round(stats.totalTimeHours * 100) / 100,
      }))
      .sort((a, b) => b.legislationCount - a.legislationCount);
  }

  /**
   * Close the database connection.
   */
  close(): void {
    this.db.close();
  }
}
