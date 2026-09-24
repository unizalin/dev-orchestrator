# Token Usage Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add opt-in, local-only terminal reporting that attributes exact Codex and Antigravity token usage to project, account alias, orchestrator role, and model, including rolling five-hour and all-project totals.

**Architecture:** A Python standard-library package records append-only normalized usage events outside repositories. Codex usage comes from cumulative `token_count` snapshots joined to explicit role checkpoints; Antigravity usage comes from `agy --output-format json`. A terminal command aggregates ledger events and optionally reads tokscale quota JSON without making tokscale mandatory.

**Tech Stack:** Python 3.9+ standard library, `unittest`, JSON/JSONL, `fcntl` on macOS/Linux with a Windows locking fallback, existing Bash packaging scripts, existing YAML validation.

## Global Constraints

- No background service, web UI, menu-bar app, cloud sync, or remote telemetry.
- Store no prompts, responses, reasoning text, tool output, email addresses, OAuth tokens, API keys, or credentials.
- Tracking is opt-in and failures never block routing, implementation, build, test, or task completion.
- Exact and unavailable are the only precision states emitted in version 2.1; never invent estimates.
- Cached input may be a subset of input and thinking may be a subset of output; use provider-reported `total_tokens` rather than summing visible columns.
- Actual tokens may be summed across accounts; quota percentages must remain separate per account.
- Use a rolling `(now - 5 hours, now]` interval and attribute boundary-crossing calls by completion timestamp.
- Merge Git worktrees into their common repository identity.
- tokscale is optional, detected at runtime, and never installed automatically.
- Normal tests must not use network access or consume model quota.
- Keep the ChatGPT adapter free of local-session scripts and claims of local access.

---

## File Structure

- `scripts/dev-orchestrator-usage`: executable Python entrypoint with no business logic.
- `scripts/dev_orchestrator_usage/model.py`: immutable token and event data types plus normalization.
- `scripts/dev_orchestrator_usage/project.py`: Git/worktree and non-Git project identity.
- `scripts/dev_orchestrator_usage/state.py`: state paths, account settings, file locking, JSONL append/read, deduplication.
- `scripts/dev_orchestrator_usage/codex.py`: Codex session discovery, model/snapshot parsing, task start/checkpoint/finish.
- `scripts/dev_orchestrator_usage/external.py`: safe `agy` wrapper and JSON normalization.
- `scripts/dev_orchestrator_usage/aggregate.py`: windows, filters, grouping, totals, and terminal tables.
- `scripts/dev_orchestrator_usage/tokscale.py`: optional per-account quota adapter.
- `scripts/dev_orchestrator_usage/cli.py`: argparse commands and exit behavior.
- `tests/fixtures/usage/`: deterministic Codex, agy, and tokscale fixtures.
- `tests/test_usage_*.py`: focused standard-library test modules.
- `config.yaml`: opt-in usage policy, separate from role/model bindings.
- `adapters/codex/SKILL.md`: non-blocking task/checkpoint/finalize integration.
- `core/external-agents.md`: tracked agy invocation path.
- `core/handoff.md`: optional usage summary in DEV HANDOFF.
- `scripts/install_codex.sh`: install usage package only into the Codex adapter.
- `scripts/validate_portable.py`: structure and policy assertions for the new files.
- `README.md`, `CHANGELOG.md`, `VERSION`: setup, semantics, attribution, and 2.1 release metadata.

---

### Task 1: Normalized Usage and Event Types

**Files:**
- Create: `scripts/dev_orchestrator_usage/__init__.py`
- Create: `scripts/dev_orchestrator_usage/model.py`
- Create: `tests/test_usage_model.py`

**Interfaces:**
- Produces: `TokenUsage`, `EventContext`, `UsageEvent`, `normalize_optional_int()`, `subtract_usage()`.
- Consumes: Python standard library only.

- [ ] **Step 1: Write failing normalization and subtraction tests**

```python
from datetime import datetime, timezone
from unittest import TestCase

from scripts.dev_orchestrator_usage.model import TokenUsage, UsageEvent, subtract_usage


class UsageModelTests(TestCase):
    def test_total_is_provider_value_not_sum_of_composition_columns(self):
        usage = TokenUsage(
            input_tokens=100,
            cache_read_tokens=80,
            cache_write_tokens=0,
            output_tokens=20,
            thinking_tokens=10,
            total_tokens=120,
        )
        self.assertEqual(usage.total_tokens, 120)

    def test_subtract_usage_preserves_provider_total_semantics(self):
        before = TokenUsage(100, 80, 0, 20, 10, 120)
        after = TokenUsage(160, 120, 0, 35, 15, 195)
        self.assertEqual(subtract_usage(after, before), TokenUsage(60, 40, 0, 15, 5, 75))

    def test_negative_delta_returns_unavailable(self):
        before = TokenUsage(100, 0, 0, 20, 0, 120)
        after = TokenUsage(90, 0, 0, 10, 0, 100)
        self.assertIsNone(subtract_usage(after, before))

    def test_event_round_trip_omits_prompt_content(self):
        event = UsageEvent.new(
            project_key="p1",
            project_label="demo",
            account_alias="personal",
            task_id="t1",
            thread_id="th1",
            session_id="s1",
            conversation_id=None,
            role="implement",
            provider="openai",
            model="gpt-5.6-luna",
            source="codex-session",
            precision="exact",
            started_at=datetime(2026, 9, 24, 0, 0, tzinfo=timezone.utc),
            completed_at=datetime(2026, 9, 24, 0, 1, tzinfo=timezone.utc),
            usage=TokenUsage(100, 80, 0, 20, 10, 120),
        )
        restored = UsageEvent.from_dict(event.to_dict())
        self.assertEqual(restored, event)
        self.assertNotIn("prompt", event.to_dict())
        self.assertNotIn("response", event.to_dict())
```

