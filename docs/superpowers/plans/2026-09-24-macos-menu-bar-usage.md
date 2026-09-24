# macOS Menu Bar Usage App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build, install, and verify a native macOS menu bar app that displays Dev Orchestrator's locally tracked token usage by project, account, role, provider, and model.

**Architecture:** Python remains the authoritative aggregation layer and exposes a versioned JSON `summary` command. A SwiftUI `MenuBarExtra` application invokes a version-matched reporting helper embedded in the app bundle, decodes the JSON into typed state, and renders only useful fields. Refresh is local-only; recording remains in the installed Dev Orchestrator Skill.

**Tech Stack:** Python 3 standard library and `unittest`; Swift 5.9 package on macOS 13+; SwiftUI, Foundation, ServiceManagement, XCTest; shell packaging scripts; ad-hoc local code signing.

## Global Constraints

- Target macOS 13 or newer; the development Mac runs macOS 26.7.1 with Xcode 26.6 and Swift 6.3.3.
- Keep all data local and opt-in. Never store or emit prompts, responses, credentials, cookies, tool output, or source code.
- Refresh reads local state only and must never invoke Codex, `agy`, Gemini, Claude, or another model.
- Missing token fields are `null`, never zero. Hide fields that are unavailable in every visible row.
- “Current project” means the project of the most recently completed valid ledger event unless a development/test project path override is supplied.
- Account selection filters reports only and must not mutate the active attribution alias.
- Menu bar total is the all-project, all-account five-hour total, independent of the popover filters.
- Luna performs implementation, development builds, tests, and first-pass fixes. Gemini is advisory/read-only. Codex integrates, repeats tests, installs, and performs final acceptance.
- Sol High remains disabled unless two evidence-backed attempts fail or the user explicitly overrides the escalation gate.
- Follow TDD: red test, minimal implementation, green test, then commit.

## File Map

### Python reporting contract

- Create `scripts/dev_orchestrator_usage/summary.py`: authoritative JSON-ready summary construction.
- Modify `scripts/dev_orchestrator_usage/cli.py`: add the `summary` command and JSON serialization.
- Create `tests/test_usage_summary.py`: aggregation and schema behavior.
- Modify `tests/test_usage_cli.py`: command-level setup, filtering, diagnostics, and privacy behavior.
- Modify `scripts/validate_portable.py`: require the new summary module and the new release version.

### Native macOS package

- Create `macos/DevOrchestratorBar/Package.swift`: package products and targets.
- Create `macos/DevOrchestratorBar/Sources/UsageClient/UsageSnapshot.swift`: JSON contract types.
- Create `macos/DevOrchestratorBar/Sources/UsageClient/UsageRequest.swift`: CLI argument generation.
- Create `macos/DevOrchestratorBar/Sources/UsageClient/ProcessUsageClient.swift`: bounded, non-shell process execution and decoding.
- Create `macos/DevOrchestratorBar/Sources/UsageUI/CompactTokens.swift`: compact token formatting.
- Create `macos/DevOrchestratorBar/Sources/UsageUI/UsageViewModel.swift`: refresh and last-good-state behavior.
- Create `macos/DevOrchestratorBar/Sources/UsageUI/UsagePopoverView.swift`: conditional SwiftUI presentation.
- Create `macos/DevOrchestratorBar/Sources/DevOrchestratorBarApp/DevOrchestratorBarApp.swift`: menu bar shell and refresh loop.
- Create `macos/DevOrchestratorBar/Sources/DevOrchestratorBarApp/LaunchAtLogin.swift`: `SMAppService` adapter.
- Create `macos/DevOrchestratorBar/Tests/UsageClientTests/*`: decode, request, and process errors.
- Create `macos/DevOrchestratorBar/Tests/UsageUITests/*`: formatting and view-model state.
- Create `macos/DevOrchestratorBar/Resources/Info.plist`: bundle metadata and `LSUIElement`.

### Packaging and documentation

- Create `scripts/build_macos_app.sh`: release/debug app-bundle assembly, helper embedding, and ad-hoc signing.
- Create `scripts/install_macos_app.sh`: recoverable user-local installation.
- Modify `scripts/validate.sh`: run Swift tests on macOS unless explicitly skipped.
- Modify `.gitignore`: ignore Swift build output and generated app bundles.
- Modify `README.md`, `CHANGELOG.md`, `VERSION`, and `config.yaml`: document and version 2.2.0.

