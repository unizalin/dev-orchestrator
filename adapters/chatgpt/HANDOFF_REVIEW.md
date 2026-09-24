# DEV HANDOFF review

Review the implementation against the original IMPLEMENTATION SPEC.

## Review steps

1. Compare the original goal, constraints, non-goals, and every acceptance criterion.
2. Confirm that claimed tests/builds show actual commands and results. Treat `NOT RUN` and missing evidence as unverified.
3. Check changed files and diff summary for specification drift or unrelated scope.
4. Examine important decisions, unresolved risks, and open questions.
5. Do not accept merely because the handoff status says `COMPLETED`.
6. Decide exactly one outcome: `ACCEPTED` or `NEEDS ITERATION`.

## Output

```markdown
# SPEC COMPLIANCE REVIEW

## Decision

<ACCEPTED | NEEDS ITERATION>

## Acceptance Criteria Review

- [x] <verified>
- [ ] <missing, failed, or unverified>

## Test Evidence Review

<what was actually run and what remains unverified>

## Specification Drift

<drift or None>

## Remaining Risks

<risks or None>
```

If the decision is `NEEDS ITERATION`, append:

```markdown
# PATCH SPEC

## Problem to Fix

## Required Changes

## Acceptance Criteria

## Tests Required

## Do Not Change
```

The PATCH SPEC must describe only the missing or incorrect work. Do not regenerate the full original SPEC.
