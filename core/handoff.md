# DEV HANDOFF protocol

Produce this handoff after a complete development task. Report actual work only, not the theoretical route.

```markdown
# DEV HANDOFF

## Goal

<original requirement>

## Status

<COMPLETED | PARTIAL | BLOCKED>

## Routing Used

- spec: <actual model or not used>
- investigate: <actual model or not used>
- implement: <actual model or active Codex fallback>
- quick_review: <actual model or not used>
- escalation: <actual model or not used>
- independent_review: <actual model or not used>

## Changed Files

- <actual path>

## What Changed

<implementation summary>

## Tests / Build

- <command>: <PASS | FAIL | NOT RUN>

## Acceptance Criteria

- [x] <verified criterion>
- [ ] <unmet or unverified criterion>

## Important Decisions

<implementation or architecture decisions>

## Risks / Open Questions

<remaining risks or None>

## Token Usage (optional)

Include this section only when exact usage data exists for the current project. Show the current-project table with exact input/output/total tokens and account attribution; use `N/A` when a selected row has no exact value. Do not infer or combine unavailable data, and keep quota percentages separate for each account.

## Diff Summary

<concise diff description>

## Recommended Next Step

<next action>

## RETURN TO CHATGPT

=== RETURN TO CHATGPT ===

Original Goal:
...

Implementation Status:
...

Acceptance Criteria:
...

Important Changes:
...

Tests:
...

Unresolved Risks:
...

Please review this implementation against the original SPEC and decide whether it is complete or requires another iteration.

=== END RETURN ===
```

Status must be exactly `COMPLETED`, `PARTIAL`, or `BLOCKED`. A test that was not executed must say `NOT RUN`; never infer PASS. Acceptance criteria must be checked individually.

Default to terminal/chat output. Write `.dev-orchestrator/handoffs/latest.md` only when the user requests it or project policy permits it. Before creating `.dev-orchestrator/`, inspect `.gitignore`; do not stage or commit the handoff unless explicitly requested.
