/**
 * Cost Model Type Definitions
 *
 * These types capture both discrete costs (time, money) and indefinite costs
 * (liability transfers, burden of proof shifts) for Australian legislation.
 *
 * WHY: A consistent type system enables meaningful comparison of compliance
 * and enforcement costs across legislation, jurisdictions, and time periods.
 */

/**
 * Parties who may bear costs under legislation.
 * Citizens face compliance costs differently than businesses, which differ from government.
 */
export type Party =
  | 'citizen'           // Individual natural persons
  | 'business'          // Commercial entities of any size
  | 'small_business'    // Businesses under specific size thresholds
  | 'large_business'    // Businesses above specific size thresholds
  | 'government'        // Government entities (not enforcement, but compliance obligations)
  | 'nonprofit'         // Non-profit organizations
  | 'other';            // Catch-all for edge cases

/**
 * Time units for expressing time-based costs.
 * Support for minutes through years enables appropriate granularity.
 */
export type TimeUnit = 'minutes' | 'hours' | 'days' | 'weeks' | 'months' | 'years';

/**
 * Frequency of recurring costs.
 * Many compliance costs are not one-time but ongoing obligations.
 */
export type CostFrequency =
  | 'one_time'          // Single occurrence (e.g., registration)
  | 'per_transaction'   // Each time an action occurs
  | 'daily'
  | 'weekly'
  | 'monthly'
  | 'quarterly'
  | 'annually'
  | 'as_needed';        // Conditional/variable frequency

/**
 * Represents a time-based cost component.
 */
export interface TimeCost {
  /** Raw amount of time */
  amount: number;
  /** Unit of time measurement */
  unit: TimeUnit;
  /** Pretty-formatted string for display (e.g., "2 hours", "3 days") */
  display: string;
}

/**
 * Represents a monetary cost component in AUD.
 */
export interface MoneyCost {
  /** Raw amount in AUD cents (for precision) */
  amountCents: number;
  /** Pretty-formatted string for display (e.g., "$500", "$1.2M") */
  display: string;
}

/**
 * Compliance costs borne by a specific party.
 *
 * WHY separate compliance from enforcement: Compliance is what regulated
 * parties must do; enforcement is what the state must do to ensure compliance.
 */
export interface ComplianceCost {
  /** Who bears this cost */
  party: Party;

  /** Time required to comply (optional - not all costs are time-based) */
  time?: TimeCost;

  /** Direct monetary cost (fees, required purchases, etc.) */
  money?: MoneyCost;

  /**
   * Calculated monetary value of time spent, using appropriate wage rate.
   * WHY: Enables apples-to-apples comparison of time vs money costs.
   */
  assumedTimeValue?: MoneyCost;

  /** How often this cost recurs */
  frequency: CostFrequency;

  /**
   * True if the cost cannot be quantified (e.g., reversed burden of proof,
   * indefinite liability exposure, reputational risk).
   */
  isIndefinite: boolean;

  /** Explanation of indefinite costs or additional context */
  notes?: string;
}

/**
 * Enforcement costs borne by the state.
 */
export interface EnforcementCost {
  /** Time required for enforcement activities */
  time?: TimeCost;

  /** Direct monetary cost of enforcement */
  money?: MoneyCost;

  /** Calculated monetary value of enforcement time */
  assumedTimeValue?: MoneyCost;

  /** How often enforcement occurs */
  frequency: CostFrequency;

  /** True if enforcement cost cannot be quantified */
  isIndefinite: boolean;

  /** Explanation of indefinite costs or additional context */
  notes?: string;
}

/**
 * Complete cost entry for a piece of legislation.
 * Links all cost data to the legislation it describes.
 */
export interface CostEntry {
  /** Foreign key to legislation */
  legislationId: string;

  /** All compliance costs (potentially multiple parties) */
  complianceCosts: ComplianceCost[];

  /** Enforcement cost (typically one per legislation) */
  enforcementCost?: EnforcementCost;

  /** When this cost analysis was performed */
  analyzedAt: Date;

  /** Model/version used for analysis (for reproducibility) */
  analysisModel: string;

  /** Overall notes about the cost analysis */
  analysisNotes?: string;
}

/**
 * Analysis status for tracking pipeline progress.
 */
export type AnalysisStatus = 'pending' | 'in_progress' | 'complete' | 'failed';

/**
 * Australian jurisdictions represented in the corpus.
 * These match the exact values from the isaacus/open-australian-legal-corpus dataset.
 */
export type Jurisdiction =
  | 'commonwealth'       // Federal legislation (103,882 docs)
  | 'new_south_wales'    // NSW (119,587 docs)
  | 'queensland'         // QLD (3,306 docs)
  | 'tasmania'           // TAS (2,552 docs)
  | 'western_australia'  // WA (1,564 docs)
  | 'south_australia'    // SA (1,350 docs)
  | 'norfolk_island';    // Norfolk Island (319 docs)

/**
 * Document types in the corpus.
 * These match the exact values from the isaacus/open-australian-legal-corpus dataset.
 */
export type DocumentType =
  | 'decision'              // Court decisions (189,216 docs)
  | 'secondary_legislation' // Regulations, rules, etc. (31,696 docs)
  | 'primary_legislation'   // Acts of Parliament (9,059 docs)
  | 'bill';                 // Bills before Parliament (2,589 docs)

/**
 * Core legislation metadata.
 */
export interface Legislation {
  /** Unique identifier (from corpus) */
  id: string;

  /** Full title of the legislation */
  title: string;

  /** Which jurisdiction enacted this legislation */
  jurisdiction: Jurisdiction;

  /** Type of document */
  type: DocumentType;

  /** Date enacted (if available) */
  dateEnacted?: Date;

  /** Date repealed (if applicable) */
  dateRepealed?: Date;

  /** Citation reference */
  citation?: string;

  /** URL to original source */
  sourceUrl?: string;

  /** Reference to full text location in corpus */
  textPath?: string;

  /** First N characters for preview */
  textExcerpt?: string;

  /** Topic tags/clusters for categorization */
  topics: string[];

  /** Current status in the analysis pipeline */
  analysisStatus: AnalysisStatus;

  /** When the record was created */
  createdAt: Date;

  /** When the record was last updated */
  updatedAt: Date;
}
