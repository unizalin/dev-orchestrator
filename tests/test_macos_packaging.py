from __future__ import annotations

import plistlib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLIST = ROOT / "macos/DevOrchestratorBar/Resources/Info.plist"
BUILD_SCRIPT = ROOT / "scripts/build_macos_app.sh"
INSTALL_SCRIPT = ROOT / "scripts/install_macos_app.sh"


class MacOSPackagingTests(unittest.TestCase):
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
        script = BUILD_SCRIPT.read_text()

        self.assertIn("set -euo pipefail", script)
        self.assertIn("source_root", script)
        self.assertIn('debug|release', script)
        self.assertIn("scripts/dev-orchestrator-usage", script)
        self.assertIn("scripts/dev_orchestrator_usage", script)
        self.assertIn("Resources/UsageCLI", script)
        self.assertIn('"$contents/MacOS/DevOrchestratorBar"', script)
        self.assertIn("codesign --force --deep --sign -", script)
        self.assertIn("codesign --verify --deep --strict", script)

    def test_build_script_validates_exact_app_destination_before_replacement(self):
        script = BUILD_SCRIPT.read_text()

        self.assertIn('app_path="$dist_root/DevOrchestratorBar.app"', script)
        self.assertIn('$(basename "$app_path")', script)
        self.assertIn('$(dirname "$app_path")', script)
        self.assertIn('rm -rf "$app_path"', script)

    def test_install_script_backs_up_existing_app_before_ditto(self):
        script = INSTALL_SCRIPT.read_text()

        self.assertIn("set -euo pipefail", script)
        self.assertIn('DEV_ORCHESTRATOR_APP_DIR:-$HOME/Applications', script)
        self.assertIn('$(basename "$destination")', script)
        self.assertIn("Application Support/dev-orchestrator/backups/apps", script)
        self.assertIn('mv "$destination" "$backup_path"', script)
        self.assertIn('ditto "$source_app" "$destination"', script)
        self.assertNotIn("open ", script)
        self.assertNotIn("launchctl", script)


if __name__ == "__main__":
    unittest.main()
