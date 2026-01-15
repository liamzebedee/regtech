# Website

## Purpose

Provide a beautiful, minimal interface for exploring Australian legislation and its associated compliance/enforcement costs. The website is the primary demo of the project's value.

## Acceptance Criteria

- **Index page**: lists all legislation
  - Ordered by date (default)
  - Filterable by topic tags/clusters, jurisdiction, date range
  - Search by title or keyword
- **Legislation detail page**: shows a single piece of legislation
  - Title, jurisdiction, dates, full text (or excerpt)
  - Compliance costs displayed per-party with:
    - Time (pretty format, e.g., "2 hours" or "3 days")
    - Money (pretty format, e.g., "$500" or "$1.2M")
    - Assumed time value (for time costs)
  - Enforcement costs displayed similarly
  - Notes explaining indefinite costs where applicable
- **Topic/cluster pages**: browse legislation grouped by topic
- Built with Next.js, TypeScript, React
- Responsive, works on mobile
- Minimal but aesthetically pleasing design

## Edge Cases

- Legislation with no cost data yet (analysis pending)
- Very long legislation text (pagination or collapsing)
- Topics with thousands of entries (pagination)
- Empty states (no results for filter/search)
- Accessibility (screen readers, keyboard navigation)

## Dependencies

- Database schema must be stable
- Database must be populated with at least sample data for development
- Cost model dictates what fields are displayed
