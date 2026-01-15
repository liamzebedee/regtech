# Create a Self-Improving Loop

Create a new loop for a specific work area.

## What You Need

1. **Work area name**: A slug for the folder (e.g., `analysis`, `migration`, `review`)
2. **Goal**: What should be true when the loop is done?
3. **Work items source**: Where does the loop find what to do? (specs/, a plan file, a queue)
4. **State indicators**: How does the loop know what's already done?

## Template: loop.sh

```bash
#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MAX_ITERATIONS=${1:-0}
ITERATION=0

while true; do
    if [ $MAX_ITERATIONS -gt 0 ] && [ $ITERATION -ge $MAX_ITERATIONS ]; then
        echo "Reached max iterations: $MAX_ITERATIONS"
        break
    fi

    cat "$SCRIPT_DIR/PROMPT.md" | claude -p \
        --dangerously-skip-permissions \
        --model sonnet

    ITERATION=$((ITERATION + 1))
    echo "======================== LOOP $ITERATION ========================"
done
```

## Template: PROMPT.md

```markdown
## State Assessment
1. Read [state source] to understand current state
2. Read [goal source] to understand desired state
3. Compare and identify remaining work

## Work Selection
1. Read implementation_plan.md for prioritized items
2. Select the highest priority incomplete item
3. If no items remain, exit with "DONE"

## Execution
1. Complete the selected work item
2. Verify completion (tests, validation, etc.)
3. Update implementation_plan.md with results

## Logging
- Log what was attempted and learned
- If stuck after 3 similar attempts, document blockers and pause
```

## Template: implementation_plan.md

```markdown
## Work Queue

- [ ] Item 1
- [ ] Item 2
- [ ] Item 3

## Progress Log

| Iteration | Item | Result | Notes |
|-----------|------|--------|-------|
```

## Reference

See `ralph/` for examples:
- `ralph/loop.sh` - Production loop runner
- `ralph/PROMPT_build.md` - Build mode prompt
- `ralph/PROMPT_plan.md` - Planning mode prompt
