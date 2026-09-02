from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DockerPackagingTests(unittest.TestCase):
    def test_image_contains_portable_runtime_and_healthcheck(self):
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        for package in ("python3", "nodejs", "curl", "7zip", "gosu"):
            self.assertRegex(dockerfile, rf"\b{re.escape(package)}\b")
        self.assertIn("NAS_PORTAL_STORAGE_ROOTS=/downloads", dockerfile)
        self.assertIn("NAS_PORTAL_7ZZ=/usr/bin/7zz", dockerfile)
        self.assertIn("/api/auth/status", dockerfile)
        self.assertIn('ENTRYPOINT ["/usr/local/bin/nasdrop-entrypoint"]', dockerfile)
        self.assertIn("docker/account.py /app/docker/account.py", dockerfile)
        self.assertIn("docker/account-command.sh /usr/local/bin/nasdrop-account", dockerfile)

    def test_entrypoint_never_recursively_changes_download_permissions(self):
        entrypoint = (ROOT / "docker" / "entrypoint.sh").read_text(encoding="utf-8")
        self.assertIn('chown "${PUID}:${PGID}" "$state_dir"', entrypoint)
        self.assertNotRegex(entrypoint, r"chown\s+(?:-[Rr]|--recursive)")
        self.assertNotIn('chown "${PUID}:${PGID}" "$target_dir"', entrypoint)
        self.assertIn('gosu "${PUID}:${PGID}"', entrypoint)

        account_command = (ROOT / "docker" / "account-command.sh").read_text(encoding="utf-8")
        self.assertIn('gosu "${PUID}:${PGID}" python3 /app/docker/account.py', account_command)

    def test_compose_persists_state_and_downloads(self):
        compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
        self.assertIn("ghcr.io/littleweirdlab0514-web/nasdrop:latest", compose)
        self.assertIn('"8791:8791"', compose)
        self.assertIn(":/config", compose)
        self.assertIn(":/downloads", compose)
        self.assertIn("no-new-privileges:true", compose)

    def test_release_workflow_builds_amd64_and_arm64(self):
        workflow = (ROOT / ".github" / "workflows" / "docker.yml").read_text(encoding="utf-8")
        self.assertIn("linux/amd64,linux/arm64", workflow)
        self.assertIn("ghcr.io/littleweirdlab0514-web/nasdrop", workflow)
        self.assertIn("packages: write", workflow)


if __name__ == "__main__":
    unittest.main()
