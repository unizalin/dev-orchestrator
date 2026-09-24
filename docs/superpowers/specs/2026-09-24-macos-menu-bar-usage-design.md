# macOS Menu Bar Usage App Design

**Date:** 2026-09-24

**Status:** Approved

**Repository:** `dev-orchestrator`

## Purpose

Add a native macOS menu bar app that makes Dev Orchestrator's existing local token ledger understandable at a glance. The app must answer four questions without requiring terminal use:

1. How many tracked tokens were used in the latest five-hour rolling window?
2. How much did the current project use, and how much did all projects use?
3. Which account, role, provider, and model produced that usage?
4. Which details are actually available from each provider?

The app reports tracked usage, not an estimate of provider quota. It must never label tracked tokens as an official OpenAI, Google, or Anthropic allowance.

## Scope

Version 1 includes:

- A native SwiftUI macOS menu bar app with no Dock icon.
- A compact five-hour total in the menu bar when data exists, and an icon-only empty state otherwise.
- Current-project and all-project views.
- Cross-account totals plus an account filter.
- Grouped usage by project, account, role, provider, and model.
- Conditional token detail fields: unavailable fields are hidden rather than rendered as empty UI.
- Thirty-second local refresh, manual refresh, and a pause-auto-refresh control.
- Clear setup, empty-data, unavailable-CLI, malformed-data, and retry states.
- An optional “Launch at Login” setting, off by default.
- A stable JSON reporting interface in the existing `dev-orchestrator-usage` CLI.
- Build, test, packaging, and local installation instructions in the existing repository.

Version 1 does not:

- Switch the login identity of Codex, Antigravity, Gemini, or any provider.
- Intercept provider traffic or discover untracked historical usage.
- Poll a model or make a model request during refresh.
- Sum quota percentages across accounts.
- Run a local HTTP service or background daemon.
- Add charts whose meaning cannot be supported by exact ledger data.

## Product Behavior

### Menu bar

When at least one selected event has an exact `total_tokens` value in the latest five hours, the menu bar item shows a compact value such as `◉ 128K`. Formatting follows the existing CLI conventions. When no useful total exists, it shows the app icon without a misleading zero.

The menu bar total represents all tracked projects and all accounts for the rolling five-hour window. The popover makes the scope explicit.

### Popover

The popover opens to the current-project view. Its header contains:

- A segmented current-project / all-projects selector.
- The latest-five-hours tracked total for the selected project scope and account filter.
- The selected project's tracked cumulative total when current-project scope is active.
- Last refreshed time.
- A manual refresh button.

An account picker defaults to “All Accounts.” Selecting an account filters the display only. It does not change the active CLI attribution account or provider login. When “All Accounts” is selected, events from multiple accounts in the same project contribute to the same project total and remain available as separate detail groups.

The details section groups rows by the smallest useful distinction: project when all-projects is selected, then account, role, provider, and model. Fields such as input, cache, output, and thinking tokens appear only if at least one visible row contains that exact field. `total_tokens` remains the primary metric; unavailable totals display an explicit unavailable state at row level but do not become zero.

Sections with no useful information do not appear. This applies to quota, token-detail columns, account groups, errors, and help text.

### Settings and controls

The footer or settings menu provides:

- Auto Refresh: on by default, every 30 seconds.
- Refresh Now.
- Launch at Login: off by default.
- Open Setup Help when tracking is not configured.

Automatic refresh reads local files through the CLI only. It does not invoke Codex, Gemini, Claude, or another model and therefore consumes no model tokens.

## Architecture

### Chosen approach

The SwiftUI app executes the existing CLI's stable JSON report command and decodes its standard output. The CLI remains the single source of truth for ledger parsing, project identity, window filtering, grouping, conditional field availability, and totals.

This approach is preferred over duplicating ledger parsing in Swift because the terminal and GUI cannot silently diverge. It is preferred over a local service because a daemon adds installation, security, and lifecycle complexity without improving the first version.

### Repository layout

The app targets macOS 13 or newer and lives in the existing public repository under a focused macOS package directory:

