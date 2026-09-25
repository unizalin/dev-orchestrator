# Changelog

All notable changes to Portable Dev Orchestrator are documented here.

## 2.2.1 — 2026-09-25

- 修正 App 已執行但使用者看不到介面的問題：啟動時直接顯示用量視窗。
- 保留原有選單列入口、30 秒本機刷新與登入時啟動功能。
- 新增可見視窗的 packaging regression test。

## 2.2.0 — 2026-09-24

- 新增 macOS 選單列 App，可直接查看已追蹤任務的五小時用量。
- 新增 `scripts/build_macos_app.sh` 與 `scripts/install_macos_app.sh` 的建置、簽署與安全安裝流程。
- 補強 portable、macOS manifest、版本來源與完整驗證入口。
- README 補充 GUI 範圍、隱私、刷新與帳號／專案篩選語意。

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
