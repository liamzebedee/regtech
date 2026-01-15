/**
 * Tests for database schema and repository.
 *
 * WHY: Verifying database operations ensures data integrity and query correctness
 * before building the analysis pipeline and website on top of this foundation.
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { initializeDatabase } from '../schema';
import { LegislationRepository } from '../repository';
import type Database from 'better-sqlite3';
import { unlinkSync, existsSync } from 'fs';

const TEST_DB_PATH = '/tmp/test-legislation.db';

describe('LegislationRepository', () => {
  let db: Database.Database;
  let repo: LegislationRepository;

  beforeEach(() => {
    // Clean up any existing test database
    if (existsSync(TEST_DB_PATH)) {
      unlinkSync(TEST_DB_PATH);
    }
    if (existsSync(`${TEST_DB_PATH}-wal`)) {
      unlinkSync(`${TEST_DB_PATH}-wal`);
    }
    if (existsSync(`${TEST_DB_PATH}-shm`)) {
      unlinkSync(`${TEST_DB_PATH}-shm`);
    }

    db = initializeDatabase(TEST_DB_PATH);
    repo = new LegislationRepository(db);
  });

  afterEach(() => {
    repo.close();
    // Clean up test database
    if (existsSync(TEST_DB_PATH)) {
      unlinkSync(TEST_DB_PATH);
    }
    if (existsSync(`${TEST_DB_PATH}-wal`)) {
      unlinkSync(`${TEST_DB_PATH}-wal`);
    }
    if (existsSync(`${TEST_DB_PATH}-shm`)) {
      unlinkSync(`${TEST_DB_PATH}-shm`);
    }
  });

  describe('initializeDatabase', () => {
    it('should create legislation table', () => {
      const tables = db
        .prepare("SELECT name FROM sqlite_master WHERE type='table' AND name='legislation'")
        .get();
      expect(tables).toBeDefined();
    });

    it('should create costs table', () => {
      const tables = db
        .prepare("SELECT name FROM sqlite_master WHERE type='table' AND name='costs'")
        .get();
      expect(tables).toBeDefined();
    });

    it('should create required indexes', () => {
      const indexes = db
        .prepare("SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'")
        .all() as { name: string }[];
      const indexNames = indexes.map(i => i.name);

      expect(indexNames).toContain('idx_legislation_jurisdiction');
      expect(indexNames).toContain('idx_legislation_date_enacted');
      expect(indexNames).toContain('idx_legislation_analysis_status');
      expect(indexNames).toContain('idx_costs_legislation_id');
    });
  });

  describe('upsertLegislation', () => {
    it('should insert new legislation', () => {
      repo.upsertLegislation({
        id: 'test-act-2024',
        title: 'Test Act 2024',
        jurisdiction: 'commonwealth',
        type: 'primary_legislation',
        dateEnacted: '2024-01-01',
        topics: ['taxation', 'compliance'],
      });

      const result = repo.getLegislationById('test-act-2024');
      expect(result).toBeDefined();
      expect(result!.title).toBe('Test Act 2024');
      expect(result!.jurisdiction).toBe('commonwealth');
      expect(JSON.parse(result!.topics)).toEqual(['taxation', 'compliance']);
    });

    it('should update existing legislation', () => {
      repo.upsertLegislation({
        id: 'test-act-2024',
        title: 'Test Act 2024',
        jurisdiction: 'commonwealth',
      });

      repo.upsertLegislation({
        id: 'test-act-2024',
        title: 'Test Act 2024 (Amended)',
        jurisdiction: 'commonwealth',
        topics: ['amended'],
      });

      const result = repo.getLegislationById('test-act-2024');
      expect(result!.title).toBe('Test Act 2024 (Amended)');
      expect(JSON.parse(result!.topics)).toEqual(['amended']);
    });

    it('should set default analysis_status to pending', () => {
      repo.upsertLegislation({
        id: 'test-act-2024',
        title: 'Test Act 2024',
        jurisdiction: 'new_south_wales',
      });

      const result = repo.getLegislationById('test-act-2024');
      expect(result!.analysis_status).toBe('pending');
    });
  });

  describe('listLegislation', () => {
    beforeEach(() => {
      // Insert test data
      repo.upsertLegislation({
        id: 'nsw-act-1',
        title: 'NSW Environmental Act',
        jurisdiction: 'new_south_wales',
        dateEnacted: '2020-01-01',
        topics: ['environment'],
        analysisStatus: 'complete',
      });
      repo.upsertLegislation({
        id: 'vic-act-1',
        title: 'Victoria Planning Act',
        jurisdiction: 'queensland',
        dateEnacted: '2021-06-15',
        topics: ['planning', 'development'],
        analysisStatus: 'pending',
      });
      repo.upsertLegislation({
        id: 'cth-act-1',
        title: 'Commonwealth Tax Act',
        jurisdiction: 'commonwealth',
        dateEnacted: '2022-07-01',
        topics: ['taxation'],
        analysisStatus: 'complete',
      });
    });

    it('should list all legislation', () => {
      const results = repo.listLegislation();
      expect(results).toHaveLength(3);
    });

    it('should filter by jurisdiction', () => {
      const results = repo.listLegislation({ jurisdiction: 'new_south_wales' });
      expect(results).toHaveLength(1);
      expect(results[0].id).toBe('nsw-act-1');
    });

    it('should filter by analysis status', () => {
      const results = repo.listLegislation({ status: 'complete' });
      expect(results).toHaveLength(2);
    });

    it('should filter by topic', () => {
      const results = repo.listLegislation({ topic: 'taxation' });
      expect(results).toHaveLength(1);
      expect(results[0].id).toBe('cth-act-1');
    });

    it('should search by title', () => {
      const results = repo.listLegislation({ search: 'Environmental' });
      expect(results).toHaveLength(1);
      expect(results[0].id).toBe('nsw-act-1');
    });

    it('should order by date descended by default', () => {
      const results = repo.listLegislation();
      expect(results[0].id).toBe('cth-act-1'); // Most recent
      expect(results[2].id).toBe('nsw-act-1'); // Oldest
    });

    it('should support pagination', () => {
      const page1 = repo.listLegislation({ limit: 2, offset: 0 });
      expect(page1).toHaveLength(2);

      const page2 = repo.listLegislation({ limit: 2, offset: 2 });
      expect(page2).toHaveLength(1);
    });

    it('should filter by date range (dateFrom)', () => {
      const results = repo.listLegislation({ dateFrom: '2021-01-01' });
      expect(results).toHaveLength(2); // vic-act-1 (2021-06-15) and cth-act-1 (2022-07-01)
    });

    it('should filter by date range (dateTo)', () => {
      const results = repo.listLegislation({ dateTo: '2021-01-01' });
      expect(results).toHaveLength(1); // nsw-act-1 (2020-01-01)
      expect(results[0].id).toBe('nsw-act-1');
    });

    it('should filter by date range (both dateFrom and dateTo)', () => {
      const results = repo.listLegislation({ dateFrom: '2020-06-01', dateTo: '2022-01-01' });
      expect(results).toHaveLength(1); // vic-act-1 (2021-06-15)
      expect(results[0].id).toBe('vic-act-1');
    });

    it('should combine date range with other filters', () => {
      const results = repo.listLegislation({
        dateFrom: '2020-01-01',
        dateTo: '2022-12-31',
        status: 'complete',
      });
      expect(results).toHaveLength(2); // nsw-act-1 and cth-act-1 (both complete)
    });
  });

  describe('countLegislation', () => {
    beforeEach(() => {
      repo.upsertLegislation({
        id: 'act-1',
        title: 'Act 1',
        jurisdiction: 'new_south_wales',
        dateEnacted: '2020-01-01',
      });
      repo.upsertLegislation({
        id: 'act-2',
        title: 'Act 2',
        jurisdiction: 'new_south_wales',
        dateEnacted: '2021-06-15',
      });
      repo.upsertLegislation({
        id: 'act-3',
        title: 'Act 3',
        jurisdiction: 'queensland',
        dateEnacted: '2022-12-01',
      });
    });

    it('should count all legislation', () => {
      expect(repo.countLegislation()).toBe(3);
    });

    it('should count with filters', () => {
      expect(repo.countLegislation({ jurisdiction: 'new_south_wales' })).toBe(2);
      expect(repo.countLegislation({ jurisdiction: 'queensland' })).toBe(1);
    });

    it('should count with date range filter', () => {
      expect(repo.countLegislation({ dateFrom: '2021-01-01' })).toBe(2);
      expect(repo.countLegislation({ dateTo: '2021-01-01' })).toBe(1);
      expect(repo.countLegislation({ dateFrom: '2021-01-01', dateTo: '2022-01-01' })).toBe(1);
    });
  });

  describe('updateAnalysisStatus', () => {
    it('should update status', () => {
      repo.upsertLegislation({ id: 'test-1', title: 'Test', jurisdiction: 'queensland' });
      expect(repo.getLegislationById('test-1')!.analysis_status).toBe('pending');

      repo.updateAnalysisStatus('test-1', 'in_progress');
      expect(repo.getLegislationById('test-1')!.analysis_status).toBe('in_progress');

      repo.updateAnalysisStatus('test-1', 'complete');
      expect(repo.getLegislationById('test-1')!.analysis_status).toBe('complete');
    });
  });

  describe('getPendingLegislation', () => {
    it('should return only pending legislation', () => {
      repo.upsertLegislation({ id: 'pending-1', title: 'Pending', jurisdiction: 'south_australia' });
      repo.upsertLegislation({
        id: 'complete-1',
        title: 'Complete',
        jurisdiction: 'south_australia',
        analysisStatus: 'complete',
      });

      const pending = repo.getPendingLegislation();
      expect(pending).toHaveLength(1);
      expect(pending[0].id).toBe('pending-1');
    });
  });

  describe('costs', () => {
    beforeEach(() => {
      repo.upsertLegislation({ id: 'test-act', title: 'Test Act', jurisdiction: 'tasmania' });
    });

    it('should insert compliance cost', () => {
      const id = repo.insertCost({
        legislationId: 'test-act',
        costType: 'compliance',
        party: 'citizen',
        timeHours: 2,
        timeUnit: 'hours',
        timeDisplay: '2 hours',
        frequency: 'annually',
        isIndefinite: false,
      });

      expect(id).toBeGreaterThan(0);

      const costs = repo.getComplianceCosts('test-act');
      expect(costs).toHaveLength(1);
      expect(costs[0].party).toBe('citizen');
      expect(costs[0].time_hours).toBe(2);
    });

    it('should insert enforcement cost', () => {
      repo.insertCost({
        legislationId: 'test-act',
        costType: 'enforcement',
        moneyCents: 100000,
        moneyDisplay: '$1,000',
        frequency: 'per_transaction',
      });

      const cost = repo.getEnforcementCost('test-act');
      expect(cost).toBeDefined();
      expect(cost!.money_cents).toBe(100000);
    });

    it('should handle indefinite costs', () => {
      repo.insertCost({
        legislationId: 'test-act',
        costType: 'compliance',
        party: 'business',
        isIndefinite: true,
        notes: 'Burden of proof reversed',
      });

      const costs = repo.getComplianceCosts('test-act');
      expect(costs[0].is_indefinite).toBe(1);
      expect(costs[0].notes).toBe('Burden of proof reversed');
    });

    it('should get all costs for legislation', () => {
      repo.insertCost({ legislationId: 'test-act', costType: 'compliance', party: 'citizen' });
      repo.insertCost({ legislationId: 'test-act', costType: 'compliance', party: 'business' });
      repo.insertCost({ legislationId: 'test-act', costType: 'enforcement' });

      const allCosts = repo.getCostsByLegislationId('test-act');
      expect(allCosts).toHaveLength(3);
    });

    it('should delete costs when re-analyzing', () => {
      repo.insertCost({ legislationId: 'test-act', costType: 'compliance', party: 'citizen' });
      repo.insertCost({ legislationId: 'test-act', costType: 'enforcement' });

      repo.deleteCostsByLegislationId('test-act');

      const costs = repo.getCostsByLegislationId('test-act');
      expect(costs).toHaveLength(0);
    });
  });

  describe('getAllTopics', () => {
    it('should return unique topics across all legislation', () => {
      repo.upsertLegislation({
        id: 'act-1',
        title: 'Act 1',
        jurisdiction: 'new_south_wales',
        topics: ['environment', 'planning'],
      });
      repo.upsertLegislation({
        id: 'act-2',
        title: 'Act 2',
        jurisdiction: 'queensland',
        topics: ['planning', 'taxation'],
      });

      const topics = repo.getAllTopics();
      expect(topics).toEqual(['environment', 'planning', 'taxation']);
    });

    it('should return empty array when no topics', () => {
      repo.upsertLegislation({ id: 'act-1', title: 'Act 1', jurisdiction: 'new_south_wales' });
      const topics = repo.getAllTopics();
      expect(topics).toEqual([]);
    });
  });
});
