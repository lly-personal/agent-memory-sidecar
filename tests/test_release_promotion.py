from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "publish_release.py"
COMMIT = "a" * 40
REPOSITORY = "example/agent-memory-sidecar"
TAG = "v0.3.6"


def load_module():
    spec = importlib.util.spec_from_file_location("release_promotion", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_fixture(root: Path) -> Path:
    (root / "CHANGELOG.md").write_text(
        "# Changelog\n\n## 0.3.6 (2026-08-21)\n\n- Released component set.\n\n## 0.3.5\n",
        encoding="utf-8",
    )
    output = root / "dist" / "release"
    core = output / "core"
    core.mkdir(parents=True)
    artifacts = {
        "core/agent_memory_sidecar-0.3.6-py3-none-any.whl": b"wheel",
        "agent-memory-portable-0.3.6.zip": b"portable",
        "source-manifest.json": b"{}\n",
    }
    for relative, content in artifacts.items():
        path = output / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    manifest = {
        "contract_version": "agent_memory_public_release_manifest_v1",
        "status": "public_artifact_verified",
        "source": {
            "repository": f"https://github.com/{REPOSITORY}",
            "ref": TAG,
            "commit": COMMIT,
        },
        "artifacts": [
            {
                "path": relative,
                "bytes": (output / relative).stat().st_size,
                "sha256": sha256(output / relative),
            }
            for relative in artifacts
        ],
    }
    manifest_path = output / "release-manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    checksum_paths = [*(output / relative for relative in artifacts), manifest_path]
    (output / "SHA256SUMS").write_text(
        "".join(f"{sha256(path)}  {path.relative_to(output).as_posix()}\n" for path in checksum_paths),
        encoding="utf-8",
    )
    return output


class FakeRunner:
    def __init__(self, module, asset_dir: Path) -> None:
        assets, _ = module._release_files(asset_dir)
        self.assets = [
            {
                "name": item["name"],
                "size": item["bytes"],
                "digest": f"sha256:{item['sha256']}",
                "state": "uploaded",
            }
            for item in reversed(assets)
        ]
        self.published = False
        self.immutable_after_publish = True
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, command: list[str], root: Path) -> str:
        del root
        call = tuple(command)
        self.calls.append(call)
        if call[:3] == ("git", "status", "--porcelain"):
            return ""
        if call[:3] == ("git", "rev-parse", "HEAD"):
            return COMMIT
        if call[:3] == ("git", "rev-parse", "--verify"):
            return COMMIT
        if call[:3] == ("git", "cat-file", "-t"):
            return "tag"
        if call[:4] == ("git", "remote", "get-url", "origin"):
            return f"https://github.com/{REPOSITORY}.git"
        if call[:3] == ("git", "ls-remote", "origin") and "refs/heads/main" in call:
            return f"{COMMIT}\trefs/heads/main"
        if call[:3] == ("git", "ls-remote", "--tags"):
            return f"{'b' * 40}\trefs/tags/{TAG}\n{COMMIT}\trefs/tags/{TAG}^{{}}"
        if call[:3] == ("gh", "api", f"repos/{REPOSITORY}/immutable-releases"):
            return json.dumps({"enabled": True})
        if call[:3] == ("gh", "release", "view"):
            return json.dumps(
                {
                    "assets": self.assets,
                    "isDraft": not self.published,
                    "isImmutable": self.published and self.immutable_after_publish,
                    "isPrerelease": False,
                    "name": TAG,
                    "publishedAt": "2026-08-21T12:00:00Z" if self.published else None,
                    "tagName": TAG,
                    "url": f"https://github.com/{REPOSITORY}/releases/tag/{TAG}",
                }
            )
        if call[:3] == ("gh", "release", "edit"):
            self.published = True
            return ""
        if call[:3] in (("gh", "release", "verify"), ("gh", "release", "verify-asset")):
            return "{}"
        raise AssertionError(f"unexpected command: {command}")


class ReleasePromotionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.promotion = load_module()

    def test_inspect_and_apply_close_the_immutable_release_loop(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            asset_dir = make_fixture(root)
            runner = FakeRunner(self.promotion, asset_dir)
            inputs = {
                "root": root,
                "asset_dir": asset_dir,
                "repository": REPOSITORY,
                "tag": TAG,
                "expected_commit": COMMIT,
                "runner": runner,
            }
            plan = self.promotion.inspect_plan(**inputs)
            self.assertEqual("authorization_required", plan["status"])
            self.assertEqual(64, len(plan["plan_hash"]))
            self.assertFalse(any(call[:3] == ("gh", "release", "edit") for call in runner.calls))

            receipt = self.promotion.apply_plan(
                **inputs,
                plan_hash=plan["plan_hash"],
                wait=lambda _: None,
            )
            self.assertEqual("public_published", receipt["status"])
            self.assertTrue(receipt["is_immutable"])
            self.assertEqual(len(runner.assets), receipt["asset_count"])
            verified_assets = [call for call in runner.calls if call[:3] == ("gh", "release", "verify-asset")]
            self.assertEqual(len(runner.assets), len(verified_assets))

    def test_stale_release_copy_blocks_inspect(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            asset_dir = make_fixture(root)
            (root / "CHANGELOG.md").write_text("## 0.3.6\n\nThe unreleased component set.\n", encoding="utf-8")
            runner = FakeRunner(self.promotion, asset_dir)
            with self.assertRaisesRegex(self.promotion.PromotionError, "promotion_stale_release_copy"):
                self.promotion.inspect_plan(
                    root=root,
                    asset_dir=asset_dir,
                    repository=REPOSITORY,
                    tag=TAG,
                    expected_commit=COMMIT,
                    runner=runner,
                )

    def test_remote_asset_drift_blocks_inspect(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            asset_dir = make_fixture(root)
            runner = FakeRunner(self.promotion, asset_dir)
            runner.assets[0]["digest"] = f"sha256:{'f' * 64}"
            with self.assertRaisesRegex(self.promotion.PromotionError, "promotion_remote_asset_mismatch"):
                self.promotion.inspect_plan(
                    root=root,
                    asset_dir=asset_dir,
                    repository=REPOSITORY,
                    tag=TAG,
                    expected_commit=COMMIT,
                    runner=runner,
                )

    def test_apply_rejects_a_stale_plan_before_publication(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            asset_dir = make_fixture(root)
            runner = FakeRunner(self.promotion, asset_dir)
            with self.assertRaisesRegex(self.promotion.PromotionError, "promotion_plan_stale"):
                self.promotion.apply_plan(
                    root=root,
                    asset_dir=asset_dir,
                    repository=REPOSITORY,
                    tag=TAG,
                    expected_commit=COMMIT,
                    plan_hash="f" * 64,
                    runner=runner,
                    wait=lambda _: None,
                )
            self.assertFalse(runner.published)

    def test_apply_fails_when_github_does_not_lock_the_release(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            asset_dir = make_fixture(root)
            runner = FakeRunner(self.promotion, asset_dir)
            inputs = {
                "root": root,
                "asset_dir": asset_dir,
                "repository": REPOSITORY,
                "tag": TAG,
                "expected_commit": COMMIT,
                "runner": runner,
            }
            plan = self.promotion.inspect_plan(**inputs)
            runner.immutable_after_publish = False
            with self.assertRaisesRegex(self.promotion.PromotionError, "promotion_publish_readback_mutable"):
                self.promotion.apply_plan(
                    **inputs,
                    plan_hash=plan["plan_hash"],
                    wait=lambda _: None,
                )


if __name__ == "__main__":
    unittest.main()