---

### Task 1: Authoritative Python Summary Model

**Files:**
- Create: `scripts/dev_orchestrator_usage/summary.py`
- Create: `tests/test_usage_summary.py`

**Interfaces:**
- Consumes: `UsageEvent`, `ProjectIdentity`, `parse_window()`, `filter_events()`, and `group_events()`.
- Produces: `build_summary(events, *, window_name, scope, accounts, active_account, selected_account=None, now=None, project_override=None, malformed_event_count=0) -> dict[str, object]`.

- [ ] **Step 1: Write failing summary tests**

Create deterministic events at `2026-09-24T10:00:00Z` and add tests with these exact assertions:

```python
summary = build_summary(
    events,
    window_name="5h",
    scope="current_project",
    accounts=["personal", "work"],
    active_account="work",
    now=NOW,
)
self.assertEqual(summary["schema_version"], 1)
self.assertEqual(summary["current_project"], {"key": "new", "label": "Newest"})
self.assertEqual(summary["all_projects_window_total"], 160)
self.assertEqual(summary["selected_scope_window_total"], 60)
self.assertEqual(summary["current_project_cumulative_total"], 90)
self.assertEqual(summary["accounts"], ["personal", "work"])
self.assertEqual(summary["active_account"], "work")
```

Also assert:

```python
self.assertEqual(build_summary(events, window_name="5h", scope="all_projects", accounts=[], active_account=None, selected_account="personal", now=NOW)["selected_scope_window_total"], 100)
self.assertEqual(summary["available_detail_fields"], ["input_tokens", "output_tokens"])
self.assertIsNone(build_summary([], window_name="5h", scope="current_project", accounts=[], active_account=None, now=NOW)["current_project"])
self.assertEqual(build_summary(events, window_name="5h", scope="current_project", accounts=[], active_account=None, now=NOW, malformed_event_count=2)["diagnostics"], {"malformed_event_count": 2})
```

Verify the left five-hour boundary is excluded, the right boundary is included, the latest project is chosen from all valid events even when older than five hours, account filtering does not change `all_projects_window_total`, duplicate account aliases are removed, and every missing detail remains `None`.

- [ ] **Step 2: Run the new test and confirm red**

Run:

```bash
python3 -m unittest tests.test_usage_summary -v
```

Expected: import failure for `scripts.dev_orchestrator_usage.summary`.

- [ ] **Step 3: Implement the summary builder**

Create `summary.py` with these public constants and helpers:

```python
SCHEMA_VERSION = 1
VALID_SCOPES = ("current_project", "all_projects")
DETAIL_FIELDS = ("input_tokens", "cache_tokens", "output_tokens", "thinking_tokens")

def _sum_available(values: Iterable[int | None]) -> int | None:
    known = [value for value in values if value is not None]
    return sum(known) if known else None

def _project_dict(project: ProjectIdentity | None) -> dict[str, str] | None:
    return None if project is None else {"key": project.key, "label": project.label}

def _latest_project(events: Sequence[UsageEvent]) -> ProjectIdentity | None:
    if not events:
        return None
    event = max(events, key=lambda item: (item.completed_at, item.recorded_at, item.event_id))
    return ProjectIdentity(event.project_key, event.project_label, Path(""))
```

`build_summary()` must validate `scope`, parse `window_name` exactly once, materialize events once, choose `project_override` before `_latest_project`, calculate the global five-hour total before applying account/project filters, and return this exact shape:

```python
{
    "schema_version": SCHEMA_VERSION,
    "generated_at": now.isoformat(),
    "window": window_name,
    "window_started_at": (now - window).isoformat(),
    "scope": scope,
    "current_project": _project_dict(current_project),
    "selected_account": selected_account,
    "accounts": sorted(set(accounts) | {e.account_alias for e in all_events}),
    "active_account": active_account,
    "all_projects_window_total": _sum_available(r.total_tokens for r in global_rows),
    "selected_scope_window_total": _sum_available(r.total_tokens for r in selected_rows),
    "current_project_cumulative_total": current_project_cumulative_total,
    "available_detail_fields": [field for field in DETAIL_FIELDS if any(getattr(r, field) is not None for r in selected_rows)],
    "rows": [
        {
            "project_key": row.project_key,
            "project_label": row.project_label,
            "account_alias": row.account_alias,
            "role": row.role,
            "provider": row.provider,
            "model": row.model,
            "precision": "exact" if row.total_tokens is not None else "unavailable",
            "usage": {
                "input_tokens": row.input_tokens,
                "cache_tokens": row.cache_tokens,
                "output_tokens": row.output_tokens,
                "thinking_tokens": row.thinking_tokens,
                "total_tokens": row.total_tokens,
            },
        }
        for row in selected_rows
    ],
    "diagnostics": {"malformed_event_count": malformed_event_count},
}
```