```text
macos/DevOrchestratorBar/
├── Package.swift
├── Sources/
│   ├── DevOrchestratorBarApp/
│   ├── UsageClient/
│   └── UsageUI/
└── Tests/
```

Supporting build and installation scripts live under `scripts/`. Generated app bundles and Swift build output remain ignored.

### Component boundaries

`dev-orchestrator-usage` owns data semantics. It adds a machine-readable summary command that accepts the same window and account filters as the current text reports, plus explicit current/all project scope and an explicit project path. It emits versioned JSON and sends diagnostics to standard error.

`UsageClient` owns process execution and JSON decoding. It executes the reporting helper packaged inside the app bundle, supplies a bounded `PATH` containing standard Apple Silicon, Intel Homebrew, and system binary locations, and reports clearly when Python 3 is unavailable. A development-tree helper path can be injected only by tests and debug builds. It returns typed success or error states and never interprets ledger files directly.

`UsageUI` owns presentation models, compact number formatting where needed for display, conditional visibility, filtering controls, and empty/error states. It does not calculate authoritative totals.

`DevOrchestratorBarApp` owns the `MenuBarExtra` shell, refresh timer, user defaults, launch-at-login integration, and dependency wiring.

Each boundary has an independent test surface. The JSON schema is the contract between Python and Swift.

## JSON Contract

The CLI emits one JSON object with a schema version and no prompt, response, credential, or tool-output content. The contract includes:

- `schema_version`
- `generated_at`
- `window` and `window_started_at`
- `scope` (`current_project` or `all_projects`)
- current project identity when applicable
- selected account filter
- known account aliases and active attribution alias
- exact all-project five-hour total for the menu bar
- selected-scope five-hour total
- selected project's cumulative tracked total when applicable
- grouped rows containing project label/key, account alias, role, provider, model, precision, available token fields, and total
- a list of available token-detail field names
- non-fatal diagnostics, including skipped malformed records

JSON numbers remain integers. Missing provider fields are `null`, not zero. Totals are `null` when no contributing exact total exists. Timestamps use ISO 8601 with offsets.

The app accepts only supported schema versions. An unsupported version produces an update-required state rather than guessing.

## Data Flow

1. The app opens or the thirty-second timer fires.
2. `UsageClient` invokes the local CLI with JSON output, five-hour window, selected scope, and optional account filter.
3. The CLI reads the local registry and append-only ledger.
4. The CLI resolves the current project from the app's requested working directory when current-project scope is selected.
5. Existing aggregation primitives select and group events and compute exact totals.
6. The CLI emits versioned JSON.
7. The app decodes it into immutable state and replaces the visible snapshot atomically.
8. On failure, the last successful snapshot remains visible with a non-blocking stale-data indicator and a retry action.

The app never edits the ledger. Recording remains the responsibility of `task-start`, `checkpoint`, `finish`, and `run-agy`.

## Project and Account Semantics

Project identity continues to use the existing stable project key. Worktrees that share the same Git common directory are treated as one project. All-project scope groups by project key and label; labels are display text and are not unique identifiers.

Account aliases are local attribution labels. The GUI account picker is a report filter. Changing it cannot change the active alias stored by `accounts set`, because filtering and attribution are separate user actions.

Five-hour totals include only events whose completion timestamp falls within the open-start, closed-end rolling window already used by the CLI. Project cumulative total includes all valid recorded events for that project and selected account filter, regardless of age.

## Error and Empty States

- **Tracking disabled:** explain that setup is required and show the exact safe setup command with a copy action.
- **No events:** show “No tracked usage yet” and explain that future orchestrated tasks will appear automatically.
- **CLI missing:** show where the app looked and provide the installation command.
- **Malformed ledger rows:** show valid data, include the skipped-record count in a compact warning, and never fail the entire report.
- **Unsupported schema:** ask the user to update the App or Skill as appropriate.
- **Refresh failure after success:** keep the last successful data, mark it stale, show the error, and allow retry.
- **Unknown token details:** hide globally unavailable fields; render unavailable at row level only when the field is useful elsewhere in the same result.

Errors must remain local and must not trigger model calls, telemetry, or network requests.

