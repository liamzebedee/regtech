# Cost Model

## Purpose

Define a consistent framework for measuring and representing the costs of compliance and enforcement across all legislation. This model must capture both discrete costs (time, money) and indefinite costs (liability transfers, burden of proof shifts) in a way that enables meaningful comparison.

## Acceptance Criteria

- **Compliance costs** are captured per-party (multiple parties may bear different costs for the same legislation)
- **Enforcement costs** are captured as costs borne by the state
- Discrete costs have two dimensions:
  - Time (hours/days, pretty-formatted for display)
  - Money (AUD, pretty-formatted for display)
- Where cost is time, an `assumed_time_value` is calculated using minimum wage (or contextually appropriate rate for the actor type)
- Non-discrete costs (e.g., reversed burden of proof) are flagged as "indefinite cost" with explanatory notes
- The model supports comparison/aggregation across legislation (e.g., total cost by topic area, by jurisdiction, by year)

## Edge Cases

- Legislation with zero measurable cost (purely declarative/ceremonial)
- Costs that vary wildly based on business size (compliance cost for a 5-person business vs 5000-person business)
- Costs that are one-time vs recurring (annual filing requirements)
- Costs that are conditional (only triggered if certain conditions met)
- How to handle amendments that modify costs of existing legislation
- Currency/wage rate changes over time (historical vs present value)

## Dependencies

- Analysis pipeline must be designed to extract and structure costs in this format
- Database schema must store all cost dimensions
- Website must display costs in human-readable formats