For cumulative totals, filter all materialized events by the current project key and optional account without applying the five-hour window, group them, and call `_sum_available`.

- [ ] **Step 4: Run the focused and aggregation tests**

Run:

```bash
python3 -m unittest tests.test_usage_summary tests.test_usage_aggregate -v
```

Expected: all tests pass, and existing text aggregation behavior remains unchanged.

- [ ] **Step 5: Commit Task 1**

```bash
git add scripts/dev_orchestrator_usage/summary.py tests/test_usage_summary.py
git commit -m "feat: add machine-readable usage summary model"
```

### Task 2: Stable CLI JSON Endpoint

**Files:**
- Modify: `scripts/dev_orchestrator_usage/cli.py`
- Modify: `tests/test_usage_cli.py`
- Modify: `scripts/validate_portable.py`

**Interfaces:**
- Consumes: `build_summary()` from Task 1, `Ledger`, `AccountRegistry`, and `resolve_project()`.
- Produces: `dev-orchestrator-usage summary --scope {current_project,all_projects} --window 5h [--account ALIAS] [--project-path PATH]`.

- [ ] **Step 1: Add failing CLI contract tests**

Add `summary` to the help-command assertion and create tests that parse stdout with `json.loads()`:

```python
result = run_cli("summary", "--scope", "all_projects", "--window", "5h", state_dir=root)
self.assertEqual(result.returncode, 0)
payload = json.loads(result.stdout)
self.assertEqual(payload["schema_version"], 1)
self.assertEqual(payload["scope"], "all_projects")
self.assertEqual(payload["all_projects_window_total"], 12)
self.assertNotIn("prompt", result.stdout.lower())
self.assertNotIn("response", result.stdout.lower())
self.assertEqual(result.stderr, "")
```

Add cases for disabled tracking (`EXIT_TRACKING_DISABLED`), invalid window/scope (`EXIT_USAGE_ERROR`), account filtering without active-account mutation, `--project-path` override, and one malformed JSONL row producing `diagnostics.malformed_event_count == 1` while keeping valid rows.

- [ ] **Step 2: Verify CLI tests fail**

Run:

```bash
python3 -m unittest tests.test_usage_cli -v
```

Expected: failures because `summary` is not a recognized command.

- [ ] **Step 3: Implement `_summary()` and parser wiring**

Import `build_summary`. Add:

```python
def _summary(args) -> int:
    if not _require_enabled(args):
        return EXIT_TRACKING_DISABLED
    try:
        parse_window(args.window)
        root = _root(args)
        registry = AccountRegistry(root)
        ledger = Ledger(root)
        events = list(ledger.events())
        project_override = resolve_project(args.project_path) if args.project_path else None
        payload = build_summary(
            events,
            window_name=args.window,
            scope=args.scope,
            accounts=registry.accounts(),
            active_account=registry.active(),
            selected_account=args.account,
            project_override=project_override,
            malformed_event_count=len(ledger.diagnostics),
        )
        print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
        return EXIT_OK
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE_ERROR
    except OSError as exc:
        print(f"summary: {exc}", file=sys.stderr)
        return EXIT_DATA_UNAVAILABLE
```

Register the parser with exact choices and a resolved `Path`:

```python
p = sub.add_parser("summary")
p.add_argument("--scope", choices=("current_project", "all_projects"), default="current_project")
p.add_argument("--window", default="5h")
p.add_argument("--account")
p.add_argument("--project-path", type=Path)
_add_common(p)
```

Dispatch `summary` before the text-report branches. Do not call `load_quotas()` from `_summary()`.

- [ ] **Step 4: Require the summary module in portable validation**

Append this exact path to `required_files`:

```python
"scripts/dev_orchestrator_usage/summary.py",
```

- [ ] **Step 5: Run Python and privacy checks**

Run:

