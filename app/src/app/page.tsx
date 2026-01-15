import { getDatabase, LegislationRow } from "@/lib/db";
import Link from "next/link";

interface ListParams {
  jurisdiction?: string;
  status?: string;
  search?: string;
  topic?: string;
  dateFrom?: string;
  dateTo?: string;
  page?: number;
}

async function getLegislation(params: ListParams) {
  const db = getDatabase();
  const conditions: string[] = [];
  const values: unknown[] = [];

  // Default to showing only analyzed legislation
  conditions.push("analysis_status = ?");
  values.push(params.status || "complete");

  if (params.jurisdiction) {
    conditions.push("jurisdiction = ?");
    values.push(params.jurisdiction);
  }

  if (params.search) {
    conditions.push("title LIKE ?");
    values.push(`%${params.search}%`);
  }

  if (params.topic) {
    // Topics are stored as JSON arrays, so we use LIKE to match
    conditions.push("topics LIKE ?");
    values.push(`%"${params.topic}"%`);
  }

  if (params.dateFrom) {
    conditions.push("date_enacted >= ?");
    values.push(params.dateFrom);
  }

  if (params.dateTo) {
    conditions.push("date_enacted <= ?");
    values.push(params.dateTo);
  }

  const where = conditions.length > 0 ? `WHERE ${conditions.join(" AND ")}` : "";
  const limit = 50;
  const offset = ((params.page || 1) - 1) * limit;

  const countStmt = db.prepare(`SELECT COUNT(*) as count FROM legislation ${where}`);
  const countResult = countStmt.get(...values) as { count: number };
  const total = countResult.count;

  const stmt = db.prepare(`
    SELECT * FROM legislation ${where}
    ORDER BY date_enacted IS NULL, date_enacted DESC
    LIMIT ? OFFSET ?
  `);
  const rows = stmt.all(...values, limit, offset) as LegislationRow[];

  return { rows, total, page: params.page || 1, limit };
}

/**
 * Get all unique topics from analyzed legislation.
 * WHY: Enables topic filter dropdown on index page per spec requirement.
 */
