# Routing policy

Resolve provider/model bindings from `config.yaml`. Apply task-scoped overrides from `overrides.md` before selecting roles.

## Model-binding guard

When `limits.strict_openai_role_binding` is enabled, a selected OpenAI role must
run on the model bound to that role. In particular, `implement` and
`quick_implement` are bound to Luna and must not silently fall back to the
currently selected Sol model. If the active picker does not match, pause before
writing and ask the user to switch the picker to Luna, unless the user gave an
explicit model override. `escalate` remains the only automatic Sol path after
the configured failure threshold.

## Decision order

1. Apply read-only, safety, and explicit negative constraints.
2. Apply an explicit provider/model or named-mode instruction.
3. Classify the task.
4. Choose the smallest role sequence whose members produce distinct information.
5. Remove optional calls whose expected information gain does not justify the cost.

When instructions conflict, the more specific and more recent instruction wins, except that safety and read-only constraints remain binding.

## Default routes

| Class | Signals | Initial route |
|---|---|---|
| TRIVIAL | Typo, rename, simple CSS, obvious one-line change | `quick_implement` → targeted verification |
| CLEAR FEATURE | SPEC and acceptance criteria are clear; affected area is known | `implement` → tests → verification |
| EXISTING SYSTEM FEATURE | Change is clear but requires understanding an older/unfamiliar system | optional `investigate` → implementation plan → `implement` → tests → optional `quick_review` |
| UNKNOWN BUG | Cause or blast radius is unknown | `investigate` → `implement` → focused test; repeat only with new evidence |
| LARGE REFACTOR | Cross-module/API/data-flow change or migration risk | dependency/impact `investigate` → `spec` if needed → implementation slices → `implement` → tests → risk-based review |
| HIGH RISK | Security, data loss, irreversible migration, concurrency, or public compatibility risk | add `spec` and/or `independent_review` only for the specific risk |

Skip `spec` when requirements and architecture are already settled. Skip external investigation when local inspection answers the question. Never put `escalate` in the initial automatic route.

## Distinct-information rule

Each call must have a unique deliverable:

- `spec`: design decisions and acceptance boundaries;
- `investigate`: evidence, flow/dependency map, ranked hypotheses, or impact map;
- `implement`/`quick_implement`: repository change and focused tests;
- `quick_review`: concrete findings in an existing diff;
- `independent_review`: an independent assessment of a named high-risk concern;
- `escalate`: resolution of a documented impasse.

Do not send the same open-ended prompt to multiple models and vote on answers. Pass artifacts forward so later roles build on earlier work.

## Escalation accounting

Count an attempt only when it includes a new evidence-supported hypothesis or implementation and the relevant check still fails for the target problem.

Do not count reruns, transport failures, unavailable models, sandbox/permission errors, unrelated flaky tests, or untested suggestions. Use `escalate` only at `limits.sol_min_failed_attempts`, when the problem remains material, and when Sol is not disabled. Provide all failed hypotheses, evidence, changed files, and exact failing checks.