```bash
python3 -m unittest discover -s tests -p 'test_usage_*.py' -v
python3 scripts/validate_portable.py .
```

Expected: all usage tests and 12 deterministic routing checks pass; serialized JSON contains no prohibited content keys.

- [ ] **Step 6: Commit Task 2**

```bash
git add scripts/dev_orchestrator_usage/cli.py scripts/validate_portable.py tests/test_usage_cli.py
git commit -m "feat: expose versioned usage summary JSON"
```

### Task 3: Swift Package, Contract Models, and Process Client

**Files:**
- Create: `macos/DevOrchestratorBar/Package.swift`
- Create: `macos/DevOrchestratorBar/Sources/UsageClient/UsageSnapshot.swift`
- Create: `macos/DevOrchestratorBar/Sources/UsageClient/UsageRequest.swift`
- Create: `macos/DevOrchestratorBar/Sources/UsageClient/ProcessUsageClient.swift`
- Create: `macos/DevOrchestratorBar/Tests/UsageClientTests/UsageSnapshotTests.swift`
- Create: `macos/DevOrchestratorBar/Tests/UsageClientTests/UsageRequestTests.swift`
- Create: `macos/DevOrchestratorBar/Tests/UsageClientTests/ProcessUsageClientTests.swift`

**Interfaces:**
- Produces: `UsageSnapshot`, `UsageRequest`, `ProjectScope`, `UsageLoading`, and `ProcessUsageClient` for Task 4.
- `UsageLoading.load(_:) async throws -> UsageSnapshot` is the only UI-facing data interface.

- [ ] **Step 1: Create the package manifest and failing decode/request tests**

Use `// swift-tools-version: 5.9`, platform `.macOS(.v13)`, libraries `UsageClient` and `UsageUI`, executable `DevOrchestratorBar`, and corresponding XCTest targets.

The decode fixture must include two rows, a null detail field, two accounts, and diagnostics. Assert:

```swift
let snapshot = try JSONDecoder.usageDecoder.decode(UsageSnapshot.self, from: fixture)
XCTAssertEqual(snapshot.schemaVersion, 1)
XCTAssertEqual(snapshot.allProjectsWindowTotal, 160)
XCTAssertNil(snapshot.rows[1].usage.inputTokens)
XCTAssertEqual(snapshot.diagnostics.malformedEventCount, 1)
```

The request test must assert exact arguments:

```swift
XCTAssertEqual(
    UsageRequest(scope: .allProjects, account: "work").arguments,
    ["summary", "--scope", "all_projects", "--window", "5h", "--account", "work"]
)
```

- [ ] **Step 2: Confirm tests fail before model files exist**

Run:

```bash
swift test --package-path macos/DevOrchestratorBar
```

Expected: compile failures for missing `UsageSnapshot` and `UsageRequest`.

- [ ] **Step 3: Implement typed JSON models and request arguments**

Define public `Decodable`, `Equatable`, and `Sendable` structs matching every JSON field. Use:

```swift
public extension JSONDecoder {
    static var usageDecoder: JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .iso8601
        return decoder
    }
}

public enum ProjectScope: String, CaseIterable, Sendable {
    case currentProject = "current_project"
    case allProjects = "all_projects"
}

public struct UsageRequest: Equatable, Sendable {
    public var scope: ProjectScope = .currentProject
    public var window = "5h"
    public var account: String?
    public var projectPath: String?

    public var arguments: [String] {
        var value = ["summary", "--scope", scope.rawValue, "--window", window]
        if let account, !account.isEmpty { value += ["--account", account] }
        if let projectPath, !projectPath.isEmpty { value += ["--project-path", projectPath] }
        return value
    }
}
```

Reject unsupported `schema_version` after decoding with `UsageClientError.unsupportedSchema(Int)`.

- [ ] **Step 4: Write failing process-client tests**

Inject a `CommandRunning` fake and assert success decode, nonzero exit with stderr, malformed JSON, timeout mapping, and exact environment behavior. The production environment must prepend `/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin` to any existing `PATH`.

- [ ] **Step 5: Implement bounded non-shell execution**

Define:

```swift
public struct CommandResult: Sendable {
    public let status: Int32
    public let stdout: Data
    public let stderr: Data
}

public protocol CommandRunning: Sendable {
    func run(executable: URL, arguments: [String], environment: [String: String], timeout: TimeInterval) async throws -> CommandResult
}

public protocol UsageLoading: Sendable {
    func load(_ request: UsageRequest) async throws -> UsageSnapshot
}
```

