/**
 * Cost Model Constants
 *
 * WHY: Consistent wage rates and conversion factors enable fair comparison
 * of time costs across different actor types. Using minimum wage as a baseline
 * ensures conservative estimates that don't understate the burden on individuals.
 */

import type { Party, TimeUnit, MoneyCost, TimeCost } from './cost';

/**
 * Australian National Minimum Wage (as of 1 July 2024).
 * Source: Fair Work Commission Annual Wage Review 2023-24.
 * Updated annually - this should be kept current.
 */
export const MINIMUM_WAGE_HOURLY_CENTS = 2433; // $24.33/hour

/**
 * Wage rates by party type (in cents per hour).
 *
 * WHY different rates: A business owner's time has different opportunity cost
 * than a citizen's time. Using contextually appropriate rates provides more
 * accurate cost estimates.
 */
export const HOURLY_WAGE_BY_PARTY: Record<Party, number> = {
  citizen: MINIMUM_WAGE_HOURLY_CENTS,
  business: 5000,           // ~$50/hour (average business owner)
  small_business: 4000,     // ~$40/hour
  large_business: 7500,     // ~$75/hour (higher opportunity cost)
  government: 5500,         // ~$55/hour (APS average)
  nonprofit: 3500,          // ~$35/hour
  other: MINIMUM_WAGE_HOURLY_CENTS,
};

/**
 * Conversion factors to normalize all time to hours.
 */
export const TIME_TO_HOURS: Record<TimeUnit, number> = {
  minutes: 1 / 60,
  hours: 1,
  days: 8,        // 8-hour workday
  weeks: 40,      // 40-hour workweek
  months: 160,    // ~4 weeks
  years: 1920,    // ~48 working weeks
};

/**
 * Convert a time cost to hours.
 */
export function timeToHours(time: TimeCost): number {
  return time.amount * TIME_TO_HOURS[time.unit];
}

/**
 * Calculate the monetary value of a time cost for a given party.
 *
 * WHY: Enables comparison between pure time costs and pure money costs,
 * and allows aggregation of total burden.
 */
export function calculateAssumedTimeValue(time: TimeCost, party: Party): MoneyCost {
  const hours = timeToHours(time);
  const hourlyRate = HOURLY_WAGE_BY_PARTY[party];
  const totalCents = Math.round(hours * hourlyRate);

  return {
    amountCents: totalCents,
    display: formatMoneyCents(totalCents),
  };
}

/**
 * Format cents as a human-readable AUD string.
 *
 * Examples:
 *   50000 -> "$500"
 *   150000000 -> "$1.5M"
 *   1234567 -> "$12,346"
 */
export function formatMoneyCents(cents: number): string {
  const dollars = cents / 100;

  if (dollars >= 1_000_000) {
    const millions = dollars / 1_000_000;
    return `$${millions.toFixed(1).replace(/\.0$/, '')}M`;
  }

  if (dollars >= 10_000) {
    return `$${Math.round(dollars).toLocaleString('en-AU')}`;
  }

  if (dollars >= 1000) {
    return `$${Math.round(dollars).toLocaleString('en-AU')}`;
  }

  // For smaller amounts, show cents if present
  if (cents % 100 === 0) {
    return `$${dollars}`;
  }

  return `$${dollars.toFixed(2)}`;
}

/**
 * Format a time amount as a human-readable string.
 *
 * Examples:
 *   { amount: 2, unit: 'hours' } -> "2 hours"
 *   { amount: 1, unit: 'days' } -> "1 day"
 *   { amount: 0.5, unit: 'hours' } -> "30 minutes"
 */
export function formatTime(amount: number, unit: TimeUnit): string {
  // Convert fractional hours to minutes if appropriate
  if (unit === 'hours' && amount < 1 && amount > 0) {
    const minutes = Math.round(amount * 60);
    return minutes === 1 ? '1 minute' : `${minutes} minutes`;
  }

  // Handle singular vs plural
  const rounded = Math.round(amount * 10) / 10; // One decimal place
  const displayAmount = rounded % 1 === 0 ? Math.round(rounded) : rounded;

  // Singularize unit if amount is 1
  if (displayAmount === 1) {
    const singular = unit.replace(/s$/, ''); // Remove trailing 's'
    return `1 ${singular}`;
  }

  return `${displayAmount} ${unit}`;
}

/**
 * Create a TimeCost object with auto-generated display string.
 */
export function createTimeCost(amount: number, unit: TimeUnit): TimeCost {
  return {
    amount,
    unit,
    display: formatTime(amount, unit),
  };
}

/**
 * Create a MoneyCost object with auto-generated display string.
 */
export function createMoneyCost(amountCents: number): MoneyCost {
  return {
    amountCents,
    display: formatMoneyCents(amountCents),
  };
}