- [ ] **Step 2: Run the focused test and verify the missing module failure**

Run: `python3 -m unittest tests.test_usage_model -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.dev_orchestrator_usage'`.

- [ ] **Step 3: Implement immutable normalized types**

```python
# scripts/dev_orchestrator_usage/model.py
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Literal, Optional

Precision = Literal["exact", "unavailable"]


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: Optional[int]
    cache_read_tokens: Optional[int]
    cache_write_tokens: Optional[int]
    output_tokens: Optional[int]
    thinking_tokens: Optional[int]
    total_tokens: Optional[int]

    @classmethod
    def unavailable(cls) -> "TokenUsage":
        return cls(None, None, None, None, None, None)


@dataclass(frozen=True)
class EventContext:
    project_key: str
    project_label: str
    account_alias: str
    task_id: str
    thread_id: Optional[str]
    session_id: str
    role: str
    provider: str
    model: str


def normalize_optional_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    parsed = int(value)
    if parsed < 0:
        raise ValueError("token counts cannot be negative")
    return parsed


def subtract_usage(after: TokenUsage, before: TokenUsage) -> Optional[TokenUsage]:
    values = []
    for newer, older in zip(asdict(after).values(), asdict(before).values()):
        if newer is None or older is None or newer < older:
            return None
        values.append(newer - older)
    return TokenUsage(*values)


@dataclass(frozen=True)
class UsageEvent:
    schema_version: int
    event_id: str
    recorded_at: datetime
    started_at: datetime
    completed_at: datetime
    project_key: str
    project_label: str
    account_alias: str
    task_id: str
    thread_id: Optional[str]
    session_id: str
    conversation_id: Optional[str]
    role: str
    provider: str
    model: str
    source: str
    precision: Precision
    usage: TokenUsage

    @classmethod
    def new(cls, **values: Any) -> "UsageEvent":
        identity = "|".join(str(values.get(k, "")) for k in (
            "project_key", "account_alias", "task_id", "session_id",
            "conversation_id", "role", "started_at", "completed_at",
        ))
        return cls(
            schema_version=1,
            event_id=sha256(identity.encode("utf-8")).hexdigest(),
            recorded_at=datetime.now(timezone.utc),
            **values,
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ("recorded_at", "started_at", "completed_at"):
            data[key] = data[key].isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UsageEvent":
        copy = dict(data)
        copy["usage"] = TokenUsage(**copy["usage"])
        for key in ("recorded_at", "started_at", "completed_at"):
            copy[key] = datetime.fromisoformat(copy[key])
        return cls(**copy)
```

- [ ] **Step 4: Run the tests**

Run: `python3 -m unittest tests.test_usage_model -v`  
Expected: 4 tests, all PASS.

- [ ] **Step 5: Commit the normalized model**

```bash
git add scripts/dev_orchestrator_usage/__init__.py scripts/dev_orchestrator_usage/model.py tests/test_usage_model.py
git commit -m "feat: add normalized usage event model"
```

---

### Task 2: Project Identity, Account Registry, and Append-Only Ledger

**Files:**
- Create: `scripts/dev_orchestrator_usage/project.py`
- Create: `scripts/dev_orchestrator_usage/state.py`
- Create: `tests/test_usage_state.py`

**Interfaces:**
- Consumes: `UsageEvent` from Task 1.
- Produces: `ProjectIdentity`, `resolve_project()`, `state_root()`, `AccountRegistry`, `Ledger.append()`, `Ledger.events()`.

- [ ] **Step 1: Write failing state, worktree, account, and deduplication tests**

```python
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, mock

from scripts.dev_orchestrator_usage.project import resolve_project
from scripts.dev_orchestrator_usage.state import AccountRegistry, Ledger, state_root


class UsageStateTests(TestCase):
    def test_macos_state_root_and_override(self):
        home = Path("/Users/test")
        self.assertEqual(
            state_root({}, "darwin", home),
            home / "Library/Application Support/dev-orchestrator/usage",
        )
        self.assertEqual(state_root({"DEV_ORCHESTRATOR_STATE_DIR": "/tmp/custom"}, "darwin", home), Path("/tmp/custom"))

    def test_account_registry_uses_alias_not_email(self):
        with TemporaryDirectory() as tmp:
            registry = AccountRegistry(Path(tmp))
            registry.set_active("personal")
            self.assertEqual(registry.active(), "personal")
            self.assertNotIn("@", (Path(tmp) / "settings.json").read_text())

    def test_duplicate_event_is_written_once(self):
        with TemporaryDirectory() as tmp:
            ledger = Ledger(Path(tmp))
            event = make_event(event_id="same")
            self.assertTrue(ledger.append(event))
            self.assertFalse(ledger.append(event))
            self.assertEqual(list(ledger.events()), [event])

    @mock.patch("scripts.dev_orchestrator_usage.project.run_git")
    def test_worktrees_share_git_common_directory_key(self, run_git):
        run_git.side_effect = ["/repo/worktree-a", "/repo/.git", "demo"]
        identity = resolve_project(Path("/repo/worktree-a"))
        self.assertEqual(identity.label, "demo")
        self.assertEqual(identity.root, Path("/repo/worktree-a"))
```