`ProcessUsageClient` must pass arguments directly to `Process` without `/bin/sh`, use a five-second timeout, decode only stdout, include bounded stderr in errors, and throw `unsupportedSchema` unless the decoded version is exactly `1`.

- [ ] **Step 6: Run Swift client tests**

Run:

```bash
swift test --package-path macos/DevOrchestratorBar --filter UsageClientTests
```

Expected: all UsageClient tests pass without invoking the real ledger or network.

- [ ] **Step 7: Commit Task 3**

```bash
git add macos/DevOrchestratorBar
git commit -m "feat: add native usage client package"
```

### Task 4: View Model, Formatting, and Refresh State

**Files:**
- Create: `macos/DevOrchestratorBar/Sources/UsageUI/CompactTokens.swift`
- Create: `macos/DevOrchestratorBar/Sources/UsageUI/UsageViewModel.swift`
- Create: `macos/DevOrchestratorBar/Tests/UsageUITests/CompactTokensTests.swift`
- Create: `macos/DevOrchestratorBar/Tests/UsageUITests/UsageViewModelTests.swift`

**Interfaces:**
- Consumes: `UsageLoading`, `UsageRequest`, and `UsageSnapshot`.
- Produces: `compactTokens(_:)`, `UsageViewModel`, `LoadState`, `refresh()`, and filter bindings used by Task 5.

- [ ] **Step 1: Write formatting and state tests first**

Assert exact formatting boundaries:

```swift
XCTAssertEqual(compactTokens(nil), nil)
XCTAssertEqual(compactTokens(999), "999")
XCTAssertEqual(compactTokens(1_000), "1K")
XCTAssertEqual(compactTokens(1_250), "1.3K")
XCTAssertEqual(compactTokens(999_950), "1M")
```

Use a queued fake loader and assert:

```swift
await model.refresh()
XCTAssertEqual(model.snapshot, first)
XCTAssertEqual(model.state, .loaded)
loader.enqueue(error: SampleError.failed)
await model.refresh()
XCTAssertEqual(model.snapshot, first)
XCTAssertTrue(model.isStale)
```

Also verify default scope is `.currentProject`, default account is nil (“All Accounts”), scope/account changes create the correct next request, overlapping refreshes are ignored, and `menuBarTitle` always uses `snapshot.allProjectsWindowTotal` rather than filtered totals.

- [ ] **Step 2: Confirm UsageUI tests fail**

Run:

```bash
swift test --package-path macos/DevOrchestratorBar --filter UsageUITests
```

Expected: compile failures for missing formatter and view model.

- [ ] **Step 3: Implement the formatter and main-actor model**

Define:

```swift
public enum LoadState: Equatable { case idle, loading, loaded, failed(String) }

@MainActor
public final class UsageViewModel: ObservableObject {
    @Published public var scope: ProjectScope = .currentProject
    @Published public var selectedAccount: String?
    @Published public var autoRefresh = true
    @Published public private(set) var snapshot: UsageSnapshot?
    @Published public private(set) var state: LoadState = .idle
    @Published public private(set) var isStale = false
    @Published public private(set) var refreshedAt: Date?

    private let loader: any UsageLoading
    private var refreshInFlight = false

    public func refresh() async {
        guard !refreshInFlight else { return }
        refreshInFlight = true
        defer { refreshInFlight = false }
        if snapshot == nil { state = .loading }
        do {
            snapshot = try await loader.load(UsageRequest(scope: scope, account: selectedAccount))
            state = .loaded
            isStale = false
            refreshedAt = Date()
        } catch {
            state = .failed(error.localizedDescription)
            isStale = snapshot != nil
        }
    }
}
```

Add computed `menuBarTitle`, selected and global totals, accounts, visible detail fields, grouped rows, and empty-state predicates. `compactTokens` must match the Python formatter's rounding and never produce `1000K`.

- [ ] **Step 4: Run all Swift unit tests**

Run:

```bash
swift test --package-path macos/DevOrchestratorBar
```

Expected: all UsageClient and UsageUI tests pass.

- [ ] **Step 5: Commit Task 4**

```bash
git add macos/DevOrchestratorBar/Sources/UsageUI macos/DevOrchestratorBar/Tests/UsageUITests
git commit -m "feat: add usage presentation state"
```

