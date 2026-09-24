from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, mock, skipUnless
import os
import json
import multiprocessing

from scripts.dev_orchestrator_usage.model import TokenUsage, UsageEvent
from scripts.dev_orchestrator_usage.project import resolve_project
from scripts.dev_orchestrator_usage.state import AccountRegistry, Ledger, locked_file, state_root


def make_event(event_id=None, completed_at=None):
    event = UsageEvent.new(
        started_at=datetime(2026, 9, 24, 1, 0, tzinfo=timezone.utc),
        completed_at=completed_at or datetime(2026, 9, 24, 1, 1, tzinfo=timezone.utc),
        project_key="project",
        project_label="demo",
        account_alias="personal",
        task_id="task",
        thread_id=None,
        session_id="session",
        conversation_id=None,
        role="implement",
        provider="test",
        model="model",
        source="test",
        precision="exact",
        usage=TokenUsage(1, 0, 0, 2, 0, 3),
    )
    if event_id is not None:
        return event.__class__(**{**event.__dict__, "event_id": event_id})
    return event


def append_in_process(root, event):
    Ledger(Path(root)).append(event)


class UsageStateTests(TestCase):
    def test_macos_state_root_and_override(self):
        home = Path("/Users/test")
        self.assertEqual(
            state_root({}, "darwin", home),
            home / "Library/Application Support/dev-orchestrator/usage",
        )
        self.assertEqual(
            state_root({"DEV_ORCHESTRATOR_STATE_DIR": "/tmp/custom"}, "darwin", home),
            Path("/tmp/custom"),
        )

    def test_xdg_state_root(self):
        home = Path("/home/test")
        self.assertEqual(
            state_root({"XDG_STATE_HOME": "/tmp/state"}, "linux", home),
            Path("/tmp/state/dev-orchestrator/usage"),
        )
        self.assertEqual(
            state_root({}, "linux", home),
            home / ".local/state/dev-orchestrator/usage",
        )

    def test_account_registry_uses_alias_not_email(self):
        with TemporaryDirectory() as tmp:
            registry = AccountRegistry(Path(tmp))
            registry.set_active("personal")
            self.assertEqual(registry.active(), "personal")
            self.assertNotIn("@", (Path(tmp) / "settings.json").read_text())

    def test_account_registry_is_disabled_until_explicit_enable(self):
        with TemporaryDirectory() as tmp:
            registry = AccountRegistry(Path(tmp))
            self.assertFalse(registry.is_enabled())
            registry.set_active("personal")
            self.assertEqual(registry.accounts(), ["personal"])
            registry.enable()
            self.assertTrue(registry.is_enabled())

    def test_duplicate_event_is_written_once(self):
        with TemporaryDirectory() as tmp:
            ledger = Ledger(Path(tmp))
            event = make_event(event_id="same")
            self.assertTrue(ledger.append(event))
            self.assertFalse(ledger.append(event))
            self.assertEqual(list(ledger.events()), [event])

    def test_malformed_and_partial_lines_are_skipped_with_diagnostics(self):
        with TemporaryDirectory() as tmp:
            ledger = Ledger(Path(tmp))
            event = make_event(event_id="valid")
            path = Path(tmp) / "events/2026-09.jsonl"
            path.parent.mkdir()
            path.write_text(
                json.dumps(event.to_dict(), separators=(",", ":"))
                + "\nnot-json\n{\"schema_version\": 1",
                encoding="utf-8",
            )
            self.assertEqual(list(ledger.events()), [event])
            self.assertEqual(len(ledger.diagnostics), 2)
            self.assertEqual(ledger.diagnostics[0]["line"], 2)

    def test_append_does_not_duplicate_existing_diagnostics(self):
        with TemporaryDirectory() as tmp:
            ledger = Ledger(Path(tmp))
            path = Path(tmp) / "events/2026-09.jsonl"
            path.parent.mkdir()
            path.write_text("not-json\n", encoding="utf-8")
            self.assertEqual(list(ledger.events()), [])
            self.assertEqual(len(ledger.diagnostics), 1)
            ledger.append(make_event(event_id="first"))
            ledger.append(make_event(event_id="second"))
            self.assertEqual(len(ledger.diagnostics), 1)

    @skipUnless(os.name != "nt", "POSIX flock regression")
    def test_lock_failure_closes_handle_without_unlocking(self):
        handle = mock.MagicMock()
        handle.fileno.return_value = 123
        handle.close.side_effect = OSError("close failed")
        with mock.patch.object(Path, "open", return_value=handle), mock.patch(
            "fcntl.flock", side_effect=OSError("lock failed")
        ) as flock:
            with self.assertRaisesRegex(OSError, "lock failed"):
                with locked_file(Path("/tmp/lock-regression")):
                    pass
        self.assertEqual(flock.call_count, 1)
        handle.close.assert_called_once_with()

    @skipUnless(os.name != "nt", "POSIX flock regression")
    def test_body_failure_is_preserved_when_unlock_fails(self):
        handle = mock.MagicMock()
        handle.fileno.return_value = 123
        handle.close.side_effect = OSError("close failed")
        with mock.patch.object(Path, "open", return_value=handle), mock.patch(
            "fcntl.flock", side_effect=[None, OSError("unlock failed")]
        ):
            with self.assertRaisesRegex(ValueError, "body failed"):
                with locked_file(Path("/tmp/lock-regression")):
                    raise ValueError("body failed")
        handle.close.assert_called_once_with()

    @skipUnless(os.name != "nt", "POSIX flock regression")
    def test_close_failure_is_propagated_after_successful_body_and_unlock(self):
        handle = mock.MagicMock()
        handle.fileno.return_value = 123
        handle.close.side_effect = OSError("close failed")
        with mock.patch.object(Path, "open", return_value=handle), mock.patch(
            "fcntl.flock", side_effect=[None, None]
        ):
            with self.assertRaisesRegex(OSError, "close failed"):
                with locked_file(Path("/tmp/lock-regression")):
                    pass
        handle.close.assert_called_once_with()

    @skipUnless(os.name != "nt", "POSIX flock regression")
    def test_unlock_failure_is_preserved_when_close_also_fails(self):
        handle = mock.MagicMock()
        handle.fileno.return_value = 123
        handle.close.side_effect = OSError("close failed")
        with mock.patch.object(Path, "open", return_value=handle), mock.patch(
            "fcntl.flock", side_effect=[None, OSError("unlock failed")]
        ):
            with self.assertRaisesRegex(OSError, "unlock failed"):
                with locked_file(Path("/tmp/lock-regression")):
                    pass
        handle.close.assert_called_once_with()

    @skipUnless(os.name != "nt", "POSIX flock regression")
    def test_successful_body_unlock_and_close_completes(self):
        handle = mock.MagicMock()
        handle.fileno.return_value = 123
        with mock.patch.object(Path, "open", return_value=handle), mock.patch(
            "fcntl.flock", side_effect=[None, None]
        ):
            with locked_file(Path("/tmp/lock-regression")):
                pass
        handle.close.assert_called_once_with()

    @mock.patch("scripts.dev_orchestrator_usage.project.run_git")
    def test_worktrees_share_git_common_directory_key(self, run_git):
        run_git.side_effect = [
            "/repo/worktree-a", "/repo/.git", "demo",
            "/repo/worktree-b", "/repo/.git", "demo",
        ]
        first = resolve_project(Path("/repo/worktree-a"))
        second = resolve_project(Path("/repo/worktree-b"))
        self.assertEqual(first.key, second.key)
        self.assertNotEqual(first.root, second.root)
        self.assertEqual(first.label, second.label)

    def test_two_process_append_keeps_complete_json_lines(self):
        with TemporaryDirectory() as tmp:
            events = [make_event(event_id=f"event-{i}") for i in range(2)]

            processes = [
                multiprocessing.Process(target=append_in_process, args=(tmp, event))
                for event in events
            ]
            for process in processes:
                process.start()
            for process in processes:
                process.join()
                self.assertEqual(process.exitcode, 0)
            lines = (Path(tmp) / "events/2026-09.jsonl").read_text().splitlines()
            self.assertEqual(len(lines), 2)
            self.assertEqual({json.loads(line)["event_id"] for line in lines}, {"event-0", "event-1"})
