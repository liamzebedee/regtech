"use client";

/**
 * Expandable Text Component
 *
 * WHY: Legislation text can be very long (thousands of lines). This component
 * shows a preview by default and expands to show full content when clicked.
 * Improves page load performance and keeps the UI clean.
 *
 * Accessibility: Uses aria-expanded and aria-controls to communicate state to
 * screen readers. Provides unique IDs for ARIA relationships.
 */

import { useState, useId } from "react";

interface ExpandableTextProps {
  text: string;
  previewLines?: number;
  sourceUrl?: string | null;
}

export default function ExpandableText({
  text,
  previewLines = 30,
  sourceUrl,
}: ExpandableTextProps) {
  const [expanded, setExpanded] = useState(false);
  const contentId = useId();

  const lines = text.split("\n");
  const isLong = lines.length > previewLines;
  const displayText = expanded ? text : lines.slice(0, previewLines).join("\n");

  return (
    <div className="relative">
      <pre
        id={contentId}
        className={`whitespace-pre-wrap font-mono text-sm text-gray-700 dark:text-gray-300 ${
          !expanded && isLong ? "max-h-[400px] overflow-hidden" : ""
        }`}
        tabIndex={0}
        aria-label={`Legislation text, ${lines.length} lines${!expanded && isLong ? ", currently showing preview" : ""}`}
      >
        {displayText}
        {!expanded && isLong && "..."}
      </pre>

      {isLong && (
        <div
          className={`${
            !expanded
              ? "absolute bottom-0 left-0 right-0 bg-gradient-to-t from-gray-50 dark:from-gray-900 pt-16"
              : "mt-4"
          }`}
        >
          <button
            onClick={() => setExpanded(!expanded)}
            aria-expanded={expanded}
            aria-controls={contentId}
            className="w-full py-2 text-sm text-blue-600 hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-300 font-medium focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 rounded-md transition-colors"
          >
            {expanded ? "Show less" : `Show all ${lines.length} lines`}
          </button>
        </div>
      )}

      {sourceUrl && (
        <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-800">
          <a
            href={sourceUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm text-blue-600 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 rounded-sm"
            aria-label="View full text on official source (opens in new tab)"
          >
            View full text on official source →
          </a>
        </div>
      )}
    </div>
  );
}
