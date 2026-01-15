/**
 * Topic Detail Page
 *
 * WHY: Shows all legislation tagged with a specific topic. Enables users to
 * explore a subject area (e.g., all taxation legislation) and understand the
 * cumulative compliance/enforcement costs in that domain.
 */

import { getDatabase, LegislationRow, CostRow } from "@/lib/db";
import Link from "next/link";
import { notFound } from "next/navigation";

// Force dynamic rendering since we need database access
export const dynamic = "force-dynamic";

interface TopicStats {
  totalLegislation: number;
  totalComplianceCosts: number; // in cents
  totalEnforcementCosts: number; // in cents
  partiesAffected: Set<string>;
}

/**
 * Get legislation with a specific topic.
 */
async function getLegislationByTopic(
  topic: string,
  page: number = 1
): Promise<{ rows: LegislationRow[]; total: number }> {
  const db = getDatabase();
  const limit = 50;
  const offset = (page - 1) * limit;

  // SQLite JSON functions to search within the topics array
  // Using LIKE as a simpler approach since topics are stored as JSON arrays
  const topicPattern = `%"${topic}"%`;

  const countResult = db
    .prepare(
      `SELECT COUNT(*) as count FROM legislation
       WHERE analysis_status = 'complete' AND topics LIKE ?`
    )
    .get(topicPattern) as { count: number };

  const rows = db
    .prepare(
      `SELECT * FROM legislation
       WHERE analysis_status = 'complete' AND topics LIKE ?
       ORDER BY date_enacted DESC NULLS LAST
       LIMIT ? OFFSET ?`
    )
    .all(topicPattern, limit, offset) as LegislationRow[];

  return { rows, total: countResult.count };
}

/**
 * Calculate aggregate statistics for a topic.
 */
async function getTopicStats(topic: string): Promise<TopicStats> {
  const db = getDatabase();
  const topicPattern = `%"${topic}"%`;

  // Get all legislation IDs with this topic
  const legislationIds = db
    .prepare(
      `SELECT id FROM legislation
       WHERE analysis_status = 'complete' AND topics LIKE ?`
    )
    .all(topicPattern) as { id: string }[];

  const stats: TopicStats = {
    totalLegislation: legislationIds.length,
    totalComplianceCosts: 0,
    totalEnforcementCosts: 0,
    partiesAffected: new Set(),
  };

  if (legislationIds.length === 0) return stats;

  // Get costs for all legislation with this topic
  const idPlaceholders = legislationIds.map(() => "?").join(",");
  const costs = db
    .prepare(
      `SELECT * FROM costs WHERE legislation_id IN (${idPlaceholders})`
    )
    .all(...legislationIds.map((l) => l.id)) as CostRow[];

  for (const cost of costs) {
    const moneyCents = cost.money_cents || 0;

    if (cost.cost_type === "compliance") {
      stats.totalComplianceCosts += moneyCents;
      if (cost.party) {
        stats.partiesAffected.add(cost.party);
      }
    } else if (cost.cost_type === "enforcement") {
      stats.totalEnforcementCosts += moneyCents;
    }
  }

  return stats;
}

