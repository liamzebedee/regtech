# Diagnose a Stuck Loop

When a loop isn't making progress, diagnose the root cause.

## Symptoms

1. **Infinite loop**: Same action repeated without state change
2. **Oscillation**: Alternating between two states
3. **Silent failure**: Loop runs but nothing happens
4. **Premature exit**: Loop stops before goal is reached

## Diagnostic Questions

### Is the state assessment working?
- Can the loop correctly identify what's done vs what remains?
- Is it reading stale state? (cached files, uncommitted changes)
- Are state indicators unambiguous?

### Is work item selection deterministic?
- Given the same state, does it pick the same item?
- Is prioritization clear or ambiguous?
- Are there circular dependencies between items?

### Is completion detection accurate?
- How does the loop know an item is done?
- Could it mark something done that isn't?
- Could it fail to recognize completion?

### Is the prompt clear?
- Would a fresh Claude instance know what to do?
- Are there implicit assumptions not stated?
- Is the goal measurable?

## Common Fixes

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| Repeats same action | State not updating | Ensure writes commit/flush |
| Picks wrong item | Ambiguous priority | Add explicit ordering |
| Never finishes | Completion unclear | Add verifiable done criteria |
| Oscillates | Competing goals | Resolve contradictions in spec |
| Silent failure | Error swallowed | Add explicit error logging |

## Adding Loop Detection

Add to the prompt:

```markdown
## Loop Detection
Before starting work, review SESSION_LOG.md:
- If the last 3 entries show the same approach, STOP
- Re-analyze the problem with fresh assumptions
- Consider if this item is blocked by something else
- Document the blocker and move to next item
```

## Supervisor Intervention

If worker loops are unreliable, add a supervisor:

```bash
# supervisor.sh
claude -p < PROMPT_supervise.md  # Watches loop.sh output, intervenes when stuck
```

The supervisor prompt should:
- Monitor for repeated failures
- Have authority to modify the worker's plan
- Escalate to human after N interventions