### Task 5: Native Menu Bar Interface and Login Setting

**Files:**
- Create: `macos/DevOrchestratorBar/Sources/UsageUI/UsagePopoverView.swift`
- Create: `macos/DevOrchestratorBar/Sources/DevOrchestratorBarApp/DevOrchestratorBarApp.swift`
- Create: `macos/DevOrchestratorBar/Sources/DevOrchestratorBarApp/LaunchAtLogin.swift`
- Create: `macos/DevOrchestratorBar/Tests/UsageUITests/ConditionalPresentationTests.swift`

**Interfaces:**
- Consumes: `UsageViewModel` and `ProcessUsageClient`.
- Produces: the runnable `DevOrchestratorBar` executable and menu bar popover.

- [ ] **Step 1: Add failing conditional-presentation tests**

Keep rendering rules in pure presentation helpers and assert:

```swift
XCTAssertFalse(Presentation(snapshot: noDetails).showsInput)
XCTAssertTrue(Presentation(snapshot: mixedDetails).showsInput)
XCTAssertFalse(Presentation(snapshot: clean).showsDiagnostics)
XCTAssertTrue(Presentation(snapshot: malformed).showsDiagnostics)
XCTAssertTrue(Presentation(snapshot: empty).showsEmptyState)
```

- [ ] **Step 2: Implement the popover with conditional sections**

Build a fixed-width, vertically scrollable view containing:

```swift
Picker("範圍", selection: $model.scope) {
    Text("目前專案").tag(ProjectScope.currentProject)
    Text("全部專案").tag(ProjectScope.allProjects)
}
.pickerStyle(.segmented)

Picker("帳號", selection: $model.selectedAccount) {
    Text("全部帳號").tag(String?.none)
    ForEach(model.accounts, id: \.self) { Text($0).tag(Optional($0)) }
}

Toggle("自動更新（30 秒）", isOn: $model.autoRefresh)
Button("立即更新") { Task { await model.refresh() } }
```

Show “近 5 小時已追蹤用量,” “專案累計,” and last refresh time. Group details by project/account/role/provider/model. Render token detail labels only through the pure `Presentation` visibility booleans. Use `ContentUnavailableView` for setup, empty, CLI/Python missing, unsupported schema, and load failures. A stale warning must coexist with the last good rows.

- [ ] **Step 3: Implement launch-at-login behavior**

Wrap `SMAppService.mainApp` behind:

```swift
@MainActor
final class LaunchAtLogin: ObservableObject {
    @Published private(set) var isEnabled = SMAppService.mainApp.status == .enabled
    @Published private(set) var errorMessage: String?

    func setEnabled(_ enabled: Bool) {
        do {
            if enabled { try SMAppService.mainApp.register() }
            else { try SMAppService.mainApp.unregister() }
            isEnabled = SMAppService.mainApp.status == .enabled
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
```

The toggle defaults off because the service is not registered during installation.

- [ ] **Step 4: Implement the app shell and refresh loop**

Use:

```swift
@main
struct DevOrchestratorBarApp: App {
    @StateObject private var model = UsageViewModel(loader: AppDependencies.usageClient())

    var body: some Scene {
        MenuBarExtra {
            UsagePopoverView(model: model)
                .task { await model.refresh() }
                .task(id: model.autoRefresh) {
                    while model.autoRefresh && !Task.isCancelled {
                        try? await Task.sleep(for: .seconds(30))
                        guard !Task.isCancelled else { return }
                        await model.refresh()
                    }
                }
        } label: {
            Label(model.menuBarTitle ?? "", systemImage: "chart.bar.xaxis")
        }
        .menuBarExtraStyle(.window)
    }
}
```

`AppDependencies.usageClient()` must locate `Contents/Resources/UsageCLI/dev-orchestrator-usage` from `Bundle.main` and must not fall back to an arbitrary executable on `PATH` in release builds.

- [ ] **Step 5: Run tests and a development build**

Run:

```bash
swift test --package-path macos/DevOrchestratorBar
swift build --package-path macos/DevOrchestratorBar -c debug
```

Expected: tests pass and the executable links with SwiftUI and ServiceManagement.

- [ ] **Step 6: Commit Task 5**

```bash
git add macos/DevOrchestratorBar
git commit -m "feat: add macOS menu bar usage interface"
```

