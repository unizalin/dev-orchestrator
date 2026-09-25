import json
from datetime import datetime, timezone
from pathlib import Path
from subprocess import CompletedProcess
from tempfile import TemporaryDirectory
from unittest import TestCase, mock

from scripts.dev_orchestrator_usage.external import (
    ExternalCommandError, normalize_agy_result, run_agy,
)
from scripts.dev_orchestrator_usage.model import EventContext

FIXTURE = Path(__file__).parent / "fixtures/usage/agy-success.json"


def context():
    return EventContext("project-key", "demo", "personal", "task-1", "thread-1", "session-1", "investigate", "google", "gemini-3.1-pro-high")


class ExternalUsageTests(TestCase):
    def test_normalizes_exact_agy_usage_without_storing_response(self):
        event = normalize_agy_result(json.loads(FIXTURE.read_text()), context())
        self.assertEqual(event.usage.total_tokens, 15702)
        self.assertEqual(event.usage.thinking_tokens, 10)
        self.assertEqual(event.precision, "exact")
        self.assertNotIn("response", event.to_dict())

    def test_normalization_maps_missing_usage_fields_to_none(self):
        event = normalize_agy_result({"status": "SUCCESS", "usage": {"total_tokens": 3}}, context())
        self.assertIsNone(event.usage.input_tokens)
        self.assertEqual(event.usage.total_tokens, 3)

    def test_missing_total_is_unavailable(self):
        event = normalize_agy_result({"status": "SUCCESS", "usage": {"input_tokens": 3}}, context())
        self.assertEqual(event.precision, "unavailable")
        self.assertIsNone(event.usage.total_tokens)

    def test_non_success_status_is_rejected(self):
        with self.assertRaises(ValueError):
            normalize_agy_result({"status": "FAILURE", "usage": {"total_tokens": 1}}, context())

    def test_missing_or_null_status_is_rejected(self):
        for payload in ({"usage": {"total_tokens": 1}}, {"status": None, "usage": {"total_tokens": 1}}):
            with self.assertRaises(ValueError):
                normalize_agy_result(payload, context())

    @mock.patch("scripts.dev_orchestrator_usage.external.subprocess.run")
    def test_run_agy_uses_sandbox_json_and_no_permission_bypass(self, run):
        run.return_value = CompletedProcess([], 0, FIXTURE.read_text(), "")
        with TemporaryDirectory() as tmp:
            prompt = Path(tmp) / "prompt.txt"
            prompt.write_text("sanitized prompt")
            response, event = run_agy(prompt, role="investigate", model="gemini-3.1-pro-high", effort="high", context=context())
        args = run.call_args.args[0]
        self.assertIn("--sandbox", args)
        self.assertIn("--output-format", args)
        self.assertIn("--mode", args)
        self.assertIn("--effort", args)
        self.assertEqual(args[args.index("--effort") + 1], "high")
        self.assertEqual(args[args.index("--mode") + 1], "plan")
        self.assertNotIn("--dangerously-skip-permissions", args)
        self.assertEqual(response, "review complete\n")
        self.assertEqual(event.usage.total_tokens, 15702)

    @mock.patch("scripts.dev_orchestrator_usage.external.subprocess.run")
    def test_run_agy_auto_omits_incompatible_effort_argument(self, run):
        run.return_value = CompletedProcess([], 0, FIXTURE.read_text(), "")
        with TemporaryDirectory() as tmp:
            prompt = Path(tmp) / "prompt.txt"
            prompt.write_text("independent review")
            run_agy(prompt, role="independent_review", model="claude-sonnet-4-6", effort="auto", context=context())

        args = run.call_args.args[0]
        self.assertNotIn("--effort", args)

    @mock.patch("scripts.dev_orchestrator_usage.external.subprocess.run")
    def test_run_agy_null_response_returns_empty_string(self, run):
        run.return_value = CompletedProcess([], 0, '{"status":"SUCCESS","response":null,"usage":{"total_tokens":1}}', "")
        with TemporaryDirectory() as tmp:
            prompt = Path(tmp) / "prompt.txt"
            prompt.write_text("sanitized prompt")
            response, _ = run_agy(prompt, role="investigate", model="m", effort="high", context=context())
        self.assertEqual(response, "")

    @mock.patch("scripts.dev_orchestrator_usage.external.subprocess.run")
    def test_run_agy_nonzero_raises_clear_error(self, run):
        run.return_value = CompletedProcess([], 2, "", "permission denied")
        with self.assertRaises(ExternalCommandError) as raised:
            run_agy(FIXTURE, role="investigate", model="m", effort="high", context=context())
        self.assertIn("permission denied", str(raised.exception))

    @mock.patch("scripts.dev_orchestrator_usage.external.subprocess.run")
    def test_run_agy_malformed_json_raises(self, run):
        run.return_value = CompletedProcess([], 0, "not json", "")
        with self.assertRaises(json.JSONDecodeError):
            run_agy(FIXTURE, role="investigate", model="m", effort="high", context=context())

    @mock.patch("scripts.dev_orchestrator_usage.external.subprocess.run")
    def test_run_agy_missing_usage_raises(self, run):
        run.return_value = CompletedProcess([], 0, '{"status":"SUCCESS"}', "")
        with self.assertRaises(ValueError):
            run_agy(FIXTURE, role="investigate", model="m", effort="high", context=context())
