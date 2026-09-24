from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, mock
import json
import os

from scripts.dev_orchestrator_usage.codex import (
    CodexSnapshot, TaskState, checkpoint_from_snapshot, read_snapshot, find_session_file,
    start_task, checkpoint_task, finish_task,
)
from scripts.dev_orchestrator_usage.model import TokenUsage
from scripts.dev_orchestrator_usage.project import ProjectIdentity
from scripts.dev_orchestrator_usage.state import AccountRegistry, Ledger

FIXTURE = Path(__file__).parent / "fixtures/usage/codex-session.jsonl"

def snapshot(total, input, cache, output, thinking, timestamp):
    return CodexSnapshot(datetime.fromisoformat(timestamp).replace(tzinfo=timezone.utc), "session-1", "thread-1", "openai", "gpt-5.6-luna", TokenUsage(input, cache, 0, output, thinking, total))

def project():
    return ProjectIdentity("project-key", "demo", Path("/repo"))

def task_state(s):
    return TaskState("task-1", "project-key", Path("/session.jsonl"), s, s.timestamp)

class CodexUsageTests(TestCase):
    def test_snapshot_reads_model_and_latest_cumulative_usage(self):
        result = read_snapshot(FIXTURE)
        self.assertEqual(result.model, "gpt-5.6-luna")
        self.assertEqual(result.usage.total_tokens, 195)
        self.assertEqual(result.thread_id, "thread-1")

    def test_checkpoint_records_only_delta_for_role(self):
        from scripts.dev_orchestrator_usage.codex import checkpoint_from_snapshot
        state = task_state(snapshot(120, 100, 80, 20, 10, "2026-09-24T00:01:00"))
        event, updated = checkpoint_from_snapshot(state, snapshot(195, 160, 120, 35, 15, "2026-09-24T00:02:00"), role="implement", account_alias="personal", project=project())
        self.assertEqual(event.usage.total_tokens, 75)
        self.assertEqual(event.role, "implement")
        self.assertEqual(updated.snapshot.usage.total_tokens, 195)

    def test_missing_or_decreasing_snapshot_produces_unavailable_event(self):
        state = task_state(snapshot(195, 160, 120, 35, 15, "2026-09-24T00:02:00"))
        event, _ = checkpoint_from_snapshot(state, snapshot(120, 100, 80, 20, 10, "2026-09-24T00:03:00"), role="review", account_alias="personal", project=project())
        self.assertEqual(event.precision, "unavailable")
        self.assertIsNone(event.usage.total_tokens)

    def test_missing_total_snapshot_is_unavailable(self):
        state = task_state(snapshot(120, 100, 80, 20, 10, "2026-09-24T00:01:00"))
        missing = CodexSnapshot(datetime(2026, 9, 24, 0, 3, tzinfo=timezone.utc), "session-1", "thread-1", "openai", "gpt-5.6-luna", TokenUsage.unavailable())
        event, _ = checkpoint_from_snapshot(state, missing, role="review", account_alias="personal", project=project())
        self.assertEqual(event.precision, "unavailable")

    def test_parser_does_not_retain_message_content(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "session.jsonl"
            path.write_text(FIXTURE.read_text() + '{"type":"response_item","payload":{"message":"secret"}}\n')
            result = read_snapshot(path)
            self.assertNotIn("secret", repr(result))

    def test_find_session_file_prefers_session_id_then_thread_first_match(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp); (root / "sessions/a").mkdir(parents=True); (root / "sessions/b").mkdir()
            def write(path, sid, tid):
                path.write_text(json.dumps({"type":"session_meta","payload":{"session_id":sid}})+"\n"+json.dumps({"type":"event_msg","payload":{"type":"thread_settings_applied","thread_id":tid}})+"\n")
            write(root / "sessions/a/one.jsonl", "other", "thread-x")
            write(root / "sessions/b/two.jsonl", "wanted", "thread-x")
            self.assertEqual(find_session_file(root, session_id="wanted", thread_id="thread-x"), root / "sessions/b/two.jsonl")
            self.assertEqual(find_session_file(root, session_id="absent", thread_id="thread-x"), root / "sessions/a/one.jsonl")

    def test_lifecycle_persists_and_rereads_account_and_finishes(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "state"; registry = AccountRegistry(Path(tmp) / "accounts"); registry.set_active("personal")
            ledger = Ledger(root); first = snapshot(120, 100, 80, 20, 10, "2026-09-24T00:01:00"); second = snapshot(195, 160, 120, 35, 15, "2026-09-24T00:02:00")
            with mock.patch.dict(os.environ, {"CODEX_THREAD_ID":"thread-task", "DEV_ORCHESTRATOR_STATE_DIR":str(root)}, clear=False):
                state = start_task(first, project(), Path("/session"), root=root)
            self.assertTrue((root / "active/thread-task.json").exists())
            event, state = checkpoint_task(state, second, "implement", project(), ledger, registry, root=root)
            self.assertEqual(event.account_alias, "personal")
            registry.set_active("work")
            third = snapshot(200, 165, 120, 40, 15, "2026-09-24T00:03:00")
            event, _ = finish_task(state, third, "implement", project(), ledger, registry, root=root)
            self.assertEqual(event.account_alias, "work")
            self.assertFalse((root / "active/thread-task.json").exists())
            self.assertTrue((root / "completed/thread-task.json").exists())
            self.assertEqual(len(list(ledger.events())), 2)

    def test_invalid_snapshot_does_not_advance_baseline(self):
        state = task_state(snapshot(120, 100, 80, 20, 10, "2026-09-24T00:01:00"))
        bad = snapshot(110, 90, 70, 19, 9, "2026-09-24T00:02:00")
        _, updated = checkpoint_from_snapshot(state, bad, "review", "personal", project())
        self.assertEqual(updated.snapshot.usage.total_tokens, 120)

    def test_file_metadata_overrides_caller_provider_and_model(self):
        result = read_snapshot(FIXTURE, model="caller-model", provider="caller-provider")
        self.assertEqual(result.model, "gpt-5.6-luna")
        self.assertEqual(result.provider, "openai")

    def test_find_session_file_uses_session_environment_fallback(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "sessions/session.jsonl"; path.parent.mkdir(parents=True)
            path.write_text(json.dumps({"type":"session_meta","payload":{"session_id":"env-session"}}) + "\n")
            with mock.patch.dict(os.environ, {"CODEX_SESSION_ID":"env-session"}, clear=False):
                self.assertEqual(find_session_file(Path(tmp)), path)

    def test_snapshot_iteration_io_failure_returns_partial_snapshot(self):
        class BrokenHandle:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def __iter__(self):
                yield '{"timestamp":"2026-09-24T00:00:00Z","type":"session_meta","payload":{"session_id":"partial","model_provider":"openai"}}'
                raise OSError("read failed")
        with mock.patch("scripts.dev_orchestrator_usage.codex.Path.open", return_value=BrokenHandle()):
            result = read_snapshot(Path("/unreadable"))
        self.assertEqual(result.session_id, "partial")
        self.assertEqual(result.provider, "openai")
        self.assertIsNone(result.usage.total_tokens)

    def test_default_root_is_used_for_every_lifecycle_step(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "state"; registry = AccountRegistry(Path(tmp) / "accounts"); registry.set_active("personal")
            ledger = Ledger(root)
            with mock.patch("scripts.dev_orchestrator_usage.codex.state_root", return_value=root), mock.patch.dict(os.environ, {"CODEX_THREAD_ID":"default-task"}, clear=False):
                state = start_task(snapshot(120, 100, 80, 20, 10, "2026-09-24T00:01:00"), project(), Path("/session"))
                self.assertTrue((root / "active/default-task.json").exists())
                state = checkpoint_task(state, snapshot(195, 160, 120, 35, 15, "2026-09-24T00:02:00"), "implement", project(), ledger, registry)[1]
                finish_task(state, snapshot(200, 165, 120, 40, 15, "2026-09-24T00:03:00"), "implement", project(), ledger, registry)
            self.assertTrue((root / "completed/default-task.json").exists())
