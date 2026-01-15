/**
 * Topics Index Page
 *
 * WHY: Enables browsing legislation by topic/category. Users can quickly
 * find legislation related to their area of interest (taxation, healthcare, etc.)
 * rather than scanning through thousands of entries chronologically.
 */

import { getDatabase } from "@/lib/db";
import Link from "next/link";

// Force dynamic rendering since we need database access
export const dynamic = "force-dynamic";

interface TopicWithCount {
  topic: string;
  count: number;
  displayName: string;
}

/**
 * Get all topics with their legislation counts.
 * Topics are stored as JSON arrays in the legislation table.
 */
async function getTopicsWithCounts(): Promise<TopicWithCount[]> {
  const db = getDatabase();

  // Get all topics from analyzed legislation
  const rows = db
    .prepare(
      `SELECT topics FROM legislation
       WHERE analysis_status = 'complete' AND topics IS NOT NULL AND topics != '[]'`
    )
    .all() as { topics: string }[];

  // Count occurrences of each topic
  const topicCounts = new Map<string, number>();

  for (const row of rows) {
    try {
      const topics = JSON.parse(row.topics) as string[];
      for (const topic of topics) {
        topicCounts.set(topic, (topicCounts.get(topic) || 0) + 1);
      }
    } catch {
      // Skip malformed JSON
    }
  }

  // Convert to array and sort by count descending
  const result: TopicWithCount[] = Array.from(topicCounts.entries())
    .map(([topic, count]) => ({
      topic,
      count,
      displayName: formatTopicName(topic),
    }))
    .sort((a, b) => b.count - a.count);

  return result;
}

/**
 * Format topic slug to display name.
 * e.g., "workplace-safety" -> "Workplace Safety"
 */
function formatTopicName(topic: string): string {
  return topic
    .split("-")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

/**
 * Group topics by category for better organization.
 */
function groupTopicsByCategory(topics: TopicWithCount[]): Map<string, TopicWithCount[]> {
  const categories: Record<string, string[]> = {
    Business: [
      "taxation",
      "business-registration",
      "financial-services",
      "licensing",
      "trade",
      "insurance",
      "superannuation",
      "corporate-governance",
      "competition",
    ],
    Environment: ["environmental", "agriculture", "mining", "energy", "land-use"],
    Social: ["healthcare", "education", "public-health", "employment", "civil-rights", "immigration"],
    Safety: ["workplace-safety", "food-safety", "consumer-protection", "transport", "construction"],
    Legal: ["criminal-justice", "privacy", "intellectual-property", "telecommunications"],
  };

  const grouped = new Map<string, TopicWithCount[]>();
  const categorized = new Set<string>();

  // Group known topics
  for (const [category, categoryTopics] of Object.entries(categories)) {
    const topicsInCategory = topics.filter((t) => categoryTopics.includes(t.topic));
    if (topicsInCategory.length > 0) {
      grouped.set(category, topicsInCategory);
      topicsInCategory.forEach((t) => categorized.add(t.topic));
    }
  }

  // Group uncategorized topics
  const uncategorized = topics.filter((t) => !categorized.has(t.topic));
  if (uncategorized.length > 0) {
    grouped.set("Other", uncategorized);
  }

  return grouped;
}

export default async function TopicsPage() {
  const topics = await getTopicsWithCounts();
  const groupedTopics = groupTopicsByCategory(topics);
  const totalLegislation = topics.reduce((sum, t) => sum + t.count, 0);

  return (
    <div>
      <h1 className="text-2xl font-bold mb-2">Browse by Topic</h1>
      <p className="text-gray-600 dark:text-gray-400 mb-6">
        {topics.length > 0
          ? `${topics.length} topics across ${totalLegislation} legislation entries`
          : "No topics available yet. Topics are extracted during legislation analysis."}
      </p>

      {topics.length === 0 ? (
        <div className="text-center py-12 text-gray-500 border border-dashed border-gray-300 dark:border-gray-700 rounded-lg">
          <p className="text-lg">No topics found</p>
          <p className="text-sm mt-2">
            Run the analysis pipeline to extract topics from legislation.
          </p>
          <code className="block mt-4 text-xs bg-gray-100 dark:bg-gray-800 p-2 rounded inline-block">
            python analysis/scripts/analyze_legislation.py --limit 100
          </code>
        </div>
      ) : (
        <div className="space-y-8">
          {Array.from(groupedTopics.entries()).map(([category, categoryTopics]) => (
            <section key={category}>
              <h2 className="text-lg font-semibold mb-3 text-gray-700 dark:text-gray-300">
                {category}
              </h2>
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
                {categoryTopics.map((topic) => (
                  <Link
                    key={topic.topic}
                    href={`/topics/${encodeURIComponent(topic.topic)}`}
                    className="block p-3 border border-gray-200 dark:border-gray-800 rounded-lg hover:border-blue-500 dark:hover:border-blue-500 transition-colors"
                  >
                    <div className="font-medium">{topic.displayName}</div>
                    <div className="text-sm text-gray-500 dark:text-gray-400">
                      {topic.count} {topic.count === 1 ? "entry" : "entries"}
                    </div>
                  </Link>
                ))}
              </div>
            </section>
          ))}
        </div>
      )}

      <div className="mt-8 pt-4 border-t border-gray-200 dark:border-gray-800">
        <Link href="/" className="text-blue-600 hover:text-blue-700">
          &larr; Back to all legislation
        </Link>
      </div>
    </div>
  );
}
