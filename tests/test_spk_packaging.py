import json
import re
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "synology" / "package"


class SpkPackagingTests(unittest.TestCase):
    def test_package_metadata_and_scripts_use_unix_line_endings(self):
        files = [PACKAGE_ROOT / "INFO"]
        files.extend((PACKAGE_ROOT / "conf").iterdir())
        files.extend((PACKAGE_ROOT / "scripts").iterdir())
        for path in files:
            if path.is_file():
                self.assertNotIn(b"\r", path.read_bytes(), str(path))

    def test_all_lifecycle_scripts_have_a_shell_shebang(self):
        for path in (PACKAGE_ROOT / "scripts").iterdir():
            if path.is_file():
                self.assertTrue(path.read_bytes().startswith(b"#!/bin/sh\n"), str(path))

    def test_service_uses_bounded_rotating_log(self):
        start_script = (PACKAGE_ROOT / "scripts" / "start-stop-status").read_text(encoding="utf-8")
        backend = (ROOT / "backend.py").read_text(encoding="utf-8")
        self.assertIn('NAS_PORTAL_LOG_FILE="$LOG_FILE"', start_script)
        self.assertIn("RotatingFileHandler", backend)
        self.assertIn("LOG_MAX_BYTES = 1024 * 1024", backend)
        self.assertIn("LOG_BACKUP_COUNT = 2", backend)

    def test_versions_are_synchronized(self):
        info = (PACKAGE_ROOT / "INFO").read_text(encoding="utf-8")
        start_script = (PACKAGE_ROOT / "scripts" / "start-stop-status").read_text(encoding="utf-8")
        backend = (ROOT / "backend.py").read_text(encoding="utf-8")
        build_script = (ROOT / "synology" / "build-spk.ps1").read_text(encoding="utf-8")
        index = (ROOT / "synology" / "web" / "index.html").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        checklist = (ROOT / "docs" / "RELEASE_CHECKLIST.md").read_text(encoding="utf-8")
        package_release = re.search(r'^version="([0-9.]+-[0-9]+)"$', info, re.MULTILINE).group(1)
        package_version = package_release.rsplit("-", 1)[0]
        self.assertIn(f'NAS_PORTAL_VERSION="{package_version}"', start_script)
        self.assertIn(f'NAS_PORTAL_VERSION", "{package_version}"', backend)
        self.assertIn(f'$packageVersion = "{package_release}"', build_script)
        self.assertEqual(index.count(f"?v={package_version}"), 6)
        self.assertIn(f"nasdrop-{package_release}-x86_64.spk", readme)
        self.assertIn(f"# NASDrop {package_version} ", checklist)

    def test_distribution_license_sources_are_present(self):
        nasdrop_license = (ROOT / "LICENSE").read_text(encoding="utf-8")
        node_license = (ROOT / "synology" / "licenses" / "nodejs-LICENSE.txt").read_text(encoding="utf-8")
        notices = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
        build_script = (ROOT / "synology" / "build-spk.ps1").read_text(encoding="utf-8")

        self.assertIn("MIT License", nasdrop_license)
        self.assertIn("Copyright Node.js contributors", node_license)
        self.assertIn("Node.js 22.13.1", notices)
        self.assertIn('"licenses\\nodejs-LICENSE.txt"', build_script)
        self.assertIn('Join-Path $repoRoot "LICENSE"', build_script)

    def test_dsm_71_metadata_uses_compatible_node_runtime(self):
        info = (PACKAGE_ROOT / "INFO").read_text(encoding="utf-8")
        build_script = (ROOT / "synology" / "build-spk.ps1").read_text(encoding="utf-8")
        notices = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")

        self.assertIn('os_min_ver="7.1-42661"', info)
        self.assertIn('NodeVariant = "linux-x64-glibc-217"', build_script)
        self.assertIn("unofficial-builds.nodejs.org", build_script)
        self.assertIn("9c0927b3cdccce0d5d5196b9076cfbd356a4ad7214cd147631a74837e52ba88e", build_script)
        self.assertIn("linux-x64-glibc-217", notices)

    def test_dsm_application_identifier_is_synchronized(self):
        info = (PACKAGE_ROOT / "INFO").read_text(encoding="utf-8")
        ui_config = json.loads((ROOT / "synology" / "package-inner" / "ui" / "config").read_text(encoding="utf-8"))
        app_name = re.search(r'^dsmappname="([^"]+)"$', info, re.MULTILINE).group(1)
        self.assertEqual(list(ui_config[".url"]), [app_name])
        app = ui_config[".url"][app_name]
        self.assertEqual(app["title"], "NASDrop")
        self.assertEqual(app["desc"], "nasdrop:desc")
        self.assertIn("nasdrop:desc", app["preloadTexts"])

    def test_dsm_icon_uses_adaptive_launcher_instead_of_fixed_http_metadata(self):
        info = (PACKAGE_ROOT / "INFO").read_text(encoding="utf-8")
        self.assertNotIn('adminprotocol=', info)
        self.assertNotIn('adminport=', info)
        self.assertNotIn('adminurl=', info)

        launcher_sources = [
            ROOT / "synology" / "package-inner" / "ui" / "launcher.html",
            PACKAGE_ROOT / "scripts" / "postinst",
            PACKAGE_ROOT / "scripts" / "postupgrade",
        ]
        for path in launcher_sources:
            source = path.read_text(encoding="utf-8")
            self.assertIn('privateHost ? "http://" : "https://"', source, str(path))
            self.assertIn('var isV6 = plainHost.indexOf(":") !== -1;', source, str(path))
            self.assertIn('+ host + ":8791/', source, str(path))
            self.assertNotIn('location.replace("http://"', source, str(path))

    def test_launcher_port_setting_updates_installed_dsm_launcher(self):
        start_script = (PACKAGE_ROOT / "scripts" / "start-stop-status").read_text(encoding="utf-8")
        postinst = (PACKAGE_ROOT / "scripts" / "postinst").read_text(encoding="utf-8")
        postupgrade = (PACKAGE_ROOT / "scripts" / "postupgrade").read_text(encoding="utf-8")
        backend = (ROOT / "backend.py").read_text(encoding="utf-8")

        self.assertIn('"NAS_PORTAL_LAUNCHER_PORT": "8791"', postinst)
        self.assertIn('"NAS_PORTAL_LAUNCHER_PORT" not in data', postupgrade)
        self.assertIn('NAS_PORTAL_LAUNCHER_FILE="${SYNOPKG_PKGDEST}/ui/launcher.html"', start_script)
        self.assertIn('result["launcher_port"] = set_launcher_port', backend)
        self.assertIn('write_launcher_file(public_port=normalized)', backend)

    def test_default_destination_is_empty_and_requires_explicit_permission(self):
        example = json.loads((ROOT / "config.example.json").read_text(encoding="utf-8"))
        resource = json.loads((PACKAGE_ROOT / "conf" / "resource").read_text(encoding="utf-8"))
        postinst = (PACKAGE_ROOT / "scripts" / "postinst").read_text(encoding="utf-8")
        postupgrade = (PACKAGE_ROOT / "scripts" / "postupgrade").read_text(encoding="utf-8")
        backend = (ROOT / "backend.py").read_text(encoding="utf-8")
        app = (ROOT / "synology" / "web" / "app.js").read_text(encoding="utf-8")

        self.assertEqual(example["NAS_PORTAL_NAS_TARGET"], "")
        self.assertEqual(resource, {})
        self.assertIn('"NAS_PORTAL_NAS_TARGET": ""', postinst)
        self.assertIn('data.get("NAS_PORTAL_NAS_TARGET") == "/volume2/downloads"', postupgrade)
        self.assertIn('data["NAS_PORTAL_NAS_TARGET"] = ""', postupgrade)
        self.assertIn('Path(NAS_TARGET) if NAS_TARGET else None', backend)
        self.assertNotIn('state.status?.target || "/volume2/downloads"', app)


if __name__ == "__main__":
    unittest.main()
