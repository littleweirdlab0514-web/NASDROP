from pathlib import Path
import re
import shlex
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DockerPackagingTests(unittest.TestCase):
    def test_versions_follow_the_canonical_server_release(self):
        info = (ROOT / "synology" / "package" / "INFO").read_text(encoding="utf-8")
        match = re.search(r'^version="(\d+\.\d+\.\d+-\d+)"$', info, re.MULTILINE)
        self.assertIsNotNone(match)
        package_version = match.group(1)
        server_version = package_version.rsplit("-", 1)[0]

        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
        release_compose = (ROOT / "docker" / "compose.release.yaml").read_text(encoding="utf-8")
        backend = (ROOT / "backend.py").read_text(encoding="utf-8")
        self.assertIn(f"ARG NASDROP_VERSION={server_version}", dockerfile)
        self.assertIn(f'NASDROP_VERSION: "{server_version}"', compose)
        self.assertIn(
            f"image: ghcr.io/littleweirdlab0514-web/nasdrop:{package_version}",
            release_compose,
        )
        self.assertIn(
            f'PACKAGE_VERSION = setting("NAS_PORTAL_VERSION", "{server_version}")',
            backend,
        )

    def test_every_copy_source_is_explicitly_included_in_build_context(self):
        rules = (ROOT / '.dockerignore').read_text(encoding='utf-8').splitlines()
        self.assertEqual(rules[0], '**')
        included = {rule[1:].rstrip('/') for rule in rules if rule.startswith('!')}
        dockerfile = (ROOT / 'Dockerfile').read_text(encoding='utf-8')
        for line in dockerfile.splitlines():
            if not line.startswith('COPY '):
                continue
            for source in shlex.split(line)[1:-1]:
                self.assertTrue((ROOT / source).exists(), source)
                self.assertIn(source.rstrip('/'), included, f'Docker COPY source excluded: {source}')
        self.assertIn('transfer_parts.py', included)

    def test_image_contains_portable_runtime_and_healthcheck(self):
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        for package in ("python3", "nodejs", "curl", "7zip", "gosu"):
            self.assertRegex(dockerfile, rf"\b{re.escape(package)}\b")
        self.assertIn("NAS_PORTAL_STORAGE_ROOTS=/downloads", dockerfile)
        self.assertIn("NAS_PORTAL_7ZZ=/usr/local/bin/7zz", dockerfile)
        self.assertIn("ARG TARGETARCH", dockerfile)
        self.assertIn("SEVENZIP_SHA256_AMD64", dockerfile)
        self.assertIn("SEVENZIP_SHA256_ARM64", dockerfile)
        self.assertIn("grep -q ' Rar5 '", dockerfile)
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
        self.assertIn('python3 /app/docker/account.py bootstrap', entrypoint)
        account_source = (ROOT / "docker" / "account.py").read_text(encoding="utf-8")
        self.assertIn("enforce_docker_default_password_change", account_source)

        account_command = (ROOT / "docker" / "account-command.sh").read_text(encoding="utf-8")
        self.assertIn('gosu "${PUID}:${PGID}" python3 /app/docker/account.py', account_command)

    def test_web_accepts_only_the_short_bootstrap_password_as_current_credentials(self):
        page = (ROOT / "synology" / "web" / "index.html").read_text(encoding="utf-8")
        login = re.search(r'<input id="login-password"[^>]+>', page).group(0)
        current = re.search(r'<input id="current-password"[^>]+>', page).group(0)
        new = re.search(r'<input id="new-password"[^>]+>', page).group(0)
        self.assertNotIn("minlength", login)
        self.assertNotIn("minlength", current)
        self.assertIn('minlength="10"', new)
        self.assertIn('id="password-change-required-warning"', page)

    def test_release_compose_and_install_guides_are_runnable(self):
        release_compose = (ROOT / "docker" / "compose.release.yaml").read_text(encoding="utf-8")
        env_example = (ROOT / "docker" / "compose.env.example").read_text(encoding="utf-8")
        english = (ROOT / "docs" / "DOCKER_INSTALL.md").read_text(encoding="utf-8")
        korean = (ROOT / "docs" / "DOCKER_INSTALL.ko.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("ghcr.io/littleweirdlab0514-web/nasdrop:0.9.26-1", release_compose)
        self.assertNotIn("build:", release_compose)
        self.assertNotIn(":latest", release_compose)
        self.assertIn("NASDROP_TRUST_FORWARDED_FOR=false", env_example)
        self.assertIn("docker/compose.release.yaml", readme)
        for guide in (english, korean):
            self.assertIn("compose.release.yaml", guide)
            self.assertIn("docker save -o nasdrop-0.9.26-1-amd64.tar", guide)
            self.assertIn('gosu "$PUID:$PGID"', guide)
            self.assertNotIn("NASDrop-0.9.23-amd64.tar", guide)
            self.assertNotIn("test -w /downloads && echo writable'", guide)

    def test_compose_persists_state_and_downloads(self):
        compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
        self.assertIn("ghcr.io/littleweirdlab0514-web/nasdrop:latest", compose)
        self.assertIn('${NASDROP_PORT:-8791}:8791', compose)
        self.assertIn("init: true", compose)
        self.assertIn("stop_grace_period: 60s", compose)
        self.assertIn(":/config", compose)
        self.assertIn(":/downloads", compose)
        self.assertIn("read_only: true", compose)
        self.assertIn("no-new-privileges:true", compose)

    def test_release_workflow_builds_amd64_and_arm64(self):
        workflow = (ROOT / ".github" / "workflows" / "docker.yml").read_text(encoding="utf-8")
        self.assertIn("linux/amd64,linux/arm64", workflow)
        self.assertIn("ghcr.io/littleweirdlab0514-web/nasdrop", workflow)
        self.assertIn("packages: write", workflow)
        self.assertIn("nasdrop:smoke", workflow)
        self.assertIn("/api/auth/status", workflow)
        self.assertIn('"configured": true', workflow)
        self.assertIn('"password_change_required": true', workflow)
        self.assertIn("Verify image embeds canonical server files", workflow)
        self.assertIn("source-core.sha256", workflow)
        self.assertIn("source-web.sha256", workflow)
        self.assertIn("candidate-${{ steps.version.outputs.value }}", workflow)
        self.assertNotIn("type=raw,value=latest", workflow)
        self.assertNotIn("type=semver", workflow)

    def test_verified_candidate_is_promoted_without_rebuilding(self):
        workflow = (ROOT / ".github" / "workflows" / "docker-promote.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("workflow_dispatch", workflow)
        self.assertIn('[[ "$CONFIRMATION" == "promote" ]]', workflow)
        self.assertIn("candidate-$VERSION", workflow)
        self.assertIn("linux", workflow)
        self.assertIn("amd64", workflow)
        self.assertIn("arm64", workflow)
        self.assertIn("imagetools create", workflow)
        self.assertIn('--tag "$IMAGE:$VERSION"', workflow)
        self.assertIn('--tag "$IMAGE:$MINOR"', workflow)
        self.assertIn('--tag "$IMAGE:latest"', workflow)
        self.assertIn('"$IMAGE@$DIGEST"', workflow)
        self.assertNotIn("docker/build-push-action", workflow)


if __name__ == "__main__":
    unittest.main()
