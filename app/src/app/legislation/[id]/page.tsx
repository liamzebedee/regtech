import { getDatabase, LegislationRow, CostRow } from "@/lib/db";
import { notFound } from "next/navigation";
import Link from "next/link";
import ExpandableText from "@/components/ExpandableText";

interface LegislationWithCosts {
  legislation: LegislationRow;
  complianceCosts: CostRow[];
  enforcementCosts: CostRow[];
}

async function getLegislationWithCosts(id: string): Promise<LegislationWithCosts | null> {
  const db = getDatabase();

  const legStmt = db.prepare("SELECT * FROM legislation WHERE id = ?");
  const legislation = legStmt.get(id) as LegislationRow | undefined;

  if (!legislation) {
    return null;
  }

  const costsStmt = db.prepare("SELECT * FROM costs WHERE legislation_id = ?");
  const costs = costsStmt.all(id) as CostRow[];

  const complianceCosts = costs.filter((c) => c.cost_type === "compliance");
  const enforcementCosts = costs.filter((c) => c.cost_type === "enforcement");

  return { legislation, complianceCosts, enforcementCosts };
}

function formatJurisdiction(jurisdiction: string): string {
  const map: Record<string, string> = {
    commonwealth: "Commonwealth of Australia",
    new_south_wales: "New South Wales",
    queensland: "Queensland",
    tasmania: "Tasmania",
    western_australia: "Western Australia",
    south_australia: "South Australia",
    norfolk_island: "Norfolk Island",
  };
  return map[jurisdiction] || jurisdiction;
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return "—";
  const date = new Date(dateStr);
  return date.toLocaleDateString("en-AU", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

function formatParty(party: string | null): string {
  if (!party) return "Unspecified";
  const map: Record<string, string> = {
    citizen: "Citizens",
    business: "Businesses",
    small_business: "Small Businesses",
    large_business: "Large Businesses",
    government: "Government",
    nonprofit: "Non-profits",
    other: "Other Parties",
  };
  return map[party] || party;
}

function formatMoney(cents: number | null, display: string | null): string {
  if (display) return display;
  if (cents === null) return "—";
  return `$${(cents / 100).toLocaleString("en-AU", { minimumFractionDigits: 2 })}`;
}

function CostCard({ cost }: { cost: CostRow }) {
  return (
    <article
      className="p-3 sm:p-4 border border-gray-200 dark:border-gray-800 rounded-lg"
      aria-labelledby={`cost-party-${cost.id}`}
    >
      <div className="flex flex-col sm:flex-row sm:justify-between sm:items-start mb-3 gap-1">
        <span id={`cost-party-${cost.id}`} className="font-medium">
          {formatParty(cost.party)}
        </span>
        <span className="text-sm text-gray-500 capitalize">
          {cost.frequency.replace("_", " ")}
        </span>
      </div>

      <dl className="space-y-2 text-sm">
        {cost.time_display && (
          <div className="flex justify-between">
            <dt className="text-gray-600 dark:text-gray-400">Time cost:</dt>
            <dd className="font-medium">{cost.time_display}</dd>
          </div>
        )}

        {cost.money_cents !== null && (
          <div className="flex justify-between">
            <dt className="text-gray-600 dark:text-gray-400">Direct cost:</dt>
            <dd className="font-medium">{formatMoney(cost.money_cents, cost.money_display)}</dd>
          </div>
        )}

        {cost.assumed_time_value_cents !== null && (
          <div className="flex justify-between">
            <dt className="text-gray-600 dark:text-gray-400">Time value:</dt>
            <dd className="font-medium text-gray-500">
              {formatMoney(cost.assumed_time_value_cents, cost.assumed_time_value_display)}
            </dd>
          </div>
        )}

        {cost.is_indefinite === 1 && (
          <div
            className="mt-2 p-2 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded text-amber-800 dark:text-amber-200"
            role="alert"
          >
            <span className="font-medium">Indefinite cost: </span>
            <span>{cost.notes || "Cost cannot be quantified"}</span>
          </div>
        )}

        {cost.notes && cost.is_indefinite !== 1 && (
          <div className="mt-2">
            <dt className="sr-only">Notes</dt>
            <dd className="text-gray-600 dark:text-gray-400 italic">{cost.notes}</dd>
          </div>
        )}
      </dl>
    </article>
  );
}

export default async function LegislationPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const decodedId = decodeURIComponent(id);
  const data = await getLegislationWithCosts(decodedId);

  if (!data) {
    notFound();
  }

  const { legislation, complianceCosts, enforcementCosts } = data;
  const topics = JSON.parse(legislation.topics || "[]") as string[];

  return (
    <article>
      {/* Header */}
      <header className="mb-6 sm:mb-8">
        <nav aria-label="Breadcrumb" className="text-sm text-gray-500 dark:text-gray-400 mb-2">
          <Link
            href="/"
            className="hover:text-blue-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 rounded-sm"
          >
            ← Back to list
          </Link>
        </nav>
        <h1 className="text-xl sm:text-2xl font-bold mb-2">{legislation.title}</h1>
        <div className="flex flex-wrap gap-2 text-xs sm:text-sm text-gray-600 dark:text-gray-400">
          <span className="px-2 py-0.5 bg-gray-100 dark:bg-gray-800 rounded">
            {formatJurisdiction(legislation.jurisdiction)}
          </span>
          <span className="px-2 py-0.5 bg-gray-100 dark:bg-gray-800 rounded capitalize">
            {legislation.type.replace("_", " ")}
          </span>
          {legislation.analysis_status === "complete" && (
            <span className="px-2 py-0.5 bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-300 rounded">
              Analyzed
            </span>
          )}
        </div>
      </header>

      {/* Metadata */}
      <section className="mb-6 sm:mb-8 grid grid-cols-1 md:grid-cols-2 gap-4" aria-label="Legislation details">
        <div className="p-3 sm:p-4 border border-gray-200 dark:border-gray-800 rounded-lg">
          <h2 className="font-semibold mb-3">Details</h2>
          <dl className="space-y-2 text-sm">
            {legislation.citation && (
              <div>
                <dt className="text-gray-600 dark:text-gray-400">Citation</dt>
                <dd className="font-medium">{legislation.citation}</dd>
              </div>
            )}
            <div>
              <dt className="text-gray-600 dark:text-gray-400">Date Enacted</dt>
              <dd className="font-medium">
                {legislation.date_enacted ? (
                  <time dateTime={legislation.date_enacted}>
                    {formatDate(legislation.date_enacted)}
                  </time>
                ) : (
                  "—"
                )}
              </dd>
            </div>
            {legislation.date_repealed && (
              <div>
                <dt className="text-gray-600 dark:text-gray-400">Date Repealed</dt>
                <dd className="font-medium">
                  <time dateTime={legislation.date_repealed}>
                    {formatDate(legislation.date_repealed)}
                  </time>
                </dd>
              </div>
            )}
            {legislation.source_url && (
              <div>
                <dt className="text-gray-600 dark:text-gray-400">Source</dt>
                <dd>
                  <a
                    href={legislation.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-blue-600 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 rounded-sm"
                    aria-label="View original source (opens in new tab)"
                  >
                    View original
                  </a>
                </dd>
              </div>
            )}
          </dl>
        </div>

        {topics.length > 0 && (
          <div className="p-3 sm:p-4 border border-gray-200 dark:border-gray-800 rounded-lg">
            <h2 className="font-semibold mb-3">Topics</h2>
            <nav aria-label="Related topics">
              <ul className="flex flex-wrap gap-2">
                {topics.map((topic) => (
                  <li key={topic}>
                    <Link
                      href={`/topics/${encodeURIComponent(topic)}`}
                      className="inline-block px-2 py-1 bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-300 rounded text-sm hover:bg-blue-200 dark:hover:bg-blue-900/50 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                    >
                      {topic}
                    </Link>
                  </li>
                ))}
              </ul>
            </nav>
          </div>
        )}
      </section>

      {/* Compliance Costs */}
      <section className="mb-6 sm:mb-8" aria-labelledby="compliance-costs-heading">
        <h2 id="compliance-costs-heading" className="text-lg sm:text-xl font-semibold mb-4">
          Compliance Costs
        </h2>
        {complianceCosts.length === 0 ? (
          <div
            className="p-6 text-center text-gray-500 border border-gray-200 dark:border-gray-800 rounded-lg"
            role="status"
          >
            {legislation.analysis_status === "complete"
              ? "No compliance costs identified for this legislation"
              : "Analysis pending"}
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 sm:gap-4">
            {complianceCosts.map((cost) => (
              <CostCard key={cost.id} cost={cost} />
            ))}
          </div>
        )}
      </section>

      {/* Enforcement Costs */}
      <section className="mb-6 sm:mb-8" aria-labelledby="enforcement-costs-heading">
        <h2 id="enforcement-costs-heading" className="text-lg sm:text-xl font-semibold mb-4">
          Enforcement Costs
        </h2>
        {enforcementCosts.length === 0 ? (
          <div
            className="p-6 text-center text-gray-500 border border-gray-200 dark:border-gray-800 rounded-lg"
            role="status"
          >
            {legislation.analysis_status === "complete"
              ? "No enforcement costs identified for this legislation"
              : "Analysis pending"}
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 sm:gap-4">
            {enforcementCosts.map((cost) => (
              <CostCard key={cost.id} cost={cost} />
            ))}
          </div>
        )}
      </section>

      {/* Legislation Text */}
      {legislation.text_excerpt && (
        <section className="mb-6 sm:mb-8" aria-labelledby="legislation-text-heading">
          <h2 id="legislation-text-heading" className="text-lg sm:text-xl font-semibold mb-4">
            Legislation Text
          </h2>
          <div className="p-3 sm:p-4 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg">
            <ExpandableText
              text={legislation.text_excerpt}
              previewLines={30}
              sourceUrl={legislation.source_url}
            />
          </div>
        </section>
      )}
    </article>
  );
}