Define `make_event()` in the test using `UsageEvent.new()` from Task 1 with fixed UTC timestamps.

- [ ] **Step 2: Run tests and verify failures**

Run: `python3 -m unittest tests.test_usage_state -v`  
Expected: FAIL because `project.py` and `state.py` do not exist.

- [ ] **Step 3: Implement project identity**

```python
# scripts/dev_orchestrator_usage/project.py
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import subprocess


@dataclass(frozen=True)
class ProjectIdentity:
    key: str
    label: str
    root: Path


def run_git(cwd: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True, check=True)
    return result.stdout.strip()


def resolve_project(cwd: Path) -> ProjectIdentity:
    resolved = cwd.expanduser().resolve()
    try:
        root = Path(run_git(resolved, "rev-parse", "--show-toplevel")).resolve()
        common = Path(run_git(root, "rev-parse", "--path-format=absolute", "--git-common-dir")).resolve()
        label = run_git(root, "rev-parse", "--show-toplevel").rstrip("/").split("/")[-1]
        identity = f"git:{common}"
    except (subprocess.CalledProcessError, FileNotFoundError):
        root = resolved
        label = root.name or "root"
        identity = f"path:{root}"
    return ProjectIdentity(sha256(identity.encode()).hexdigest(), label, root)
```

- [ ] **Step 4: Implement locked append-only state**

Implement `state_root()` with the exact macOS/XDG rules from the design. Implement `AccountRegistry` using an atomically replaced `settings.json` containing only `enabled`, `active_account`, and `accounts`. Implement `Ledger.append()` so it:

```python
def append(self, event: UsageEvent) -> bool:
    month = event.completed_at.strftime("%Y-%m")
    path = self.root / "events" / f"{month}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with locked_file(self.root / ".ledger.lock"):
        if event.event_id in {item.event_id for item in self.events()}:
            return False
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.to_dict(), separators=(",", ":"), sort_keys=True) + "\n")
        return True
```

`locked_file()` uses `fcntl.flock(..., LOCK_EX)` on POSIX and `msvcrt.locking()` on Windows. `Ledger.events()` skips malformed or partial lines, records their file/line diagnostics, and yields every valid event exactly once.

- [ ] **Step 5: Run state tests**

Run: `python3 -m unittest tests.test_usage_state -v`  
Expected: all tests PASS, including a two-process append test that produces two intact JSON lines.

- [ ] **Step 6: Commit local state support**

```bash
git add scripts/dev_orchestrator_usage/project.py scripts/dev_orchestrator_usage/state.py tests/test_usage_state.py
git commit -m "feat: add local usage ledger and account aliases"
```

---

### Task 3: Codex Session Snapshots and Role Checkpoints

**Files:**
- Create: `scripts/dev_orchestrator_usage/codex.py`
- Create: `tests/fixtures/usage/codex-session.jsonl`
- Create: `tests/test_usage_codex.py`

**Interfaces:**
- Consumes: `TokenUsage`, `UsageEvent`, `Ledger`, `ProjectIdentity`, `AccountRegistry`.
- Produces: `CodexSnapshot(timestamp: datetime, session_id: str, thread_id: str | None, provider: str, model: str, usage: TokenUsage)`, `TaskState(task_id: str, project_key: str, session_file: Path, snapshot: CodexSnapshot, started_at: datetime)`, `find_session_file()`, `read_snapshot()`, `start_task()`, `checkpoint_task()`, `finish_task()`.

- [ ] **Step 1: Add a sanitized Codex fixture**

Create JSONL containing exactly:

```jsonl
{"timestamp":"2026-09-24T00:00:00Z","type":"session_meta","payload":{"id":"session-1","session_id":"session-1","cwd":"/repo","model_provider":"openai"}}
{"timestamp":"2026-09-24T00:00:01Z","type":"event_msg","payload":{"type":"thread_settings_applied","thread_id":"thread-1","thread_settings":{"model":"gpt-5.6-luna","model_provider_id":"openai"}}}
{"timestamp":"2026-09-24T00:01:00Z","type":"event_msg","payload":{"type":"token_count","info":{"total_token_usage":{"input_tokens":100,"cached_input_tokens":80,"cache_write_input_tokens":0,"output_tokens":20,"reasoning_output_tokens":10,"total_tokens":120},"last_token_usage":{"input_tokens":100,"cached_input_tokens":80,"cache_write_input_tokens":0,"output_tokens":20,"reasoning_output_tokens":10,"total_tokens":120}}}}
{"timestamp":"2026-09-24T00:02:00Z","type":"event_msg","payload":{"type":"token_count","info":{"total_token_usage":{"input_tokens":160,"cached_input_tokens":120,"cache_write_input_tokens":0,"output_tokens":35,"reasoning_output_tokens":15,"total_tokens":195},"last_token_usage":{"input_tokens":60,"cached_input_tokens":40,"cache_write_input_tokens":0,"output_tokens":15,"reasoning_output_tokens":5,"total_tokens":75}}}}
```

