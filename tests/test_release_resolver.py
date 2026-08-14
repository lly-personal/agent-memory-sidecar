from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
REPO_RESOLVER = ROOT / ".agents" / "skills" / "agent-memory-bootstrap-anchor" / "scripts" / "resolve_release.py"
PLUGIN_RESOLVER = ROOT / "plugins" / "agent-memory-sidecar" / "skills" / "agent-memory-bootstrap-anchor" / "scripts" / "resolve_release.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class ReleaseResolverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.resolver = load_module("agent_memory_release_resolver", REPO_RESOLVER)

    def urlopen_response(self, *, expected_auth: str | None, payload: bytes = b"{}"):
        test = self

        class Response:
            headers = {"Content-Length": str(len(payload))}

            def __init__(self) -> None:
                self.finished = False

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _size: int) -> bytes:
                if self.finished:
                    return b""
                self.finished = True
                return payload

        def fake_urlopen(request, *, timeout: int):
            test.assertEqual(30, timeout)
            test.assertEqual(expected_auth, request.get_header("Authorization"))
            return Response()

        return fake_urlopen

    def fixture(
        self,
        *,
        immutable: bool = True,
        marketplace_ref: str | None = None,
        marketplace_source_kind: str = "git-subdir",
    ) -> tuple[dict, dict[str, bytes], str]:
        tag = "v0.3.1"
        commit = "a" * 40
        source_manifest = {
            "contract_version": "agent_memory_source_manifest_v1",
            "distribution": "release",
            "sidecar": {
                "remote": "https://github.com/lly-personal/agent-memory-sidecar.git",
                "ref": tag,
                "commit": commit,
            },
            "canonical_owner": None,
        }
        source_bytes = json.dumps(source_manifest, sort_keys=True, separators=(",", ":")).encode() + b"\n"
        portable_buffer = io.BytesIO()
        with zipfile.ZipFile(portable_buffer, "w") as archive:
            archive.writestr("source-manifest.json", source_bytes)
            archive.writestr("plugins/agent-memory-sidecar/source-manifest.json", source_bytes)
            marketplace = {
                "name": "agent-memory",
                "interface": {"displayName": "Agent Memory"},
                "plugins": [{
                    "name": "agent-memory-sidecar",
                    "source": {
                        "source": marketplace_source_kind,
                        "url": "https://github.com/lly-personal/agent-memory-sidecar.git",
                        "path": "./plugins/agent-memory-sidecar",
                        "ref": marketplace_ref or tag,
                    },
                    "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
                    "category": "Productivity",
                }],
            }
            archive.writestr(".agents/plugins/marketplace.json", json.dumps(marketplace))
            archive.writestr(
                ".agents/skills/agent-memory-bootstrap-anchor/SKILL.md",
                b"same anchor\n",
            )
            archive.writestr(
                "plugins/agent-memory-sidecar/skills/agent-memory-bootstrap-anchor/SKILL.md",
                b"same anchor\n",
            )
            archive.writestr(
                ".agents/skills/agent-memory-bootstrap-anchor/scripts/resolve_release.py",
                b"same resolver\n",
            )
            archive.writestr(
                ".agents/skills/agent-memory-workstation-bootstrap/SKILL.md",
                b"bootstrap skill\n",
            )
            archive.writestr(
                ".agents/skills/agent-memory-workstation-bootstrap/scripts/enrollment.py",
                b"enrollment script\n",
            )
            archive.writestr(
                ".agents/skills/agent-memory-workstation-bootstrap/scripts/managed_sources.py",
                b"managed sources script\n",
            )
            archive.writestr(
                ".agents/skills/global-owner-scout/SKILL.md",
                b"scout skill\n",
            )
            archive.writestr(
                "plugins/agent-memory-sidecar/skills/agent-memory-bootstrap-anchor/scripts/resolve_release.py",
                b"same resolver\n",
            )
        portable_name = "agent-memory-portable-0.3.1.zip"
        portable = portable_buffer.getvalue()
        source_sha = hashlib.sha256(source_bytes).hexdigest()
        portable_sha = hashlib.sha256(portable).hexdigest()
        release_manifest = {
            "contract_version": "agent_memory_public_release_manifest_v1",
            "status": "public_artifact_verified",
            "source": {
                "repository": "https://github.com/lly-personal/agent-memory-sidecar",
                "ref": tag,
                "commit": commit,
            },
            "versions": {"core": "0.3.1", "plugin": "1.2.0", "bootstrap": "1.7.0", "scout": "5.5.0"},
            "artifacts": [
                {"path": portable_name, "sha256": portable_sha},
                {"path": "source-manifest.json", "sha256": source_sha},
            ],
        }
        release_bytes = json.dumps(release_manifest, sort_keys=True, separators=(",", ":")).encode() + b"\n"
        release_sha = hashlib.sha256(release_bytes).hexdigest()
        checksums = (
            f"{portable_sha}  {portable_name}\n"
            f"{release_sha}  release-manifest.json\n"
            f"{source_sha}  source-manifest.json\n"
        ).encode()
        payloads = {
            "SHA256SUMS": checksums,
            "source-manifest.json": source_bytes,
            "release-manifest.json": release_bytes,
            portable_name: portable,
        }
        assets = []
        for name, value in payloads.items():
            assets.append({
                "name": name,
                "browser_download_url": f"https://github.com/lly-personal/agent-memory-sidecar/releases/download/{tag}/{name}",
                "digest": "sha256:" + hashlib.sha256(value).hexdigest(),
                "size": len(value),
            })
        release = {
            "tag_name": tag,
            "draft": False,
            "prerelease": False,
            "immutable": immutable,
            "assets": assets,
        }
        return release, payloads, commit

    def test_resolver_is_identical_across_anchor_surfaces(self) -> None:
        self.assertEqual(REPO_RESOLVER.read_bytes(), PLUGIN_RESOLVER.read_bytes())

    def test_api_request_uses_explicit_github_token(self) -> None:
        with mock.patch.dict(
            self.resolver.os.environ,
            {"GITHUB_TOKEN": "", "GH_TOKEN": "github-token-for-test"},
        ), mock.patch.object(
            self.resolver.urllib.request,
            "urlopen",
            side_effect=self.urlopen_response(expected_auth="Bearer github-token-for-test"),
        ):
            self.assertEqual(b"{}", self.resolver._request(self.resolver.API_ROOT, limit=1024))

    def test_api_rate_limit_has_a_distinct_failure(self) -> None:
        error = self.resolver.urllib.error.HTTPError(
            self.resolver.API_ROOT,
            403,
            "rate limit exceeded",
            {"X-RateLimit-Remaining": "0"},
            None,
        )
        with mock.patch.dict(
            self.resolver.os.environ,
            {"GITHUB_TOKEN": "", "GH_TOKEN": ""},
        ), mock.patch.object(
            self.resolver.urllib.request,
            "urlopen",
            side_effect=error,
        ):
            with self.assertRaisesRegex(
                self.resolver.ResolutionError,
                "release_github_api_rate_limited",
            ):
                self.resolver._request(self.resolver.API_ROOT, limit=1024)

    def test_api_request_uses_existing_noninteractive_gh_token(self) -> None:
        completed = self.resolver.subprocess.CompletedProcess(
            args=["gh", "auth", "token"],
            returncode=0,
            stdout="gh-token-for-test\n",
            stderr="",
        )
        with mock.patch.dict(
            self.resolver.os.environ,
            {"GITHUB_TOKEN": "", "GH_TOKEN": ""},
        ), mock.patch.object(
            self.resolver.shutil,
            "which",
            return_value="gh",
        ), mock.patch.object(
            self.resolver.subprocess,
            "run",
            return_value=completed,
        ), mock.patch.object(
            self.resolver.urllib.request,
            "urlopen",
            side_effect=self.urlopen_response(expected_auth="Bearer gh-token-for-test"),
        ):
            self.assertEqual(b"{}", self.resolver._request(self.resolver.API_ROOT, limit=1024))

    def test_release_asset_request_never_receives_api_token(self) -> None:
        with mock.patch.dict(
            self.resolver.os.environ,
            {"GITHUB_TOKEN": "github-token-for-test", "GH_TOKEN": ""},
        ), mock.patch.object(
            self.resolver.urllib.request,
            "urlopen",
            side_effect=self.urlopen_response(expected_auth=None, payload=b"ok"),
        ):
            self.assertEqual(
                b"ok",
                self.resolver._request(
                    "https://github.com/lly-personal/agent-memory-sidecar/releases/download/v0.3.1/SHA256SUMS",
                    limit=1024,
                ),
            )

    def test_resolver_verifies_immutable_release_and_writes_only_after_success(self) -> None:
        release, payloads, commit = self.fixture()

        def fake_json(url: str):
            if "/git/ref/tags/" in url:
                return {"object": {"type": "commit", "sha": commit}}
            return release

        def fake_bytes(url: str, *, limit: int):
            del limit
            return payloads[url.rsplit("/", 1)[1]]

        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(
            self.resolver, "_get_json", side_effect=fake_json
        ), mock.patch.object(
            self.resolver, "_get_bytes", side_effect=fake_bytes
        ):
            output = Path(temporary) / "resolved"
            result = self.resolver.resolve_release(output=output, version="0.3.1")
            self.assertEqual("verified", result["status"])
            self.assertEqual(commit, result["commit"])
            self.assertEqual("portable", result["portable_root"])
            self.assertTrue((output / "resolution.json").is_file())
            self.assertTrue((output / "agent-memory-portable-0.3.1.zip").is_file())
            self.assertEqual(
                b"managed sources script\n",
                (
                    output / "portable" / ".agents" / "skills"
                    / "agent-memory-workstation-bootstrap" / "scripts" / "managed_sources.py"
                ).read_bytes(),
            )

    def test_portable_materialization_rejects_symbolic_link_entries(self) -> None:
        value = io.BytesIO()
        with zipfile.ZipFile(value, "w") as archive:
            info = zipfile.ZipInfo("linked")
            info.create_system = 3
            info.external_attr = 0o120777 << 16
            archive.writestr(info, "outside")
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "portable"
            with self.assertRaisesRegex(
                self.resolver.ResolutionError,
                "release_portable_entry_invalid",
            ):
                self.resolver._materialize_portable(value.getvalue(), destination=target)
            self.assertFalse(target.exists())

    def test_portable_materialization_rejects_case_collisions(self) -> None:
        value = io.BytesIO()
        with zipfile.ZipFile(value, "w") as archive:
            archive.writestr("Skill/File.txt", "first")
            archive.writestr("skill/file.txt", "second")
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "portable"
            with self.assertRaisesRegex(
                self.resolver.ResolutionError,
                "release_portable_duplicate",
            ):
                self.resolver._materialize_portable(value.getvalue(), destination=target)
            self.assertFalse(target.exists())

    def test_resolver_rejects_mutable_release_without_writing_output(self) -> None:
        release, _, commit = self.fixture(immutable=False)
        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(
            self.resolver,
            "_get_json",
            side_effect=lambda url: {"object": {"type": "commit", "sha": commit}} if "/git/ref/tags/" in url else release,
        ):
            output = Path(temporary) / "resolved"
            with self.assertRaisesRegex(
                self.resolver.ResolutionError,
                "release_not_immutable_stable",
            ):
                self.resolver.resolve_release(output=output)
            self.assertFalse(output.exists())

    def test_resolver_rejects_asset_digest_mismatch(self) -> None:
        release, payloads, commit = self.fixture()
        release["assets"][0]["digest"] = "sha256:" + "f" * 64

        def fake_json(url: str):
            if "/git/ref/tags/" in url:
                return {"object": {"type": "commit", "sha": commit}}
            return release

        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(
            self.resolver, "_get_json", side_effect=fake_json
        ), mock.patch.object(
            self.resolver, "_get_bytes", side_effect=lambda url, limit: payloads[url.rsplit("/", 1)[1]]
        ):
            output = Path(temporary) / "resolved"
            with self.assertRaisesRegex(self.resolver.ResolutionError, "release_asset_digest_mismatch"):
                self.resolver.resolve_release(output=output, version="v0.3.1")
            self.assertFalse(output.exists())

    def test_resolver_rejects_marketplace_ref_drift(self) -> None:
        release, payloads, commit = self.fixture(marketplace_ref="main")

        def fake_json(url: str):
            if "/git/ref/tags/" in url:
                return {"object": {"type": "commit", "sha": commit}}
            return release

        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(
            self.resolver, "_get_json", side_effect=fake_json
        ), mock.patch.object(
            self.resolver, "_get_bytes", side_effect=lambda url, limit: payloads[url.rsplit("/", 1)[1]]
        ):
            output = Path(temporary) / "resolved"
            with self.assertRaisesRegex(self.resolver.ResolutionError, "release_marketplace_invalid"):
                self.resolver.resolve_release(output=output, version="v0.3.1")
            self.assertFalse(output.exists())

    def test_resolver_rejects_marketplace_source_kind_drift(self) -> None:
        release, payloads, commit = self.fixture(marketplace_source_kind="git")

        def fake_json(url: str):
            if "/git/ref/tags/" in url:
                return {"object": {"type": "commit", "sha": commit}}
            return release

        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(
            self.resolver, "_get_json", side_effect=fake_json
        ), mock.patch.object(
            self.resolver, "_get_bytes", side_effect=lambda url, limit: payloads[url.rsplit("/", 1)[1]]
        ):
            output = Path(temporary) / "resolved"
            with self.assertRaisesRegex(self.resolver.ResolutionError, "release_marketplace_invalid"):
                self.resolver.resolve_release(output=output, version="v0.3.1")
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