## Privacy and Security

- The existing local-only, opt-in storage policy remains unchanged.
- The JSON endpoint contains aggregate metadata and token counts only.
- Prompts, responses, credentials, cookies, tool output, and source code are prohibited from the ledger and JSON contract.
- CLI paths and process arguments are constructed without a shell.
- The app invokes only a validated executable path and applies a bounded execution timeout.
- Refresh never invokes `agy`, Codex, or another provider CLI.
- No telemetry or automatic crash upload is added.

## Development Routing

Implementation follows Dev Orchestrator's own role policy:

- Luna is the primary implementation worker for the Swift package, SwiftUI app, CLI JSON endpoint, tests, development builds, and first-pass integration verification. Luna fixes failures found in that loop before handoff.
- Gemini is advisory and read-only for codebase/dependency analysis and independent quick review.
- Codex owns repository integration, independently repeats the relevant tests, installs the resulting app on this Mac, performs the final interactive verification, and decides whether the feature is complete.
- Gemini and Luna never edit the same files concurrently.
- Sol High is unavailable by default and may be used only after the configured escalation threshold is met or the user explicitly overrides it.

Every agent invocation used through the supported wrappers is written to the same usage ledger so this development can appear in the completed app. Usage that a provider does not expose exactly remains unavailable rather than estimated.

## Testing Strategy

### Python and contract tests

- JSON schema and stable field types.
- Current-project versus all-project filtering.
- Five-hour boundary behavior.
- Project cumulative totals.
- Multiple accounts in one project: combined total plus separate rows.
- Account filter behavior that does not mutate active attribution.
- Conditional available-field list.
- Null versus zero semantics.
- Empty ledger, disabled tracking, and malformed record diagnostics.
- Existing text reports and all existing routing tests remain unchanged.

### Swift tests

- Decode full, partial, empty, malformed, and unsupported-version fixtures.
- Map CLI failures to user-facing states.
- Hide sections and token fields with no useful data.
- Preserve the last successful snapshot after refresh failure.
- Format compact menu bar totals at numeric boundaries.
- Refresh scheduler starts, pauses, resumes, and does not overlap requests.
- Account and project scope selections produce the expected CLI arguments.

### Integration and manual acceptance

- Build the app using the repository script on the supported macOS/Xcode toolchain.
- Install the app locally and launch it as a menu bar-only application.
- Verify no Dock icon appears.
- Verify the menu bar total and popover data match the CLI JSON for the same inputs.
- Verify current-project/all-project switching and account filtering.
- Verify automatic refresh observes a newly recorded event without any model invocation.
- Verify this development's tracked Luna and Gemini usage is visible when exact provider data is available.
- Run the full existing validation suite and installed-Skill drift check.

## Packaging and Documentation

The repository provides one build script that creates a `.app` bundle and one installation path suitable for this Mac. The build copies a version-matched, read-only reporting helper and its Python modules into the app resources. The app supplies known Python search paths itself, so users do not need to configure a shell `PATH`; if Python 3 is absent, the app presents a precise local prerequisite message. Recording still comes from the separately installed Dev Orchestrator Skill and its shared local state.

`README.md` gains a visual-app section covering build, install, launch, tracking setup, privacy, what “five hours” means, multi-account behavior, and the fact that refresh does not consume tokens. `CHANGELOG.md` and `VERSION` are updated when the release is prepared.

## Acceptance Criteria

The feature is complete when:

1. A built and locally installed menu bar app opens without a Dock icon.
2. Its menu bar label shows the all-project, all-account tracked total for the latest five hours, or icon-only when no useful total exists.
3. The popover defaults to current project and can switch to all projects.
4. Multiple accounts in the same project aggregate correctly and can be filtered independently.
5. Token-detail fields and sections appear only when useful.
6. Thirty-second refresh reads local data only and consumes no model tokens.
7. The GUI and CLI agree exactly for the same report request.
8. Failure states do not destroy the last successful display or mutate ledger data.
9. Existing CLI, routing, packaging, and installed-Skill validation tests pass.
10. The app is installed and manually verified on this Mac, with the development's tracked model usage visible when available.