- [ ] **Step 2: Write failing parser and checkpoint tests**

```python
class CodexUsageTests(TestCase):
    def test_snapshot_reads_model_and_latest_cumulative_usage(self):
        snapshot = read_snapshot(FIXTURE)
        self.assertEqual(snapshot.model, "gpt-5.6-luna")
        self.assertEqual(snapshot.usage.total_tokens, 195)

    def test_checkpoint_records_only_delta_for_role(self):
        with TemporaryDirectory() as tmp:
            state = TaskState.initial(snapshot=first_snapshot(), role="implement")
            event, updated = checkpoint_from_snapshot(state, second_snapshot(), role="implement", account_alias="personal", project=project())
            self.assertEqual(event.usage.total_tokens, 75)
            self.assertEqual(event.role, "implement")
            self.assertEqual(updated.snapshot.total_tokens, 195)

    def test_missing_or_decreasing_snapshot_produces_unavailable_event(self):
        event, _ = checkpoint_from_snapshot(state_at_195(), snapshot_at_120(), role="review", account_alias="personal", project=project())
        self.assertEqual(event.precision, "unavailable")
        self.assertIsNone(event.usage.total_tokens)
```

The test module defines `snapshot(total, input, cache, output, thinking, timestamp)` and `task_state(snapshot)` helper constructors using the exact `CodexSnapshot` and `TaskState` signatures above; `first_snapshot()`, `second_snapshot()`, `state_at_195()`, and `snapshot_at_120()` in the examples are named fixtures built from those helpers.

- [ ] **Step 3: Run tests and verify failure**

Run: `python3 -m unittest tests.test_usage_codex -v`  
Expected: FAIL because `codex.py` is missing.

- [ ] **Step 4: Implement session discovery and safe parsing**

`find_session_file(codex_home, session_id, thread_id)` scans `sessions/**/*.jsonl`, reads only `session_meta` until a matching `id`/`session_id` is found, and falls back to a `thread_settings_applied.thread_id` match. `read_snapshot()` tracks the latest model and latest cumulative token object:

```python
mapping = {
    "input_tokens": "input_tokens",
    "cached_input_tokens": "cache_read_tokens",
    "cache_write_input_tokens": "cache_write_tokens",
    "output_tokens": "output_tokens",
    "reasoning_output_tokens": "thinking_tokens",
    "total_tokens": "total_tokens",
}
```

The parser ignores every other event type and never places message content in memory-owned output structures.

- [ ] **Step 5: Implement active task state and checkpoints**

Store active task state under `<state-root>/active/<task-id>.json`. Default `task_id` to `CODEX_THREAD_ID`, read `CODEX_SESSION_ID`, and use the active account alias. `start_task()` stores the initial cumulative snapshot. `checkpoint_task()` writes the delta event then atomically advances the snapshot. `finish_task()` performs one final checkpoint and moves the active state to `<state-root>/completed/`.

Read the account alias at every checkpoint instead of pinning it at task start. If the user switches from `personal` to `work` during one task, later deltas receive the new alias while earlier ledger events remain unchanged.

The model is taken from `thread_settings_applied.thread_settings.model`; a caller-provided model is only a fallback when no event contains one.

- [ ] **Step 6: Run Codex tests**

Run: `python3 -m unittest tests.test_usage_codex -v`  
Expected: all tests PASS and the privacy assertion confirms fixture message events would be ignored.

- [ ] **Step 7: Commit Codex attribution**

```bash
git add scripts/dev_orchestrator_usage/codex.py tests/fixtures/usage/codex-session.jsonl tests/test_usage_codex.py
git commit -m "feat: attribute Codex tokens to role checkpoints"
```

---

### Task 4: Tracked Antigravity Invocation

**Files:**
- Create: `scripts/dev_orchestrator_usage/external.py`
- Create: `tests/fixtures/usage/agy-success.json`
- Create: `tests/test_usage_external.py`

**Interfaces:**
- Consumes: `UsageEvent`, `Ledger`, project/account/task context.
- Produces: `normalize_agy_result()`, `run_agy()`.

- [ ] **Step 1: Add the sanitized agy fixture**

```json
{
  "conversation_id": "conversation-1",
  "status": "SUCCESS",
  "response": "review complete\n",
  "duration_seconds": 3.67,
  "num_turns": 1,
  "usage": {
    "input_tokens": 15691,
    "output_tokens": 11,
    "thinking_tokens": 10,
    "cache_read_tokens": 0,
    "total_tokens": 15702
  }
}
```

- [ ] **Step 2: Write failing normalization and subprocess tests**

```python
class ExternalUsageTests(TestCase):
    def test_normalizes_exact_agy_usage_without_storing_response(self):
        result = json.loads(FIXTURE.read_text())
        event = normalize_agy_result(result, context())
        self.assertEqual(event.usage.total_tokens, 15702)
        self.assertEqual(event.usage.thinking_tokens, 10)
        self.assertNotIn("response", event.to_dict())

    @mock.patch("scripts.dev_orchestrator_usage.external.subprocess.run")
    def test_run_agy_uses_sandbox_json_and_no_permission_bypass(self, run):
        run.return_value = CompletedProcess([], 0, FIXTURE.read_text(), "")
        response, event = run_agy(Path("prompt.md"), role="investigate", model="gemini-3.1-pro-high", effort="high", context=context())
        args = run.call_args.args[0]
        self.assertIn("--sandbox", args)
        self.assertIn("--output-format", args)
        self.assertNotIn("--dangerously-skip-permissions", args)
        self.assertEqual(response, "review complete\n")
```