function formatTopicName(topic: string): string {
  return topic
    .split("-")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

function formatJurisdiction(jurisdiction: string): string {
  const map: Record<string, string> = {
    commonwealth: "Commonwealth",
    new_south_wales: "NSW",
    queensland: "QLD",
    tasmania: "TAS",
    western_australia: "WA",
    south_australia: "SA",
    norfolk_island: "Norfolk Is.",
  };
  return map[jurisdiction] || jurisdiction;
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return "—";
  const date = new Date(dateStr);
  return date.toLocaleDateString("en-AU", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function formatMoney(cents: number): string {
  if (cents === 0) return "$0";
  const dollars = cents / 100;
  if (dollars >= 1_000_000) {
    return `$${(dollars / 1_000_000).toFixed(1)}M`;
  }
  if (dollars >= 1_000) {
    return `$${(dollars / 1_000).toFixed(1)}K`;
  }
  return `$${dollars.toFixed(2)}`;
}

function formatParty(party: string): string {
  const map: Record<string, string> = {
    citizen: "Citizens",
    business: "Businesses",
    small_business: "Small Businesses",
    large_business: "Large Businesses",
    government: "Government",
    nonprofit: "Nonprofits",
  };
  return map[party] || party;
}

export default async function TopicPage({
  params,
  searchParams,
}: {
  params: Promise<{ topic: string }>;
  searchParams: Promise<{ page?: string }>;
}) {
  const { topic } = await params;
  const { page: pageParam } = await searchParams;
  const decodedTopic = decodeURIComponent(topic);
  const page = pageParam ? parseInt(pageParam) : 1;

  const [{ rows, total }, stats] = await Promise.all([
    getLegislationByTopic(decodedTopic, page),
    getTopicStats(decodedTopic),
  ]);

  if (total === 0) {
    notFound();
  }

  const totalPages = Math.ceil(total / 50);
  const displayName = formatTopicName(decodedTopic);

  return (
    <div>
      <div className="mb-6">
        <Link href="/topics" className="text-blue-600 hover:text-blue-700 text-sm">
          &larr; All topics
        </Link>
        <h1 className="text-2xl font-bold mt-2">{displayName}</h1>
        <p className="text-gray-600 dark:text-gray-400">
          {total} {total === 1 ? "piece" : "pieces"} of legislation
        </p>
      </div>

      {/* Topic Statistics */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8 p-4 bg-gray-50 dark:bg-gray-900 rounded-lg">
        <div>
          <div className="text-sm text-gray-500 dark:text-gray-400">Legislation</div>
          <div className="text-xl font-semibold">{stats.totalLegislation}</div>
        </div>
        <div>
          <div className="text-sm text-gray-500 dark:text-gray-400">Compliance Costs</div>
          <div className="text-xl font-semibold">
            {stats.totalComplianceCosts > 0 ? formatMoney(stats.totalComplianceCosts) : "—"}
          </div>
        </div>
        <div>
          <div className="text-sm text-gray-500 dark:text-gray-400">Enforcement Costs</div>
          <div className="text-xl font-semibold">
            {stats.totalEnforcementCosts > 0 ? formatMoney(stats.totalEnforcementCosts) : "—"}
          </div>
        </div>
        <div>
          <div className="text-sm text-gray-500 dark:text-gray-400">Parties Affected</div>
          <div className="text-xl font-semibold">
            {stats.partiesAffected.size > 0
              ? Array.from(stats.partiesAffected).map(formatParty).join(", ")
              : "—"}
          </div>
        </div>
      </div>

      {/* Legislation List */}
      <div className="space-y-4">
        {rows.map((row) => (
          <Link
            key={row.id}
            href={`/legislation/${encodeURIComponent(row.id)}`}
            className="block p-4 border border-gray-200 dark:border-gray-800 rounded-lg hover:border-blue-500 dark:hover:border-blue-500 transition-colors"
          >
            <div className="flex justify-between items-start gap-4">
              <div className="flex-1 min-w-0">
                <h2 className="font-medium text-lg truncate">{row.title}</h2>
                <div className="flex flex-wrap gap-2 mt-2 text-sm text-gray-500 dark:text-gray-400">
                  <span className="px-2 py-0.5 bg-gray-100 dark:bg-gray-800 rounded">
                    {formatJurisdiction(row.jurisdiction)}
                  </span>
                  <span>{row.type.replace("_", " ")}</span>
                  {row.date_enacted && <span>Enacted {formatDate(row.date_enacted)}</span>}
                </div>
              </div>
            </div>
          </Link>
        ))}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex justify-center gap-2 mt-8">
          {page > 1 && (
            <Link
              href={`/topics/${encodeURIComponent(decodedTopic)}?page=${page - 1}`}
              className="px-4 py-2 border border-gray-300 dark:border-gray-700 rounded-md hover:bg-gray-100 dark:hover:bg-gray-800"
            >
              Previous
            </Link>
          )}
          <span className="px-4 py-2 text-gray-600 dark:text-gray-400">
            Page {page} of {totalPages}
          </span>
          {page < totalPages && (
            <Link
              href={`/topics/${encodeURIComponent(decodedTopic)}?page=${page + 1}`}
              className="px-4 py-2 border border-gray-300 dark:border-gray-700 rounded-md hover:bg-gray-100 dark:hover:bg-gray-800"
            >
              Next
            </Link>
          )}
        </div>
      )}
    </div>
  );
}
