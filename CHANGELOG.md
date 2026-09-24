# Changelog

All notable changes to Portable Dev Orchestrator are documented here.

## 2.1.0 — 2026-09-24

- Added opt-in, local-only terminal token usage tracking for Codex and Antigravity runs.
- Added account/project/role/model totals, exact-versus-`N/A` display semantics, and optional per-account tokscale quota reporting.
- Packaged the usage command in Codex installs while keeping ChatGPT exports free of local scripts.

## 2.0.0 — 2026-09-23

- Established `~/Projects/dev-orchestrator/` as the portable source of truth.
- Added separate Codex and ChatGPT Agent Skill adapters.
- Preserved role-based model routing with runtime Antigravity discovery.
- Added task-scoped natural-language overrides and the two-failure Sol escalation gate.
- Added the DEV HANDOFF and RETURN TO CHATGPT protocol.
- Added safe Codex installation with versioned backup and rollback.
- Added ChatGPT export with an uploadable Skill zip and text fallbacks.
- Added 13 deterministic routing, safety, adapter, and drift checks.
- Published the source under the MIT License.
- Kept generated exports and local environment files out of version control.