- [ ] **Step 3: Run tests and verify failure**

Run: `python3 -m unittest tests.test_usage_external -v`  
Expected: FAIL because `external.py` does not exist.

- [ ] **Step 4: Implement agy normalization and wrapper**

```python
def run_agy(prompt_file: Path, *, role: str, model: str, effort: str, context: EventContext) -> tuple[str, UsageEvent]:
    command = [
        "agy", "--print", prompt_file.read_text(encoding="utf-8"),
        "--model", model, "--effort", effort,
        "--output-format", "json", "--sandbox", "--print-timeout", "0s",
    ]
    started = datetime.now(timezone.utc)
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise ExternalCommandError(result.returncode, result.stderr.strip())
    payload = json.loads(result.stdout)
    event = normalize_agy_result(
        payload,
        context=context,
        started_at=started,
        completed_at=datetime.now(timezone.utc),
    )
    return str(payload.get("response", "")), event
```

`normalize_agy_result()` maps missing fields to `None`, uses provider total as authoritative, sets `precision="exact"` only when `total_tokens` exists, and never includes `response` in an event.

- [ ] **Step 5: Run external tests**

Run: `python3 -m unittest tests.test_usage_external -v`  
Expected: all tests PASS, including malformed JSON, non-success status, and missing-usage cases.

- [ ] **Step 6: Commit Antigravity tracking**

```bash
git add scripts/dev_orchestrator_usage/external.py tests/fixtures/usage/agy-success.json tests/test_usage_external.py
git commit -m "feat: record exact Antigravity usage"
```

---

### Task 5: Rolling Aggregation and Terminal Tables

**Files:**
- Create: `scripts/dev_orchestrator_usage/aggregate.py`
- Create: `tests/test_usage_aggregate.py`

**Interfaces:**
- Consumes: iterable `UsageEvent` objects.
- Produces: `parse_window()`, `filter_events()`, `group_events()`, `render_project_report()`, `render_all_projects_report()`.

- [ ] **Step 1: Write failing aggregation tests**

```python
class UsageAggregationTests(TestCase):
    def test_five_hour_window_is_open_left_closed_right(self):
        now = datetime(2026, 9, 24, 10, 0, tzinfo=timezone.utc)
        events = [event_at(now - timedelta(hours=5)), event_at(now - timedelta(hours=4, minutes=59)), event_at(now)]
        selected = filter_events(events, now=now, window=parse_window("5h"))
        self.assertEqual([e.completed_at for e in selected], [now - timedelta(hours=4, minutes=59), now])

    def test_same_project_accounts_are_separate_then_summed(self):
        rows = group_events([
            exact_event(account="personal", role="implement", model="luna", total=100),
            exact_event(account="work", role="implement", model="luna", total=60),
        ])
        self.assertEqual([row.total_tokens for row in rows], [100, 60])
        self.assertEqual(sum(row.total_tokens for row in rows), 160)

    def test_unavailable_is_not_rendered_as_zero(self):
        report = render_project_report([unavailable_event()], project_label="demo", now=NOW)
        self.assertIn("N/A", report)

    def test_total_does_not_add_cache_and_thinking_twice(self):
        row = group_events([exact_event(input=100, cache=80, output=20, thinking=10, total=120)])[0]
        self.assertEqual(row.total_tokens, 120)
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python3 -m unittest tests.test_usage_aggregate -v`  
Expected: FAIL because `aggregate.py` is missing.

- [ ] **Step 3: Implement filters and normalized totals**

`parse_window()` accepts positive integer suffixes `m`, `h`, and `d`; version 2.1 documents `5h`. `filter_events()` applies project/account filters and `(now-window, now]`. `group_events()` keys rows by `(project_key, project_label, account_alias, role, provider, model)`.

For each token field, sum only known exact values. If every contributing event is unavailable for a field, return `None`. Never derive `total_tokens` by adding other columns.

- [ ] **Step 4: Implement stable terminal rendering**

Render ASCII-compatible headers and compact counts (`1.2K`, `3.4M`) with deterministic column order. Include:

```text
ACCOUNT    ROLE          MODEL                    INPUT   CACHE  OUTPUT  THINK   TOTAL
personal   implement     gpt-5.6-luna             82.4K   61.2K    2.1K   1.3K   85.8K
────────────────────────────────────────────────────────────────────────────────────
PROJECT TOTAL                                                                     85.8K

Note: CACHE may be part of INPUT; THINK may be part of OUTPUT. TOTAL is provider-reported.
```

All-project output renders project sections followed by `ALL PROJECTS TOTAL`.

- [ ] **Step 5: Run aggregation tests**

Run: `python3 -m unittest tests.test_usage_aggregate -v`  
Expected: all tests PASS, including project/account filtering, five-hour boundaries, cross-boundary calls, unknown fields, and stable ordering.

- [ ] **Step 6: Commit reporting**

```bash
git add scripts/dev_orchestrator_usage/aggregate.py tests/test_usage_aggregate.py
git commit -m "feat: add project and five-hour usage reports"
```