### Task 6: Build, Bundle, Sign, and Install

**Files:**
- Create: `macos/DevOrchestratorBar/Resources/Info.plist`
- Create: `scripts/build_macos_app.sh`
- Create: `scripts/install_macos_app.sh`
- Modify: `.gitignore`
- Create: `tests/test_macos_packaging.py`

**Interfaces:**
- Produces: `dist/DevOrchestratorBar.app` containing the Swift executable and version-matched Python reporting helper.
- Installs recoverably to `${DEV_ORCHESTRATOR_APP_DIR:-$HOME/Applications}/DevOrchestratorBar.app`.

- [ ] **Step 1: Write failing packaging tests**

Parse the scripts and plist without running an install. Assert `LSUIElement == true`, `LSMinimumSystemVersion == "13.0"`, bundle identifier `com.unizalin.DevOrchestratorBar`, expected executable name, helper/module copy paths, ad-hoc signing, a destination safety equality check, and backup-before-replacement behavior.

- [ ] **Step 2: Create the bundle plist**

Use these keys:

```xml
<key>CFBundleExecutable</key><string>DevOrchestratorBar</string>
<key>CFBundleIdentifier</key><string>com.unizalin.DevOrchestratorBar</string>
<key>CFBundleName</key><string>Dev Orchestrator</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleShortVersionString</key><string>2.2.0</string>
<key>CFBundleVersion</key><string>220</string>
<key>LSMinimumSystemVersion</key><string>13.0</string>
<key>LSUIElement</key><true/>
```

- [ ] **Step 3: Implement the build script**

The script must use `set -euo pipefail`, resolve `source_root`, accept only `debug` or `release`, run Swift build with the matching configuration, assemble under a temporary directory, copy the binary, plist, `scripts/dev-orchestrator-usage`, and the complete `scripts/dev_orchestrator_usage` module tree, set executable permissions, replace only `dist/DevOrchestratorBar.app`, then run:

```bash
codesign --force --deep --sign - "$app_path"
codesign --verify --deep --strict "$app_path"
```

Validate target paths before any replacement. Generated `.build/`, `macos/DevOrchestratorBar/.build/`, and `dist/` stay ignored.

- [ ] **Step 4: Implement recoverable user-local installation**

The installer runs the release build, creates `$HOME/Applications` or the explicit override, verifies the destination basename is exactly `DevOrchestratorBar.app`, moves an existing app to `~/Library/Application Support/dev-orchestrator/backups/apps/<timestamp>-DevOrchestratorBar.app`, and copies with `ditto`. It must not launch the app; Codex performs launch and interactive verification separately.

- [ ] **Step 5: Run packaging tests and build the signed app**

Run:

```bash
python3 -m unittest tests.test_macos_packaging -v
scripts/build_macos_app.sh debug
codesign --verify --deep --strict dist/DevOrchestratorBar.app
```

Expected: packaging tests pass and signature verification exits zero.

- [ ] **Step 6: Commit Task 6**

```bash
git add .gitignore macos/DevOrchestratorBar/Resources scripts/build_macos_app.sh scripts/install_macos_app.sh tests/test_macos_packaging.py
git commit -m "build: package macOS menu bar app"
```

### Task 7: Release Integration and User Documentation

**Files:**
- Modify: `scripts/validate.sh`
- Modify: `scripts/validate_portable.py`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `VERSION`
- Modify: `config.yaml`
- Modify: `adapters/codex/SKILL.md`

**Interfaces:**
- Produces: portable release version `2.2.0`, documented GUI workflow, and full validation entry point.

- [ ] **Step 1: Add validation expectations first**

Update portable tests to require the macOS package manifest, plist, build/install scripts, and summary module. Change the exact expected version to `2.2.0`. Add a `--skip-macos` option to `validate.sh`; on Darwin, run:

```bash
swift test --package-path "$source_root/macos/DevOrchestratorBar"
```

Non-Darwin systems print a skip note instead of failing.

- [ ] **Step 2: Update version sources atomically**

Set:

```text
VERSION: 2.2.0
config.yaml portable_version: 2.2.0
```

Ensure `Info.plist` already matches. Add a validator assertion covering all three version sources.

- [ ] **Step 3: Document installation and semantics**

Add README sections for:

