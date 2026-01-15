# Effective Prompt Patterns for Cost Extraction

## Overview

This document describes the prompt engineering patterns that proved effective for extracting compliance and enforcement costs from Australian legislation.

## Pattern 1: Role Definition

**Pattern**: Establish the model as an expert analyst at the start.

```markdown
You are an expert analyst extracting compliance and enforcement costs from Australian legislation.
```

**Why it works**:
- Sets appropriate context for legal interpretation
- Establishes the expected level of analysis sophistication
- Primes the model for structured, analytical output

## Pattern 2: Structured Output Schema

**Pattern**: Provide a detailed JSON schema with examples.

```json
{
  "party": "citizen|business|...",
  "description": "What the party must do",
  "time": { "amount": 2, "unit": "hours" },
  "money": { "amount_aud": 500 }
}
```

**Why it works**:
- Eliminates ambiguity in output format
- Enables programmatic parsing without post-processing
- Constrains outputs to valid enum values
- Examples demonstrate expected granularity

## Pattern 3: Explicit Party Enumeration

**Pattern**: Define all valid party types upfront.

```markdown
## Party Types
- `citizen`: Individual natural persons
- `business`: Commercial entities generally
- `small_business`: Businesses under 20 employees
- `large_business`: Businesses over 200 employees
- `government`: Government entities (as regulated parties)
- `nonprofit`: Non-profit organizations
```

**Why it works**:
- Prevents invention of non-standard party types
- Ensures consistent categorization across documents
- Clear definitions reduce ambiguous classifications
- Distinguishes government-as-regulator from government-as-regulated

## Pattern 4: Concrete Examples

**Pattern**: Include 3+ examples covering different scenarios.

1. **Registration requirement** - Clear, quantifiable costs
2. **Burden of proof reversal** - Indefinite costs
3. **Declarative legislation** - No costs

**Why it works**:
- Demonstrates handling of edge cases
- Shows appropriate use of null values
- Calibrates estimation scale (hours vs days)
- Illustrates when to use indefinite flags

## Pattern 5: Conservative Estimation Guidelines

**Pattern**: Explicit instructions to avoid over-estimation.

```markdown
1. Be conservative: If unsure, provide a range or mark confidence as "low"
2. Focus on direct costs: Don't speculate about indirect impacts
3. Typical case: Estimate for average case, not extreme scenarios
4. Null if not applicable: Set fields to null, not zero
```

**Why it works**:
- Prevents inflation of cost estimates
- Produces more defensible numbers
- Acknowledges uncertainty explicitly
- Distinguishes "no cost" from "unknown cost"

## Pattern 6: Multi-Party Instruction

**Pattern**: Explicitly request separate entries per party.

```markdown
Multiple parties: Create separate entries for each party type affected
```

**Why it works**:
- Legislation often affects different parties differently
- Prevents combining disparate costs into single entry
- Enables party-specific queries and aggregations
- More accurate total cost calculations

## Pattern 7: Null vs Zero Distinction

**Pattern**: Clarify that absence of cost should be null, not zero.

```markdown
No cost is valid: If legislation is purely declarative with no compliance burden,
set `has_compliance_costs` to false and leave `compliance_costs` empty
```

**Why it works**:
- Zero cost could mean "free" (actual cost) or "not analyzed"
- Null clearly indicates "not applicable"
- Prevents misleading aggregations
- More accurate filtering queries

## Pattern 8: Reasoning Exposure

**Pattern**: Request explanations in notes fields.

```markdown
Explain reasoning: Use the `notes` fields to explain how you arrived at estimates
```

**Why it works**:
- Enables human review of methodology
- Catches obvious errors in reasoning
- Provides context for unusual estimates
- Documents assumptions for future reference

## Pattern 9: Current Value Standardization

**Pattern**: Request costs in current currency.

```markdown
Use current values: Express monetary costs in current AUD, even for historical legislation
```

**Why it works**:
- Enables meaningful comparison across time periods
- Avoids confusion about inflation adjustment
- Simplifies aggregation queries
- Notes field can capture original historical amounts

## Pattern 10: Topic Vocabulary

**Pattern**: Provide predefined topic tags with categories.

```markdown
Use lowercase, hyphenated terms from this list when applicable:
- `taxation`, `business-registration`, `environmental`, `workplace-safety`
- `financial-services`, `healthcare`, `transport`, `construction`
```

**Why it works**:
- Ensures consistent categorization
- Enables meaningful topic aggregations
- Prevents proliferation of synonymous tags
- Allows custom tags for unusual legislation

## Pattern 11: Reference Tracking

**Pattern**: Request explicit tracking of external legislation references.

```markdown
Look for:
- Direct references: "as defined in the [Act Name]"
- Penalty definitions: "penalty units as defined in [Act]"
- Incorporated standards: "must comply with [External Act]"
```

**Why it works**:
- Maps legislative dependencies
- Flags potentially incomplete analyses
- Enables cross-reference queries
- Identifies amendment chains

## Pattern 12: Confidence Calibration

**Pattern**: Define what each confidence level means.

```markdown
"confidence": "high|medium|low"
```

With implicit calibration from examples:
- High: Clear requirements, explicit costs (registration fee example)
- Medium: Inferred costs, some uncertainty (burden of proof example)
- Low: Missing context, significant guesswork

**Why it works**:
- Enables filtering by reliability
- Flags analyses needing review
- Honest about limitations
- Supports quality metrics

## Anti-Patterns to Avoid

### 1. Vague Output Instructions
**Bad**: "Return the costs you find"
**Good**: Explicit JSON schema with required fields

### 2. Unbounded Enumeration
**Bad**: "List all affected parties"
**Good**: Explicit enum of valid party types

### 3. Implicit Null Handling
**Bad**: "Include time costs if any"
**Good**: "Set `time` to null if no time cost, not zero"

### 4. Missing Examples
**Bad**: Schema only with no examples
**Good**: 3+ examples covering edge cases

### 5. Optimistic Estimation Bias
**Bad**: "Estimate all relevant costs"
**Good**: "Be conservative, prefer lower bounds"
