from __future__ import annotations

import plistlib
import os
import re
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLIST = ROOT / "macos/DevOrchestratorBar/Resources/Info.plist"
BUILD_SCRIPT = ROOT / "scripts/build_macos_app.sh"
INSTALL_SCRIPT = ROOT / "scripts/install_macos_app.sh"


class MacOSPackagingTests(unittest.TestCase):
    @staticmethod
    def _executable_lines(path: Path) -> list[str]:
        """Return non-empty, non-comment lines so comments cannot satisfy checks."""
        return [
            line.strip()
            for line in path.read_text().splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]

    @staticmethod
    def _line_index(lines: list[str], pattern: str) -> int:
        compiled = re.compile(pattern)
        for index, line in enumerate(lines):
            if compiled.search(line):
                return index
        raise AssertionError(f"no executable line matched {pattern!r}")

    def test_info_plist_declares_menu_bar_bundle_contract(self):
        manifest = plistlib.loads(PLIST.read_bytes())

        self.assertEqual(manifest["CFBundleExecutable"], "DevOrchestratorBar")
        self.assertEqual(manifest["CFBundleIdentifier"], "com.unizalin.DevOrchestratorBar")
        self.assertEqual(manifest["CFBundleName"], "Dev Orchestrator")
        self.assertEqual(manifest["CFBundlePackageType"], "APPL")
        self.assertEqual(manifest["CFBundleShortVersionString"], "2.2.0")
        self.assertEqual(manifest["CFBundleVersion"], "220")
        self.assertEqual(manifest["LSMinimumSystemVersion"], "13.0")
        self.assertIs(manifest["LSUIElement"], True)

    def test_build_script_assembles_helper_and_python_module_tree(self):
        lines = self._executable_lines(BUILD_SCRIPT)
        script = "\n".join(lines)

        self.assertIn("set -euo pipefail", script)
        self.assertIn('source_root="$(cd "$script_dir/.." && pwd -P)"', script)
        self.assertIn('debug|release', script)
        self.assertIn('usage_wrapper="$source_root/scripts/dev-orchestrator-usage"', script)
        self.assertIn('usage_module="$source_root/scripts/dev_orchestrator_usage"', script)
        self.assertIn('usage_cli="$contents/Resources/UsageCLI"', script)
        self.assertIn('cp "$binary_path" "$contents/MacOS/DevOrchestratorBar"', script)
        self.assertIn('codesign --force --deep --sign - "$app_path"', script)
        self.assertIn('codesign --verify --deep --strict "$app_path"', script)

    def test_build_script_validates_exact_app_destination_before_replacement(self):
        lines = self._executable_lines(BUILD_SCRIPT)
        script = "\n".join(lines)

        self.assertIn('app_path="$dist_root/DevOrchestratorBar.app"', script)
        self.assertIn('$(basename "$app_path")', script)
        self.assertIn('$(dirname "$app_path")', script)
        self.assertIn('rm -rf "$app_path"', script)

    def test_build_script_copies_resources_and_signs_in_real_order(self):
        lines = self._executable_lines(BUILD_SCRIPT)

        copy_binary = self._line_index(lines, r'^cp "\$binary_path" "\$contents/MacOS/DevOrchestratorBar"$')
        copy_plist = self._line_index(lines, r'^cp "\$info_plist" "\$contents/Info\.plist"$')
        copy_wrapper = self._line_index(lines, r'^cp "\$usage_wrapper" "\$usage_cli/dev-orchestrator-usage"$')
        copy_module = self._line_index(lines, r'^cp -R "\$usage_module" "\$usage_cli/dev_orchestrator_usage"$')
        chmod = self._line_index(lines, r'^chmod 755 "\$contents/MacOS/DevOrchestratorBar"')
        move = self._line_index(lines, r'^mv "\$staged_app" "\$app_path"$')
        sign = self._line_index(lines, r'^codesign --force --deep --sign - "\$app_path"$')
        verify = self._line_index(lines, r'^codesign --verify --deep --strict "\$app_path"$')

        self.assertLess(copy_binary, copy_plist)
        self.assertLess(copy_plist, copy_wrapper)
        self.assertLess(copy_wrapper, copy_module)
        self.assertLess(copy_module, chmod)
        self.assertLess(chmod, move)
        self.assertLess(move, sign)
        self.assertLess(sign, verify)

    def test_install_script_backs_up_existing_app_before_staged_replacement(self):
        lines = self._executable_lines(INSTALL_SCRIPT)
        script = "\n".join(lines)

        self.assertIn("set -euo pipefail", script)
        self.assertIn('DEV_ORCHESTRATOR_APP_DIR:-$HOME/Applications', script)
        self.assertIn('$(basename "$destination")', script)
        self.assertIn("Application Support/dev-orchestrator/backups/apps", script)
        self.assertIn('mv "$destination" "$backup_path"', script)
        self.assertIn('ditto "$source_app" "$staged_app"', script)
        self.assertNotIn("open ", script)
        self.assertNotIn("launchctl", script)

    def test_install_script_uses_verified_parent_staging_and_safe_order(self):
        lines = self._executable_lines(INSTALL_SCRIPT)

        safety = self._line_index(lines, r'^if \[\[ "\$destination" != "\$expected_destination"')
        stage_mktemp = self._line_index(
            lines, r'^stage_dir="\$\(mktemp -d "\$app_dir/\.DevOrchestratorBar\.install\.XXXXXX"\)"$'
        )
        stage_copy = self._line_index(lines, r'^ditto "\$source_app" "\$staged_app"$')
        stage_verify = self._line_index(lines, r'^codesign --verify --deep --strict "\$staged_app"$')
        backup = self._line_index(lines, r'^mv "\$destination" "\$backup_path"$')
        final_move = self._line_index(lines, r'^mv "\$staged_app" "\$destination"$')
        trap = self._line_index(lines, r'^trap on_exit EXIT$')

        self.assertLess(safety, stage_mktemp)
        self.assertLess(stage_mktemp, stage_copy)
        self.assertLess(stage_copy, stage_verify)
        self.assertLess(stage_verify, backup)
        self.assertLess(backup, final_move)
        self.assertLess(trap, stage_mktemp)
        script = "\n".join(lines)
        self.assertRegex(script, r'stage_dir="\$\(mktemp -d "\$app_dir/\.DevOrchestratorBar\.install\.XXXXXX"\)"')
        self.assertIn('"$stage_base" =~ ^\\.DevOrchestratorBar\\.install\\.[A-Za-z0-9]+$', script)
        self.assertIn('realpath "$stage_dir"', script)

    def test_install_script_trap_restores_backup_after_replacement_failure(self):
        lines = self._executable_lines(INSTALL_SCRIPT)
        script = "\n".join(lines)

        self.assertIn("backup_created=0", script)
        self.assertIn("backup_created=1", script)
        restore_index = self._line_index(lines, r'^if mv "\$backup_path" "\$destination"; then$')
        remove_destination = self._line_index(lines, r'^if ! rm -rf -- "\$destination"; then$')
        self.assertLess(remove_destination, restore_index)
        self.assertRegex(script, r'printf .*backup_path')
        self.assertRegex(script, r'printf .*restor')

    def test_install_script_failure_restores_original_app_in_fake_environment(self):
        """Exercise the failure trap with fake build/codesign/ditto/mv tools."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scripts = root / "scripts"
            scripts.mkdir()
            installer = scripts / "install_macos_app.sh"
            shutil.copy2(INSTALL_SCRIPT, installer)
            installer.chmod(installer.stat().st_mode | stat.S_IXUSR)
            build = scripts / "build_macos_app.sh"
            build.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "mkdir -p \"$(dirname \"$0\")/../dist/DevOrchestratorBar.app\"\n"
                "printf new > \"$(dirname \"$0\")/../dist/DevOrchestratorBar.app/marker\"\n"
            )
            build.chmod(build.stat().st_mode | stat.S_IXUSR)
            fake_bin = root / "fake-bin"
            fake_bin.mkdir()
            (fake_bin / "ditto").write_text(
                "#!/usr/bin/env bash\nset -euo pipefail\ncp -R \"$1\" \"$2\"\n"
            )
            (fake_bin / "codesign").write_text("#!/usr/bin/env bash\nexit 0\n")
            (fake_bin / "mv").write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "if [[ \"$1\" == */.DevOrchestratorBar.install.*/* ]]; then exit 42; fi\n"
                "exec /bin/mv \"$@\"\n"
            )
            for tool in (fake_bin / "ditto", fake_bin / "codesign", fake_bin / "mv"):
                tool.chmod(tool.stat().st_mode | stat.S_IXUSR)

            home = root / "home"
            app_dir = home / "Applications"
            destination = app_dir / "DevOrchestratorBar.app"
            destination.mkdir(parents=True)
            (destination / "marker").write_text("old")
            env = os.environ.copy()
            env.update(
                {
                    "HOME": str(home),
                    "DEV_ORCHESTRATOR_APP_DIR": str(app_dir),
                    "PATH": f"{fake_bin}:{env['PATH']}",
                }
            )
            result = subprocess.run(
                [str(installer)], env=env, text=True, capture_output=True, check=False
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("restore", (result.stdout + result.stderr).lower())
            self.assertEqual((destination / "marker").read_text(), "old")
            self.assertFalse(any(app_dir.glob(".DevOrchestratorBar.install.*")))


if __name__ == "__main__":
    unittest.main()