---

### Task 6: Optional tokscale Quota Adapter

**Files:**
- Create: `scripts/dev_orchestrator_usage/tokscale.py`
- Create: `tests/fixtures/usage/tokscale-usage.json`
- Create: `tests/test_usage_tokscale.py`

**Interfaces:**
- Produces: `QuotaWindow(used_percent: float | None, resets_at: datetime | None)`, `AccountQuota(provider: str, account_alias: str, session: QuotaWindow, weekly: QuotaWindow)`, `QuotaResult(available: bool, accounts: tuple[AccountQuota, ...], diagnostic: str | None)`, `parse_quotas()`, `load_quotas()`.
- Consumes: `tokscale usage --json` when the executable exists.

- [ ] **Step 1: Add a multi-account quota fixture**

```json
{
  "providers": [
    {"provider":"codex","account":{"name":"personal"},"session":{"usedPercent":40,"resetsAt":"2026-09-24T12:00:00Z"},"weekly":{"usedPercent":20,"resetsAt":"2026-09-28T00:00:00Z"}},
    {"provider":"codex","account":{"name":"work"},"session":{"usedPercent":30,"resetsAt":"2026-09-24T13:00:00Z"},"weekly":{"usedPercent":10,"resetsAt":"2026-09-29T00:00:00Z"}}
  ]
}
```

Treat this fixture as the supported normalized input shape. `parse_quotas()` also accepts the documented camelCase and snake_case field variants at provider boundaries, but always returns the fixed `QuotaResult` interface above.

- [ ] **Step 2: Write failing per-account quota tests**

```python
class TokscaleQuotaTests(TestCase):
    def test_quotas_remain_separate_per_account(self):
        quotas = parse_quotas(json.loads(FIXTURE.read_text()))
        self.assertEqual([(q.account_alias, q.session.used_percent) for q in quotas], [("personal", 40), ("work", 30)])
        self.assertFalse(hasattr(quotas[0], "combined_percent"))

    @mock.patch("shutil.which", return_value=None)
    def test_missing_tokscale_returns_unavailable_without_error(self, _):
        self.assertEqual(load_quotas(), QuotaResult.unavailable("tokscale not installed"))
```

- [ ] **Step 3: Run tests and verify failure**

Run: `python3 -m unittest tests.test_usage_tokscale -v`  
Expected: FAIL because `tokscale.py` is missing.

- [ ] **Step 4: Implement optional quota loading**

`load_quotas()` first checks `shutil.which("tokscale")`, then runs `tokscale usage --json`. Normalize provider, account alias, used percent, reset time, and stale/error status. Return one independent `AccountQuota` per account and never calculate a combined quota percent.

On missing executable, non-zero exit, timeout, or invalid JSON, return an unavailable result. Do not hide ledger token rows.

- [ ] **Step 5: Run quota tests**

Run: `python3 -m unittest tests.test_usage_tokscale -v`  
Expected: all tests PASS.

- [ ] **Step 6: Commit optional quota support**

```bash
git add scripts/dev_orchestrator_usage/tokscale.py tests/fixtures/usage/tokscale-usage.json tests/test_usage_tokscale.py
git commit -m "feat: add optional per-account quota display"
```

---

### Task 7: CLI, Explicit Setup, and Launcher

**Files:**
- Create: `scripts/dev_orchestrator_usage/cli.py`
- Create: `scripts/dev-orchestrator-usage`
- Create: `tests/test_usage_cli.py`

**Interfaces:**
- Consumes: all package APIs from Tasks 1-6.
- Produces: public `current`, `all`, `accounts`, and `setup`; internal `task-start`, `checkpoint`, `finish`, and `run-agy` commands.

- [ ] **Step 1: Write failing CLI tests**

```python
class UsageCliTests(TestCase):
    def test_setup_is_required_before_recording(self):
        result = run_cli("task-start", state_dir=empty_state())
        self.assertEqual(result.returncode, 3)
        self.assertIn("tracking is not enabled", result.stderr)

    def test_setup_stores_alias_and_enables_tracking(self):
        result = run_cli("setup", "--account", "personal", "--no-launcher", state_dir=empty_state())
        self.assertEqual(result.returncode, 0)
        self.assertIn("personal", result.stdout)

    def test_current_report_defaults_to_account_role_model(self):
        result = run_cli("current", "--window", "5h", state_dir=state_with_events())
        self.assertEqual(result.returncode, 0)
        self.assertIn("ACCOUNT", result.stdout)
        self.assertIn("ROLE", result.stdout)
        self.assertIn("MODEL", result.stdout)

    def test_run_agy_prints_response_but_not_raw_json(self):
        result = run_cli_with_mocked_agy("run-agy", "--role", "investigate", "--model", "gemini-3.1-pro-high", "--prompt-file", str(PROMPT))
        self.assertEqual(result.stdout, "review complete\n")
        self.assertNotIn("input_tokens", result.stdout)
```

The test module implements `run_cli(*args, state_dir)` by patching `DEV_ORCHESTRATOR_STATE_DIR`, calling `cli.main(list(args))`, and capturing stdout/stderr with `contextlib.redirect_stdout` and `redirect_stderr`. It returns a small `CliResult(returncode, stdout, stderr)` dataclass. `run_cli_with_mocked_agy()` uses the same helper while patching `external.subprocess.run` with the sanitized fixture.

