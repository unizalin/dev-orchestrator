import json
import subprocess
from pathlib import Path
from unittest import TestCase, mock

from scripts.dev_orchestrator_usage.tokscale import (
    AccountQuota, QuotaResult, load_quotas, parse_quotas,
)

FIXTURE = Path(__file__).parent / "fixtures/usage/tokscale-usage.json"


class TokscaleQuotaTests(TestCase):
    def test_quotas_remain_separate_per_account(self):
        quotas = parse_quotas(json.loads(FIXTURE.read_text()))
        self.assertEqual([(q.account_alias, q.session.used_percent) for q in quotas], [("personal", 40), ("work", 30)])
        self.assertFalse(hasattr(quotas[0], "combined_percent"))

    @mock.patch("shutil.which", return_value=None)
    def test_missing_tokscale_returns_unavailable_without_error(self, _):
        self.assertEqual(load_quotas(), QuotaResult.unavailable("tokscale not installed"))

    @mock.patch("scripts.dev_orchestrator_usage.tokscale.subprocess.run")
    @mock.patch("scripts.dev_orchestrator_usage.tokscale.shutil.which", return_value="/bin/tokscale")
    def test_nonzero_timeout_and_invalid_json_are_unavailable(self, _, run):
        run.return_value = subprocess.CompletedProcess([], 1, "", "boom")
        self.assertFalse(load_quotas().available)
        run.side_effect = subprocess.TimeoutExpired([], 1)
        self.assertFalse(load_quotas().available)
        run.side_effect = None
        run.return_value = subprocess.CompletedProcess([], 0, "not json", "")
        self.assertFalse(load_quotas().available)

    def test_accepts_boundary_snake_case_variants(self):
        raw = {"providers": [{"provider": "codex", "account": {"name": "x"}, "session": {"used_percent": 12.5, "resets_at": "2026-09-24T12:00:00Z"}, "weekly": {"used_percent": 3, "resets_at": None}}]}
        quotas = parse_quotas(raw)
        self.assertEqual(quotas[0].session.used_percent, 12.5)
        self.assertIsNone(quotas[0].weekly.resets_at)

    def test_malformed_payloads_raise_value_error(self):
        for payload in ([], None, "text", {}, {"providers": {}}, {"providers": ["bad"]}):
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    parse_quotas(payload)

    @mock.patch("scripts.dev_orchestrator_usage.tokscale.shutil.which", return_value="/bin/tokscale")
    @mock.patch("scripts.dev_orchestrator_usage.tokscale.subprocess.run")
    def test_non_object_payload_is_unavailable(self, run, _):
        run.return_value = subprocess.CompletedProcess([], 0, "[]", "")
        result = load_quotas()
        self.assertFalse(result.available)
