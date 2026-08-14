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
            self.assertTrue((output / "resolution.json").is_file())
            self.assertTrue((output / "agent-memory-portable-0.3.1.zip").is_file())

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
