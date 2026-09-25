from __future__ import annotations

import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

import yaml


ROOT = Path(__file__).resolve().parents[1]


class UsagePackagingTests(unittest.TestCase):
    def test_usage_wrapper_does_not_write_bytecode(self):
        """The embedded helper must remain code-signature safe after execution."""
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            scripts = root / "scripts"
            package = scripts / "dev_orchestrator_usage"
            package.mkdir(parents=True)
            wrapper = scripts / "dev-orchestrator-usage"
            shutil.copy2(ROOT / "scripts/dev-orchestrator-usage", wrapper)
            wrapper.chmod(wrapper.stat().st_mode | 0o111)
            for source in (ROOT / "scripts/dev_orchestrator_usage").glob("*.py"):
                shutil.copy2(source, package / source.name)

            result = subprocess.run(
                [str(wrapper), "--help"],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(list(package.rglob("*.pyc")))
            self.assertFalse(list(package.rglob("*.pyo")))
            self.assertFalse(list(package.rglob("__pycache__")))

    def test_codex_install_contains_usage_cli_and_package(self):
        with TemporaryDirectory() as tmp:
            env = {**os.environ, "CODEX_HOME": tmp}
            subprocess.run([str(ROOT / "scripts/install_codex.sh")], env=env, check=True)
            package = Path(tmp) / "skills/dev-orchestrator"
            self.assertTrue((package / "scripts/dev-orchestrator-usage").is_file())
            self.assertTrue((package / "scripts/dev_orchestrator_usage/cli.py").is_file())
            self.assertTrue(os.access(package / "scripts/dev-orchestrator-usage", os.X_OK))

    def test_chatgpt_export_excludes_local_usage_scripts(self):
        env = {**os.environ, "DEV_ORCHESTRATOR_SKIP_USAGE_TESTS": "1"}
        subprocess.run([str(ROOT / "scripts/export_chatgpt.sh")], env=env, check=True)
        with ZipFile(ROOT / "dist/chatgpt/dev-orchestrator-chatgpt-skill.zip") as archive:
            self.assertFalse(any("/scripts/" in name or name.startswith("dev-orchestrator/scripts/") for name in archive.namelist()))

    def test_tracking_policy_is_opt_in(self):
        config = yaml.safe_load((ROOT / "config.yaml").read_text())
        self.assertEqual(config["usage_tracking"]["mode"], "opt_in")

    def test_external_effort_defaults_match_cli_compatibility(self):
        config = yaml.safe_load((ROOT / "config.yaml").read_text())
        self.assertEqual(config["roles"]["investigate"]["effort"], "high")
        self.assertEqual(config["roles"]["quick_review"]["effort"], "high")
        self.assertEqual(config["roles"]["independent_review"]["effort"], "auto")

    def test_chatgpt_adapter_still_disclaims_local_session_access(self):
        text = (ROOT / "adapters/chatgpt/SKILL.md").read_text().lower()
        self.assertIn("do not claim", text)
        self.assertIn("local", text)

    def test_portable_version_is_221(self):
        self.assertEqual((ROOT / "VERSION").read_text().strip(), "2.2.1")
        config = yaml.safe_load((ROOT / "config.yaml").read_text())
        self.assertEqual(config["portable_version"], "2.2.1")

    def test_smoke_fixture_is_exact(self):
        self.assertEqual((ROOT / "tests/fixtures/usage/smoke-prompt.txt").read_text().strip(), "Reply exactly OK")

    def test_validation_runs_all_usage_tests(self):
        text = (ROOT / "scripts/validate.sh").read_text()
        self.assertIn("test_usage_*.py", text)

    def test_usage_package_imports_with_validator_python(self):
        subprocess.run(
            [sys.executable, "-c", "from scripts.dev_orchestrator_usage import cli"],
            cwd=ROOT,
            check=True,
        )

    def test_install_cleanup_cannot_turn_success_into_failure(self):
        with TemporaryDirectory() as tmp:
            env = {**os.environ, "CODEX_HOME": tmp}
            subprocess.run([str(ROOT / "scripts/install_codex.sh")], env=env, check=True)

    def test_install_check_cleans_staging_directory_without_warning(self):
        with TemporaryDirectory() as tmp, TemporaryDirectory() as staging:
            env = {**os.environ, "CODEX_HOME": tmp, "TMPDIR": staging}
            subprocess.run([str(ROOT / "scripts/install_codex.sh")], env=env, check=True, capture_output=True, text=True)
            result = subprocess.run([str(ROOT / "scripts/install_codex.sh"), "--check"], env=env, check=True, capture_output=True, text=True)
            self.assertNotIn("retained for manual cleanup", result.stderr)
            self.assertFalse(any(path.name.startswith("dev-orchestrator-codex.") for path in Path(staging).iterdir()))

    def test_install_bad_argument_stays_nonzero(self):
        result = subprocess.run([str(ROOT / "scripts/install_codex.sh"), "--bad"], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)

    def test_docs_cover_usage_semantics(self):
        text = (ROOT / "README.md").read_text().lower()
        for phrase in ("exact", "n/a", "account", "quota", "privacy", "tokscale", "tokenbar", "opt-out"):
            self.assertIn(phrase, text)

    def test_external_agent_docs_show_valid_tracked_agy_contract(self):
        text = (ROOT / "core/external-agents.md").read_text()
        self.assertIn("dev-orchestrator-usage run-agy", text)
        self.assertIn("--role <role>", text)
        self.assertIn("--model <resolved-model-id>", text)
        self.assertIn("--effort <compatible-effort>", text)
        self.assertIn("--prompt-file <prompt-file>", text)
        self.assertIn("must not append a second `agy`", text)
        self.assertNotIn("run-agy -- agy", text)

    def test_codex_adapter_documents_role_attribution_and_lifecycle_examples(self):
        text = (ROOT / "adapters/codex/SKILL.md").read_text()
        for phrase in (
            "task-start",
            "checkpoint --role <actual-role>",
            "finish --role <actual-role>",
            "Every role-boundary checkpoint",
            "diagnostic/non-blocking",
            "opt-in",
        ):
            self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