async function getAllTopics(): Promise<{ slug: string; displayName: string }[]> {
  const db = getDatabase();
  const rows = db
    .prepare(
      `SELECT topics FROM legislation
       WHERE analysis_status = 'complete' AND topics IS NOT NULL AND topics != '[]'`
    )
    .all() as { topics: string }[];

  const topicSet = new Set<string>();
  for (const row of rows) {
    try {
      const topics = JSON.parse(row.topics) as string[];
      topics.forEach((t) => topicSet.add(t));
    } catch {
      // Skip malformed JSON
    }
  }

  return Array.from(topicSet)
    .sort()
    .map((slug) => ({
      slug,
      displayName: slug
        .split("-")
        .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
        .join(" "),
    }));
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

/**
 * Build pagination URL with all current filter parameters preserved.
 */
function buildPaginationUrl(
  page: number,
  params: { [key: string]: string | undefined }
): string {
  const queryParams = new URLSearchParams();
  queryParams.set("page", String(page));

  if (params.jurisdiction) queryParams.set("jurisdiction", params.jurisdiction);
  if (params.search) queryParams.set("search", params.search);
  if (params.topic) queryParams.set("topic", params.topic);
  if (params.dateFrom) queryParams.set("dateFrom", params.dateFrom);
  if (params.dateTo) queryParams.set("dateTo", params.dateTo);

  return `?${queryParams.toString()}`;
}

export default async function Home({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | undefined }>;
}) {
  const params = await searchParams;
  const [{ rows, total, page, limit }, topics] = await Promise.all([
    getLegislation({
      jurisdiction: params.jurisdiction,
      status: params.status,
      search: params.search,
      topic: params.topic,
      dateFrom: params.dateFrom,
      dateTo: params.dateTo,
      page: params.page ? parseInt(params.page) : 1,
    }),
    getAllTopics(),
  ]);

  const totalPages = Math.ceil(total / limit);

  return (
    <div>
      <h1 className="text-xl sm:text-2xl font-bold mb-4 sm:mb-6">
        Legislation Cost Analysis
      </h1>

      {/* Filters */}
      <form
        className="mb-6 space-y-3 sm:space-y-4"
        role="search"
        aria-label="Filter legislation"
      >
        {/* First row: Search and Jurisdiction */}
        <div className="flex flex-col sm:flex-row flex-wrap gap-3 sm:gap-4">
          <div className="flex-1 min-w-0 sm:max-w-xs">
            <label htmlFor="search" className="sr-only">
              Search by title
            </label>
            <input
              type="search"
              id="search"
              name="search"
              placeholder="Search by title..."
              defaultValue={params.search}
              aria-label="Search legislation by title"
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-md bg-white dark:bg-gray-900 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
            />
          </div>

          <div>
            <label htmlFor="jurisdiction" className="sr-only">
              Filter by jurisdiction
            </label>
            <select
              id="jurisdiction"
              name="jurisdiction"
              defaultValue={params.jurisdiction}
              aria-label="Filter by jurisdiction"
              className="w-full sm:w-auto px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-md bg-white dark:bg-gray-900 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
            >
              <option value="">All Jurisdictions</option>
              <option value="commonwealth">Commonwealth</option>
              <option value="new_south_wales">New South Wales</option>
              <option value="queensland">Queensland</option>
              <option value="tasmania">Tasmania</option>
              <option value="western_australia">Western Australia</option>
              <option value="south_australia">South Australia</option>
              <option value="norfolk_island">Norfolk Island</option>
            </select>
          </div>

          {topics.length > 0 && (
            <div>
              <label htmlFor="topic" className="sr-only">
                Filter by topic
              </label>
              <select
                id="topic"
                name="topic"
                defaultValue={params.topic}
                aria-label="Filter by topic"
                className="w-full sm:w-auto px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-md bg-white dark:bg-gray-900 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
              >
                <option value="">All Topics</option>
                {topics.map((topic) => (
                  <option key={topic.slug} value={topic.slug}>
                    {topic.displayName}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>

        {/* Second row: Date range and Filter button */}
        <div className="flex flex-col sm:flex-row flex-wrap gap-3 sm:gap-4 items-end">
          <div className="flex flex-col sm:flex-row gap-2 sm:gap-3">
            <div>
              <label
                htmlFor="dateFrom"
                className="block text-xs text-gray-500 dark:text-gray-400 mb-1"
              >
                From date
              </label>
              <input
                type="date"
                id="dateFrom"
                name="dateFrom"
                defaultValue={params.dateFrom}
                aria-label="Filter from date"
                className="w-full sm:w-auto px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-md bg-white dark:bg-gray-900 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
              />
            </div>
            <div>
              <label
                htmlFor="dateTo"
                className="block text-xs text-gray-500 dark:text-gray-400 mb-1"
              >
                To date
              </label>
              <input
                type="date"
                id="dateTo"
                name="dateTo"
                defaultValue={params.dateTo}
                aria-label="Filter to date"
                className="w-full sm:w-auto px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-md bg-white dark:bg-gray-900 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
              />
            </div>
          </div>

          <button
            type="submit"
            className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 transition-colors"
          >
            Filter
          </button>
        </div>
      </form>

      {/* Results count */}
      <p
        className="text-gray-600 dark:text-gray-400 mb-4 text-sm sm:text-base"
        aria-live="polite"
        aria-atomic="true"
      >
        Showing {rows.length} of {total} legislation
      </p>

      {/* Legislation list */}
      {rows.length === 0 ? (
        <div className="text-center py-12 text-gray-500" role="status">
          <p className="text-lg">No legislation found</p>
          <p className="text-sm mt-2">Try adjusting your filters or search terms</p>
        </div>
      ) : (
        <ul className="space-y-3 sm:space-y-4" aria-label="Legislation results">
          {rows.map((row) => (
            <li key={row.id}>
              <Link
                href={`/legislation/${encodeURIComponent(row.id)}`}
                className="block p-3 sm:p-4 border border-gray-200 dark:border-gray-800 rounded-lg hover:border-blue-500 dark:hover:border-blue-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 transition-colors"
              >
                <div className="flex justify-between items-start gap-4">
                  <div className="flex-1 min-w-0">
                    <h2 className="font-medium text-base sm:text-lg truncate">
                      {row.title}
                    </h2>
                    <div className="flex flex-wrap gap-2 mt-2 text-xs sm:text-sm text-gray-500 dark:text-gray-400">
                      <span className="px-2 py-0.5 bg-gray-100 dark:bg-gray-800 rounded">
                        {formatJurisdiction(row.jurisdiction)}
                      </span>
                      <span>{row.type.replace("_", " ")}</span>
                      {row.date_enacted && (
                        <span>
                          <time dateTime={row.date_enacted}>
                            Enacted {formatDate(row.date_enacted)}
                          </time>
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <nav
          className="flex flex-col sm:flex-row items-center justify-center gap-2 sm:gap-4 mt-8"
          aria-label="Pagination"
        >
          {page > 1 ? (
            <Link
              href={buildPaginationUrl(page - 1, params)}
              className="w-full sm:w-auto text-center px-4 py-2 border border-gray-300 dark:border-gray-700 rounded-md hover:bg-gray-100 dark:hover:bg-gray-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 transition-colors"
              aria-label={`Go to page ${page - 1}`}
            >
              Previous
            </Link>
          ) : (
            <span
              className="w-full sm:w-auto text-center px-4 py-2 border border-gray-200 dark:border-gray-800 rounded-md text-gray-400 dark:text-gray-600 cursor-not-allowed"
              aria-disabled="true"
            >
              Previous
            </span>
          )}

          <span
            className="px-4 py-2 text-gray-600 dark:text-gray-400"
            aria-current="page"
          >
            Page {page} of {totalPages}
          </span>

          {page < totalPages ? (
            <Link
              href={buildPaginationUrl(page + 1, params)}
              className="w-full sm:w-auto text-center px-4 py-2 border border-gray-300 dark:border-gray-700 rounded-md hover:bg-gray-100 dark:hover:bg-gray-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 transition-colors"
              aria-label={`Go to page ${page + 1}`}
            >
              Next
            </Link>
          ) : (
            <span
              className="w-full sm:w-auto text-center px-4 py-2 border border-gray-200 dark:border-gray-800 rounded-md text-gray-400 dark:text-gray-600 cursor-not-allowed"
              aria-disabled="true"
            >
              Next
            </span>
          )}
        </nav>
      )}
    </div>
  );
}
