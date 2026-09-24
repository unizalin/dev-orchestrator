# Model roles

`config.yaml` is the only provider/model binding source. This document defines responsibilities; it must not duplicate model IDs.

## Roles

### `spec`

Turn large, ambiguous, architectural, or high-risk requirements into boundaries, invariants, acceptance criteria, migration/rollback decisions, and implementation slices. Skip for precise low-risk work.

### `implement`

Primary implementation role for clear features, fixes, and refactors. Adjust reasoning effort to complexity. Produce scoped changes and focused tests.

### `quick_implement`

Handle trivial, reversible, obvious changes with minimal overhead and targeted verification.

### `investigate`

Read-only evidence gathering for unfamiliar systems, dependencies, impact analysis, and unknown bugs. Its output is a handoff to implementation, not a competing implementation.

### `quick_review`

Review an existing diff for concrete regressions, correctness gaps, security/performance risks, or missed acceptance criteria. Do not redesign the feature or repeat investigation.

### `escalate`

Resolve a documented material impasse after the configured number of independent evidence-based failures, or when the user explicitly requests it. This role is never the default developer.

### `independent_review`

Provide a genuinely independent perspective for explicit requests or high-risk/security/data-loss/API-compatibility changes. It is not a mandatory second opinion.

## Binding rules

- Workflows use role names only.
- Read the binding from `config.yaml` after applying task-scoped overrides.
- Do not claim a model was used unless its invocation succeeded.
- If a configured model is unavailable, select the closest available model for the same role and disclose the fallback. Never silently change the role.
- If model switching is unavailable, root Codex may perform an OpenAI role locally and must report the fallback.