- `scripts/install_macos_app.sh`
- where the menu bar item appears and why no Dock icon exists
- current project as the latest tracked project
- current/all project scope and all-account/account filtering
- five-hour tracked usage versus official provider quota
- thirty-second local refresh consuming zero model tokens
- setup and empty states
- local-only privacy and inability to backfill untracked history
- development build and test commands

Add a `2.2.0 — 2026-09-24` changelog entry. Update the Codex Skill instructions to mention that successful tracked tasks become visible in the optional menu bar app without making the GUI mandatory.

- [ ] **Step 4: Run complete source validation**

Run:

```bash
scripts/validate.sh --skip-installed
```

Expected: portable validation, every Python usage test, Swift tests, both official Skill validations, `agy` executable discovery, and 12 routing checks pass.

- [ ] **Step 5: Commit Task 7**

```bash
git add VERSION config.yaml CHANGELOG.md README.md adapters/codex/SKILL.md scripts/validate.sh scripts/validate_portable.py
git commit -m "docs: release menu bar usage app"
```

### Task 8: Independent Review, Installation, and Acceptance

**Files:**
- Modify only files required by concrete review findings.
- Install outside the repository: `${HOME}/Applications/DevOrchestratorBar.app`.

**Interfaces:**
- Consumes: all prior tasks.
- Produces: a locally installed, running, independently verified app and release-ready branch.

- [ ] **Step 1: Run Gemini read-only quick review**

Before invocation, run `agy models` and choose an actually available Flash review model. Give Gemini the design, plan, branch diff, and explicit read-only instructions. Ask it to report only correctness, privacy, process execution, aggregation, refresh, and packaging findings with file/line evidence. Record exact usage through `dev-orchestrator-usage run-agy --role quick_review`.

- [ ] **Step 2: Have Luna fix confirmed findings and rerun its test loop**

For each confirmed finding, write or strengthen a failing regression test, apply the smallest fix, and rerun the focused suite plus:

```bash
python3 -m unittest discover -s tests -p 'test_usage_*.py' -v
swift test --package-path macos/DevOrchestratorBar
scripts/build_macos_app.sh release
```

Commit only verified corrections with `fix:` messages.

- [ ] **Step 3: Codex independently reruns final automated verification**

Run:

```bash
git diff --check main...HEAD
scripts/validate.sh --skip-installed
scripts/build_macos_app.sh release
codesign --verify --deep --strict dist/DevOrchestratorBar.app
```

Expected: all commands exit zero. Inspect the built bundle to confirm `LSUIElement`, executable, reporting helper, Python modules, and version values.

- [ ] **Step 4: Install the Skill and application recoverably**

Run:

```bash
scripts/install_codex.sh
scripts/install_macos_app.sh
```

Expected: the installed Skill passes its drift check; the app installs at `~/Applications/DevOrchestratorBar.app`; any prior app is retained in the documented backup directory.

- [ ] **Step 5: Launch and perform interactive acceptance**

Launch the installed app, verify the process is running, verify no Dock icon, open the menu bar popover, and confirm:

1. Menu bar total matches `dev-orchestrator-usage summary --scope all_projects --window 5h`.
2. The popover defaults to the most recently tracked project.
3. Current/all scope changes rows and selected total correctly.
4. All Accounts combines accounts; selecting one account filters without changing `accounts` active attribution.
5. Fields with no useful values disappear.
6. Manual refresh works.
7. A local ledger update becomes visible within 30 seconds with no provider process started.
8. Luna and Gemini rows appear when their exact tracked events are available.

Capture process and CLI evidence without storing screenshots that contain private project data in Git.

- [ ] **Step 6: Verify clean repository and create final integration commit if needed**

Run:

```bash
git status --short
git log --oneline --decorate -12
```

Expected: no uncommitted source changes; generated `dist/` and Swift build output remain ignored. If a final metadata-only correction was required, commit it with a precise message and repeat Step 3.

## Execution Routing

Use fresh Luna subagents task-by-task rather than one long-lived editor. Each implementation task receives only the approved design, this plan section, existing conventions, and the previous task's committed interface. Codex reviews each commit before beginning the next task.

Gemini runs twice at most: once before Swift implementation for advisory dependency/impact analysis if it provides distinct value, and once after Task 7 for the required read-only quick review. Do not ask both Luna and Gemini to independently re-solve the same problem. Do not use Claude unless a high-risk unresolved review question remains. Do not use Sol unless the two-failure threshold is reached.