- [ ] **Step 2: Run tests and verify failure**

Run: `python3 -m unittest tests.test_usage_cli -v`  
Expected: FAIL because the CLI files do not exist.

- [ ] **Step 3: Implement argparse commands and exit codes**

Use these exit codes:

```python
EXIT_OK = 0
EXIT_USAGE_ERROR = 2
EXIT_TRACKING_DISABLED = 3
EXIT_DATA_UNAVAILABLE = 4
EXIT_EXTERNAL_FAILURE = 5
```

`setup --account ALIAS` validates the alias with `^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$`, enables tracking, and optionally installs a launcher. `accounts` lists aliases and marks the active one. Add `accounts set ALIAS` to switch without deleting prior data.

`current` resolves the current project and defaults to all accounts and all roles/models. `all` renders project subtotals and the global total. Both accept `--window 5h`, `--account ALIAS`, `--no-quota`, and `--state-dir PATH` for tests.

Internal lifecycle commands are quiet on success so Skill use does not clutter development output. They print concise diagnostics to stderr and preserve the non-blocking contract.

- [ ] **Step 4: Implement the executable entrypoint**

```python
#!/usr/bin/env python3
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dev_orchestrator_usage.cli import main

raise SystemExit(main())
```

Make it executable with `chmod +x scripts/dev-orchestrator-usage`.

- [ ] **Step 5: Implement optional launcher creation**

Interactive setup asks before creating `${DEV_ORCHESTRATOR_BIN_DIR:-~/.local/bin}/dev-orchestrator-usage`. `--install-launcher` provides explicit non-interactive approval; `--no-launcher` skips it. The launcher is a symlink to the installed Skill executable and setup refuses to overwrite an unrelated existing path.

- [ ] **Step 6: Run CLI tests and help smoke tests**

Run: `python3 -m unittest tests.test_usage_cli -v`  
Expected: all tests PASS.

Run: `scripts/dev-orchestrator-usage --help`  
Expected: exit 0 and commands `setup`, `accounts`, `current`, `all`, `task-start`, `checkpoint`, `finish`, and `run-agy` are listed.

- [ ] **Step 7: Commit the CLI**

```bash
git add scripts/dev_orchestrator_usage/cli.py scripts/dev-orchestrator-usage tests/test_usage_cli.py
git commit -m "feat: add token usage terminal command"
```

---

### Task 8: Skill Integration, Packaging, Documentation, and Release Validation

**Files:**
- Modify: `config.yaml`
- Modify: `adapters/codex/SKILL.md`
- Modify: `core/external-agents.md`
- Modify: `core/handoff.md`
- Modify: `scripts/install_codex.sh`
- Modify: `scripts/validate_portable.py`
- Modify: `scripts/validate.sh`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `VERSION`
- Create: `tests/test_usage_packaging.py`
- Create: `tests/fixtures/usage/smoke-prompt.txt`

**Interfaces:**
- Consumes: installed CLI from Task 7.
- Produces: portable version 2.1.0 with Codex-only usage scripts and unchanged ChatGPT capability boundaries.

- [ ] **Step 1: Write failing packaging and policy tests**

```python
class UsagePackagingTests(TestCase):
    def test_codex_install_contains_usage_cli_and_package(self):
        with TemporaryDirectory() as tmp:
            env = {**os.environ, "CODEX_HOME": tmp}
            subprocess.run([str(ROOT / "scripts/install_codex.sh")], env=env, check=True)
            package = Path(tmp) / "skills/dev-orchestrator"
            self.assertTrue((package / "scripts/dev-orchestrator-usage").is_file())
            self.assertTrue((package / "scripts/dev_orchestrator_usage/cli.py").is_file())

    def test_chatgpt_export_excludes_local_usage_scripts(self):
        subprocess.run([str(ROOT / "scripts/export_chatgpt.sh")], check=True)
        with ZipFile(ROOT / "dist/chatgpt/dev-orchestrator-chatgpt-skill.zip") as archive:
            self.assertFalse(any("/scripts/" in name for name in archive.namelist()))

    def test_tracking_policy_is_opt_in(self):
        config = yaml.safe_load((ROOT / "config.yaml").read_text())
        self.assertEqual(config["usage_tracking"]["mode"], "opt_in")

    def test_chatgpt_adapter_still_disclaims_local_session_access(self):
        text = (ROOT / "adapters/chatgpt/SKILL.md").read_text().lower()
        self.assertIn("do not claim", text)
        self.assertIn("local", text)
```

- [ ] **Step 2: Run packaging tests and verify failure**

Run: `python3 -m unittest tests.test_usage_packaging -v`  
Expected: FAIL because installers and config do not include usage support.

- [ ] **Step 3: Add opt-in configuration**

Add a top-level block separate from `roles`:

```yaml
usage_tracking:
  mode: "opt_in"
  state_dir_env: "DEV_ORCHESTRATOR_STATE_DIR"
  default_window: "5h"
  default_group_by: ["account", "role", "model"]
  tokscale: "auto"
  include_in_handoff: true
```

Update `portable_version` and `VERSION` to `2.1.0`.

- [ ] **Step 4: Integrate non-blocking checkpoints into the Codex Skill**

Add concise policy to `adapters/codex/SKILL.md`:

