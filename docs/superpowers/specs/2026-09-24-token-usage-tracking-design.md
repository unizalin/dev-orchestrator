# Dev Orchestrator Token Usage Tracking Design

**Status:** Approved design, pending implementation plan  
**Date:** 2026-09-24  
**Target:** Portable Dev Orchestrator 2.1

## Context

Portable Dev Orchestrator routes work across roles such as `spec`, `implement`, `investigate`, `quick_review`, and `escalate`, but it does not currently show whether that split saves or consumes more tokens. The desired experience is inspired by [TokenBar](https://github.com/Nanako0129/TokenBar) and its [tokscale](https://github.com/junhoyeo/tokscale) data layer, while remaining a terminal-only feature focused on orchestrated development work.

TokenBar and tokscale already demonstrate reliable local parsing and aggregation across Codex, Claude Code, Antigravity, and other agent clients. Dev Orchestrator should not duplicate their full parser and pricing surface. It needs a small attribution layer that records which project, account alias, task, role, and model produced each usage event.

## Goals

- Show token usage for the current project and across all projects.
- Show a rolling five-hour usage window.
- Break usage down by account alias, orchestrator role, provider, and model.
- Preserve per-account records while allowing same-project and all-project totals.
- Keep provider quota percentages separate per account.
- Attribute root Codex usage to role checkpoints within one session.
- Capture exact Antigravity usage from `agy --output-format json`.
- Work without a background service or cloud account.
- Store no prompts, responses, credentials, OAuth tokens, or API keys.
- Use tokscale as an optional source for history, other clients, and vendor quota data.

## Non-goals

- A macOS menu-bar app, web dashboard, or long-running TUI.
- Reimplementing TokenBar or tokscale-core.
- Cloud sync, leaderboards, or remote telemetry.
- Estimating unavailable usage and presenting it as exact.
- Combining quota percentages from separate accounts.
- Complete historical role attribution for sessions recorded before this feature exists.
- Token pricing or cost optimization in the first release.

## Chosen Approach

Use a hybrid model:

1. A Dev Orchestrator ledger is authoritative for project, account, task, role, and model attribution.
2. Codex usage is read from the current session's `token_count` events, located with `CODEX_SESSION_ID` and `CODEX_THREAD_ID`.
3. Antigravity usage is captured from the JSON returned by `agy`.
4. tokscale is an optional adapter for historical sessions, other agent clients, workspace aggregation, and subscription quota data.
5. Terminal reports join and aggregate these sources without modifying their original records.

This avoids a tokscale fork while filling the account and role attribution gaps that generic session parsers cannot infer reliably.

## Architecture

### Usage recorder

The recorder creates append-only usage events and exposes four operations:

- `start`: identify the project, task, Codex session, thread, active account alias, and initial Codex cumulative token snapshot.
- `checkpoint`: capture the next Codex cumulative snapshot and assign the delta since the previous checkpoint to a role and model.
- `record-external`: normalize one completed external-agent JSON result, including its provider conversation ID.
- `finish`: capture any final Codex delta and mark the task complete, partial, or blocked.

Checkpoints occur at meaningful role boundaries, not after every assistant message. Examples include `spec → implement`, `investigate → implement`, and `implement → quick_review`.

### Codex session reader

The reader locates the current JSONL session by session or thread ID and reads only metadata and `token_count` events. It never reads or stores user messages, assistant messages, reasoning text, tool output, or file contents.

Codex cumulative usage is converted to phase usage by subtracting the previous checkpoint. A negative delta, missing session, or malformed event is recorded as unavailable rather than zero.

### Antigravity adapter

External-agent invocations use `agy --output-format json`. The adapter records the returned conversation ID, duration, provider/model binding, and usage fields. Prompts and responses are not copied into the ledger.

The observed Antigravity schema provides input, output, thinking, cache-read, and total token counts. The adapter preserves the raw usage object alongside normalized numeric fields so future schema changes can be handled without fabricating values.

### Optional tokscale adapter

When `tokscale` is installed, the reporter may use its JSON output for:

- existing Codex, Claude Code, and Antigravity history;
- workspace/model and session/model grouping;
- worktree-to-repository rollup;
- vendor-reported quota windows and reset times;
- saved Codex account quota cards.

The feature must remain usable when tokscale is absent. Installation is never automatic.

### Account registry

Users configure local aliases such as `personal` and `work`. The registry stores aliases and the currently active alias, not account email addresses or credentials.

If tokscale exposes an active saved Codex account alias, it may be used as an optional source. Otherwise the user changes the local alias explicitly when switching accounts. Switching accounts during one task creates separate events under the same project and task.

### Project identity

For a Git repository, the project key is derived from the repository's common Git directory so worktrees roll up to one project. The display label defaults to the repository directory name. A stable local fingerprint may include normalized remote metadata, but reports do not expose credentials embedded in remote URLs.

Outside Git, the normalized working directory is the project key. Project aliases can override the display label.

### Ledger storage

Usage state lives outside repositories under a configurable state directory. The macOS default is `~/Library/Application Support/dev-orchestrator/usage/`; other platforms use `${XDG_STATE_HOME:-~/.local/state}/dev-orchestrator/usage/`. `DEV_ORCHESTRATOR_STATE_DIR` overrides either default.

Events are stored as monthly append-only JSONL files. Writers use a file lock and one complete line per event so parallel Codex tasks cannot overwrite each other. Reports deduplicate using a stable event ID.

No ledger or generated report is committed to a project repository.

## Event Model

Each normalized event contains:

```json
{
  "schema_version": 1,
  "event_id": "stable-id",
  "recorded_at": "2026-09-24T09:00:00+08:00",
  "started_at": "2026-09-24T08:58:00+08:00",
  "completed_at": "2026-09-24T09:00:00+08:00",
  "project_key": "local-project-fingerprint",
  "project_label": "dev-orchestrator",
  "account_alias": "personal",
  "task_id": "local-task-id",
  "thread_id": "codex-thread-id",
  "session_id": "provider-session-id",
  "conversation_id": null,
  "role": "implement",
  "provider": "openai",
  "model": "gpt-5.6-luna",
  "source": "codex-session",
  "precision": "exact",
  "usage": {
    "input_tokens": 82400,
    "cache_read_tokens": 61200,
    "cache_write_tokens": 0,
    "output_tokens": 2100,
    "thinking_tokens": 1300,
    "total_tokens": 85800
  }
}
```

`precision` is `exact`, `estimated`, or `unavailable`. The first release records exact or unavailable data only.

Cache and thinking fields are composition details, not always additive columns. Provider-reported `total_tokens` is authoritative when present. The reporter must not calculate totals by blindly adding input, cache, output, and thinking because cached tokens may be a subset of input and thinking tokens may be a subset of output.

## Terminal Interface

The first release provides a normal terminal table, not an interactive TUI:

```text
dev-orchestrator-usage current
dev-orchestrator-usage current --window 5h
dev-orchestrator-usage current --account personal
dev-orchestrator-usage all --window 5h
dev-orchestrator-usage accounts
```

The Codex installer always places the executable inside the installed Skill at `~/.codex/skills/dev-orchestrator/scripts/dev-orchestrator-usage`. The first explicit setup command may install a launcher into `${DEV_ORCHESTRATOR_BIN_DIR:-~/.local/bin}` after confirming that location is appropriate. Tracking and launcher installation are not silently enabled by installing the Skill.

Initial setup is therefore explicit:

```text
~/.codex/skills/dev-orchestrator/scripts/dev-orchestrator-usage setup --account personal
```

The default grouping is `account,role,model`. The current-project report shows one row per grouping and a project total. The all-projects report first shows project subtotals, followed by the all-project total.

Example:

```text
Project: dev-orchestrator
Window:  2026-09-24 04:10 → 09:10

ACCOUNT    ROLE          MODEL                    INPUT   CACHE  OUTPUT  THINK   TOTAL
personal   implement     gpt-5.6-luna             82.4K   61.2K    2.1K   1.3K   85.8K
personal   investigate   gemini-3.1-pro-high      18.2K      0      620    410   19.2K
work       quick_review  gemini-3.8-flash-high     6.8K      0      210     90    7.1K
────────────────────────────────────────────────────────────────────────────────────
PROJECT TOTAL                                                                    112.1K
```

Unavailable fields display `N/A`, never `0`. Reports include a short note that cache and thinking columns may be subsets of input and output.

## Five-Hour Semantics

`--window 5h` is a rolling interval ending at the report time, not a calendar-day shortcut. A completed event is included when its completion timestamp is inside `(now - 5 hours, now]`.

The first release assigns a call that crosses the boundary to its completion time and does not prorate one call across the boundary.

The report separates two concepts:

- **Actual tokens:** locally recorded events that can be summed across accounts, roles, models, and projects.
- **Subscription quota:** vendor-reported percentage and reset time, shown separately for every account.

Quota percentages are never summed. Two accounts at 40% and 30% remain two independent quota rows even when their actual tokens appear in one project total.

## Failure Handling

- Missing or malformed provider usage becomes `N/A` with a diagnostic status.
- Missing Codex session IDs disable Codex role attribution for that checkpoint but do not block the development task.
- Unknown account aliases are recorded as `unassigned` and surfaced in the report.
- Duplicate imports are ignored using stable event IDs.
- Partial ledger lines are skipped and reported without preventing valid rows from loading.
- Failed tokscale refreshes preserve direct ledger results and show quota data as stale or unavailable.
- Usage tracking failures never change repository files, routing decisions, build results, or task completion status.

## Privacy and Security

- Store token counts, timestamps, local aliases, model IDs, roles, and session identifiers only.
- Never store prompts, responses, reasoning text, tool output, credentials, tokens, or API keys.
- Redact credentials embedded in remote URLs before deriving project metadata.
- Keep ledger files user-readable only where the platform permits.
- Do not transmit usage data or invoke tokscale submission features.
- Account aliases are local labels and need not match provider emails.

## Integration with Dev Orchestrator

- Add usage settings to `config.yaml` without mixing them into model bindings.
- Enable tracking only after the user runs the local setup or account-alias command. Public installs do not silently start a ledger.
- Update the Codex adapter to start, checkpoint, and finish usage tracking when enabled.
- Route Antigravity calls through the JSON usage adapter when tracking is enabled.
- Preserve the existing rule that external agents are advisory/read-only.
- Include the usage scripts in the installed Codex Skill package, but not in the ChatGPT adapter, which cannot read local sessions.
- Add a compact usage summary to DEV HANDOFF only when tracking is enabled and data is available.

## README Changes

Document:

- what is tracked and what is not;
- setup and account alias commands;
- current-project, all-project, account, and five-hour reports;
- exact versus unavailable data;
- account totals versus independent quota percentages;
- optional tokscale integration;
- TokenBar and tokscale inspiration and attribution;
- privacy, storage location, and opt-out behavior.

## Testing Strategy

Use deterministic fixtures rather than live model calls for normal tests.

- Codex JSONL token snapshots and checkpoint subtraction.
- Antigravity JSON normalization.
- Provider total semantics where cache/thinking are subsets.
- Same project with multiple accounts, both separate and aggregated.
- Account switching during one task.
- Rolling five-hour boundary inclusion and exclusion.
- Calls that cross the window boundary.
- Worktree-to-repository rollup.
- Non-Git directory identity.
- Stable event deduplication.
- Concurrent append behavior and partial-line recovery.
- Missing usage displayed as `N/A`.
- Missing tokscale fallback.
- Quota percentages displayed per account and never summed.
- No prompt, response, credential, or remote-userinfo fields in ledger output.
- Installed Codex package includes the usage scripts; ChatGPT package does not.

An opt-in integration test may run one minimal `agy` request to verify the current JSON schema. It is not part of the default test suite because it consumes external quota.

## Acceptance Criteria

- A user can display exact usage for the current project in the terminal.
- The report groups by account alias, role, and model and includes a project total.
- The all-project report provides project subtotals and a global total.
- A rolling five-hour token report works independently of calendar dates.
- Same-project usage from different accounts can be shown separately or summed.
- Account quota percentages remain separate and include reset times when available.
- Codex role usage is derived from session checkpoints with no prompt-content reads.
- Antigravity usage is captured from provider JSON when available.
- Missing usage is labeled unavailable rather than zero.
- Tracking is opt-in, local-only, concurrency-safe, and does not affect task execution.
- All deterministic tests pass without requiring network access or model quota.

## Deferred Work

- Interactive TUI or macOS menu-bar interface.
- Cost and pricing calculations.
- Historical role inference.
- Cloud sync and team dashboards.
- Per-minute live charts.
- Automatic account identity inference when providers expose no stable local alias.
