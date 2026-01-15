# Self-Improving Loops

A pattern for autonomous, supervised work using Claude in loops.

## The Pattern

Run Claude in a `while true` loop where each iteration:
1. Reads a prompt file (PROMPT.md)
2. Assesses current state vs desired state
3. Selects and completes a work item
4. Logs progress to a plan file
5. Repeats until done

## Core Principles

### Idempotency
Each iteration starts fresh. No memory of previous runs. The prompt must instruct Claude to:
- Read current state (files, git, database)
- Compare against desired state (specs, acceptance criteria)
- Identify what remains
- Work on closing the gap

### Context Management
Claude degrades at >50% context saturation. Keep loops fresh:
- Start clean each iteration
- Offload state to files, not conversation
- Keep prompts focused

### Supervisor Pattern
A meta-loop watches worker loops:
- Detects infinite loops (repeated actions without progress)
- Identifies stuck states
- Intervenes or escalates

### Loop Detection
Workers should log attempts to detect stuck states:
- Track approach, result, learnings per attempt
- After N similar failures, re-analyze or escalate

## Minimal Structure

```
work-area/
├── loop.sh              # while true; do claude -p < PROMPT.md; done
├── PROMPT.md            # What to do each iteration
└── implementation_plan.md   # Work queue and progress log
```

## Reference Implementation

See `ralph/` for a full implementation with:
- Multiple loop modes (build, plan, fix)
- Pretty-printed output formatting
- Git integration for commits after each iteration

## See Also

- `specs/self-improving-loops.md` - Full specification
