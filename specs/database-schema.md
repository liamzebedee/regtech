# Database Schema

## Purpose

Store legislation metadata and cost analysis results in SQLite for consumption by the website. The schema must support efficient querying for browsing, filtering, and aggregation.

## Acceptance Criteria

- **Legislation table**: stores core metadata
  - Identifier, title, jurisdiction, date enacted, date repealed (if applicable)
  - Full text or reference to text location
  - Topic tags/clusters
  - Analysis status (pending, complete, failed)
- **Costs table**: stores cost analysis per legislation
  - Foreign key to legislation
  - Cost type (compliance or enforcement)
  - Party/actor bearing the cost
  - Time cost (hours, with unit)
  - Money cost (AUD)
  - Assumed time value (calculated from time + wage rate)
  - Indefinite flag with explanation note
- Indexes on: date, jurisdiction, topic tags, cost values
- Query performance is acceptable for website use (index of all legislation loads in <2s)
- Database is a single SQLite file that can be committed or deployed with the app

## Edge Cases

- Multiple cost entries per legislation (different parties, different cost types)
- Legislation amendments that modify a parent act (versioning/relationship tracking)
- Very large text fields (full legislation text may be megabytes)
- Concurrent writes from parallel analysis workers
- Schema migrations if the cost model evolves

## Dependencies

- Cost model must be finalized before schema design
- Analysis pipeline writes to this database
- Website reads from this database
