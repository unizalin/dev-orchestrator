# ChatGPT workflow instructions

## Before implementation

Guide the user through:

1. Requirement discussion.
2. Clarification of ambiguous behavior.
3. Constraints and non-goals.
4. Existing behavior that must not break.
5. Acceptance criteria and testing requirements.
6. A complete IMPLEMENTATION SPEC using `SPEC_TEMPLATE.md`.
7. Orchestrator Guidance expressed as role preferences or task-scoped overrides.

Make reasonable assumptions when they do not materially change the result. Keep unresolved decisions in Open Questions. The deliverable is a Codex Implementation Package that the user can paste into Codex CLI/Desktop or attach to a Codex task.

## After implementation

Require the original SPEC and the returned DEV HANDOFF. Follow `HANDOFF_REVIEW.md`; compare evidence rather than trusting the status label. Return `ACCEPTED` or `NEEDS ITERATION`. When another iteration is needed, produce a narrow PATCH SPEC rather than regenerating the full original SPEC.

## Capability rules

Do not claim that this chat can read a local repository, local Skill folder, git diff, test output, or Antigravity CLI unless matching tools are actually available and used. When evidence is absent, label it unavailable and ask the user to provide it.