```markdown
## Usage tracking

When the installed usage command reports tracking enabled, start one task record, checkpoint at role boundaries, and finish before DEV HANDOFF. Tracking failures are diagnostics only and never block repository work. For Antigravity roles, use the tracked invocation described in `references/external-agents.md`. Never store prompts, responses, credentials, or tool output in usage state.
```

In `core/external-agents.md`, provide the tracked `run-agy` form and retain the existing direct invocation as the fallback when tracking is disabled or unavailable. In `core/handoff.md`, add an optional `## Token Usage` section that includes the current-project table only when exact data exists.

- [ ] **Step 5: Package usage scripts only for Codex**

Update `scripts/install_codex.sh` to create `$package/scripts`, copy the executable and package directory, and preserve executable mode. Do not change `scripts/export_chatgpt.sh`; its allowlist continues to exclude scripts.

Update `scripts/validate_portable.py` to require the new source files, assert `usage_tracking.mode == "opt_in"`, and assert that ChatGPT instructions still do not claim local access. Update `scripts/validate.sh` to run `python3 -m unittest discover -s "$source_root/tests" -p 'test_usage_*.py' -v` before installed-adapter drift validation.

- [ ] **Step 6: Document setup, commands, semantics, and attribution**

Add a README section with:

```text
~/.codex/skills/dev-orchestrator/scripts/dev-orchestrator-usage setup --account personal
dev-orchestrator-usage current --window 5h
dev-orchestrator-usage all --window 5h
dev-orchestrator-usage accounts
dev-orchestrator-usage accounts set work
```

Document exact versus `N/A`, separate account quotas, local state paths, opt-out, no prompt storage, TokenBar/tokscale inspiration, optional tokscale installation, and the fact that percentages are not additive.

Add a `2.1.0` changelog entry describing terminal usage tracking without rewriting the historical `2.0.0` entry.

Create `tests/fixtures/usage/smoke-prompt.txt` with the exact text `Reply exactly OK`.

- [ ] **Step 7: Run all deterministic tests**

Run: `python3 -m unittest discover -s tests -p 'test_usage_*.py' -v`  
Expected: all usage tests PASS with no network access.

Run: `scripts/validate.sh`  
Expected: all portable, adapter, routing, and installed-drift tests PASS after installation.

- [ ] **Step 8: Install and verify the Codex package**

Run: `scripts/install_codex.sh`  
Expected: versioned backup, installed Skill includes `LICENSE` and usage scripts, post-install validation passes.

Run: `~/.codex/skills/dev-orchestrator/scripts/dev-orchestrator-usage --help`  
Expected: exit 0 and no state directory is created merely by showing help.

- [ ] **Step 9: Verify ChatGPT export remains local-capability safe**

Run: `scripts/export_chatgpt.sh`  
Expected: ZIP validation passes and the archive contains `LICENSE` but no `scripts/` directory.

Run: `unzip -l dist/chatgpt/dev-orchestrator-chatgpt-skill.zip`  
Expected: no usage executable or Python package appears.

- [ ] **Step 10: Run the opt-in live smoke test**

Use a temporary state directory and one minimal Flash request:

```bash
DEV_ORCHESTRATOR_STATE_DIR=/private/tmp/dev-orchestrator-usage-smoke \
  scripts/dev-orchestrator-usage setup --account smoke --no-launcher

DEV_ORCHESTRATOR_STATE_DIR=/private/tmp/dev-orchestrator-usage-smoke \
  scripts/dev-orchestrator-usage run-agy \
  --role quick_review \
  --model gemini-3.8-flash-low \
  --effort low \
  --prompt-file tests/fixtures/usage/smoke-prompt.txt

DEV_ORCHESTRATOR_STATE_DIR=/private/tmp/dev-orchestrator-usage-smoke \
  scripts/dev-orchestrator-usage current --window 5h
```

Expected: response is `OK`, one exact `quick_review` row is shown, and no prompt or response appears in the ledger. This step requires explicit network/model-quota authorization and is skipped when unavailable.

- [ ] **Step 11: Commit the integrated 2.1 release candidate**

```bash
git add VERSION CHANGELOG.md README.md config.yaml adapters/codex/SKILL.md core/external-agents.md core/handoff.md scripts/install_codex.sh scripts/validate.sh scripts/validate_portable.py tests/test_usage_packaging.py
git commit -m "feat: integrate token usage tracking"
```

---

## Final Verification Checklist

- [ ] `python3 -m unittest discover -s tests -p 'test_usage_*.py' -v` reports zero failures.
- [ ] `scripts/validate.sh --live-agy` reports all routing/adapter tests and runtime model discovery passing.
- [ ] `git diff --check` reports no whitespace errors.
- [ ] Secret/privacy scan finds no prompt, response, credential, email, or OAuth fields in generated ledger fixtures.
- [ ] Installed Codex adapter matches the portable source and includes the usage CLI.
- [ ] ChatGPT ZIP validates and excludes local usage scripts.
- [ ] `dev-orchestrator-usage current --window 5h` keeps account rows separate and calculates the correct project total.
- [ ] Quota output never sums per-account percentages.
- [ ] Repository status contains only intentional commits and ignored generated exports.
- [ ] No GitHub push, tag rewrite, visibility change, or Release replacement occurs without separate explicit authorization.
