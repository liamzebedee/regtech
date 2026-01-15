/**
 * Tests for cost model constants and utility functions.
 *
 * WHY: Verifying formatting and conversion logic ensures costs are
 * displayed consistently and calculated correctly across the application.
 */

import { describe, it, expect } from 'vitest';
import {
  MINIMUM_WAGE_HOURLY_CENTS,
  HOURLY_WAGE_BY_PARTY,
  timeToHours,
  calculateAssumedTimeValue,
  formatMoneyCents,
  formatTime,
  createTimeCost,
  createMoneyCost,
} from '../constants';

describe('constants', () => {
  describe('MINIMUM_WAGE_HOURLY_CENTS', () => {
    it('should be the current Australian minimum wage', () => {
      // $24.33/hour as of July 2024
      expect(MINIMUM_WAGE_HOURLY_CENTS).toBe(2433);
    });
  });

  describe('HOURLY_WAGE_BY_PARTY', () => {
    it('should have rates for all party types', () => {
      expect(HOURLY_WAGE_BY_PARTY.citizen).toBe(MINIMUM_WAGE_HOURLY_CENTS);
      expect(HOURLY_WAGE_BY_PARTY.business).toBeGreaterThan(MINIMUM_WAGE_HOURLY_CENTS);
      expect(HOURLY_WAGE_BY_PARTY.small_business).toBeGreaterThan(0);
      expect(HOURLY_WAGE_BY_PARTY.large_business).toBeGreaterThan(HOURLY_WAGE_BY_PARTY.business);
      expect(HOURLY_WAGE_BY_PARTY.government).toBeGreaterThan(0);
      expect(HOURLY_WAGE_BY_PARTY.nonprofit).toBeGreaterThan(0);
      expect(HOURLY_WAGE_BY_PARTY.other).toBe(MINIMUM_WAGE_HOURLY_CENTS);
    });
  });
});

describe('timeToHours', () => {
  it('should convert minutes to hours', () => {
    expect(timeToHours({ amount: 30, unit: 'minutes', display: '30 minutes' })).toBeCloseTo(0.5);
    expect(timeToHours({ amount: 60, unit: 'minutes', display: '60 minutes' })).toBeCloseTo(1);
  });

  it('should pass through hours unchanged', () => {
    expect(timeToHours({ amount: 2, unit: 'hours', display: '2 hours' })).toBe(2);
  });

  it('should convert days to hours (8-hour workday)', () => {
    expect(timeToHours({ amount: 1, unit: 'days', display: '1 day' })).toBe(8);
    expect(timeToHours({ amount: 5, unit: 'days', display: '5 days' })).toBe(40);
  });

  it('should convert weeks to hours (40-hour workweek)', () => {
    expect(timeToHours({ amount: 1, unit: 'weeks', display: '1 week' })).toBe(40);
  });

  it('should convert months to hours', () => {
    expect(timeToHours({ amount: 1, unit: 'months', display: '1 month' })).toBe(160);
  });

  it('should convert years to hours', () => {
    expect(timeToHours({ amount: 1, unit: 'years', display: '1 year' })).toBe(1920);
  });
});

describe('calculateAssumedTimeValue', () => {
  it('should calculate value using party-specific wage rate', () => {
    const oneHour = { amount: 1, unit: 'hours' as const, display: '1 hour' };

    const citizenValue = calculateAssumedTimeValue(oneHour, 'citizen');
    expect(citizenValue.amountCents).toBe(2433); // Minimum wage

    const businessValue = calculateAssumedTimeValue(oneHour, 'business');
    expect(businessValue.amountCents).toBe(5000); // $50/hour
  });

  it('should calculate value for partial hours', () => {
    const thirtyMinutes = { amount: 30, unit: 'minutes' as const, display: '30 minutes' };
    const value = calculateAssumedTimeValue(thirtyMinutes, 'citizen');
    expect(value.amountCents).toBe(1217); // Half of minimum wage
  });

  it('should calculate value for days', () => {
    const oneDay = { amount: 1, unit: 'days' as const, display: '1 day' };
    const value = calculateAssumedTimeValue(oneDay, 'citizen');
    expect(value.amountCents).toBe(2433 * 8); // 8 hours at minimum wage
  });
});

describe('formatMoneyCents', () => {
  it('should format small amounts without cents when even', () => {
    expect(formatMoneyCents(10000)).toBe('$100');
    expect(formatMoneyCents(50000)).toBe('$500');
  });

  it('should format small amounts with cents when needed', () => {
    expect(formatMoneyCents(10050)).toBe('$100.50');
    expect(formatMoneyCents(2433)).toBe('$24.33');
  });

  it('should format thousands with commas', () => {
    expect(formatMoneyCents(1234500)).toBe('$12,345');
    expect(formatMoneyCents(10000000)).toBe('$100,000');
  });

  it('should format millions with M suffix', () => {
    expect(formatMoneyCents(150000000)).toBe('$1.5M');
    expect(formatMoneyCents(100000000)).toBe('$1M');
    expect(formatMoneyCents(250000000)).toBe('$2.5M');
  });
});

describe('formatTime', () => {
  it('should format singular units correctly', () => {
    expect(formatTime(1, 'hours')).toBe('1 hour');
    expect(formatTime(1, 'days')).toBe('1 day');
    expect(formatTime(1, 'weeks')).toBe('1 week');
  });

  it('should format plural units correctly', () => {
    expect(formatTime(2, 'hours')).toBe('2 hours');
    expect(formatTime(5, 'days')).toBe('5 days');
    expect(formatTime(3, 'weeks')).toBe('3 weeks');
  });

  it('should convert fractional hours to minutes', () => {
    expect(formatTime(0.5, 'hours')).toBe('30 minutes');
    expect(formatTime(0.25, 'hours')).toBe('15 minutes');
  });

  it('should handle 1 minute specially', () => {
    // 1/60 hours = 1 minute
    expect(formatTime(1/60, 'hours')).toBe('1 minute');
  });
});

describe('createTimeCost', () => {
  it('should create a TimeCost with auto-generated display', () => {
    const cost = createTimeCost(2, 'hours');
    expect(cost.amount).toBe(2);
    expect(cost.unit).toBe('hours');
    expect(cost.display).toBe('2 hours');
  });

  it('should handle singular amounts', () => {
    const cost = createTimeCost(1, 'days');
    expect(cost.display).toBe('1 day');
  });
});

describe('createMoneyCost', () => {
  it('should create a MoneyCost with auto-generated display', () => {
    const cost = createMoneyCost(50000);
    expect(cost.amountCents).toBe(50000);
    expect(cost.display).toBe('$500');
  });

  it('should handle large amounts', () => {
    const cost = createMoneyCost(150000000);
    expect(cost.display).toBe('$1.5M');
  });
});
