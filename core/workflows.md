# Development workflows

Workflows use roles only. Read bindings from `config.yaml` after applying overrides.

## End-to-end flow

```text
Requirement
  ↓
SPEC and acceptance criteria
  ↓
Investigation if needed
  ↓
Implementation
  ↓
Build and tests
  ↓
Review if needed
  ↓
Evidence-based fix loop
  ↓
Escalation only when threshold is reached
  ↓
Final verification
  ↓
DEV HANDOFF
  ↓
Return to ChatGPT for SPEC compliance review
```

## Shared execution loop

1. Read applicable project instructions and inspect only relevant context.
2. State or infer acceptance criteria; ask only when a missing choice materially changes the result.
3. Select the minimum route and assign a distinct deliverable to each role.
4. Execute sequentially when later work depends on earlier evidence. Parallelize only independent, non-writing analysis with disjoint scope.
5. Maintain one writer per file set. Re-read the working tree before integration.
6. Run proportional build/test/lint checks and diagnose failures before changing code again.
7. Review against acceptance criteria and generate the DEV HANDOFF from `handoff.md`.

## Trivial edit

- Use `quick_implement` or the active root Codex when switching costs more than the change.
- Do not create a formal spec, call an external model, or use `escalate`.
- Run the smallest meaningful verification.

## Clear feature

- Use `implement` from the supplied SPEC and acceptance criteria.
- Add `spec` only if a real architectural ambiguity appears.
- Add `quick_review` only when it checks a distinct risk in a meaningful diff.
- Root Codex integrates and verifies acceptance criteria.

## Existing system feature

- Use `investigate` when the change requires understanding unfamiliar execution, dependency, or data flow.
- Convert findings into a bounded implementation plan.
- Pass findings to `implement`; do not make the implementer rediscover the same system.
- Test affected behavior and add `quick_review` only for a distinct regression risk.

## Unknown bug

`investigate` must return:

1. Current understanding.
2. Relevant files and symbols.
3. Execution/dependency flow.
4. Ranked root-cause hypotheses.
5. Evidence for and against each hypothesis.
6. Risks and blast radius.
7. Recommended modification points.
8. Things not to change.
9. Suggested distinguishing and regression tests.

Give that artifact to `implement`, apply one evidence-supported fix, and run the smallest falsifying test. On failure, re-investigate only with the new evidence. Use `escalate` only after the configured threshold or explicit override.

## Large refactor

- Gather dependency/impact evidence with `investigate` when needed.
- Use `spec` for boundaries, invariants, compatibility, migration, and rollback decisions.
- Split work into reviewable implementation slices with exclusive ownership.
- Use `implement`, then broad relevant tests.
- Use `quick_review` or `independent_review` only for named risks.
- Use `escalate` only for a remaining material integration impasse after the threshold.

## High-risk work

Use stronger specification and independent review only for the actual risk. “品質優先” raises reasoning and verification quality but never means running every model.

## Completion gate

Before completion, confirm intended working-tree changes, real test/build results, acceptance-criteria status, independent verification of external advice, and unresolved risks. Then output the DEV HANDOFF. Do not write a handoff file unless the user requests it or project policy permits it.
