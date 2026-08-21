from __future__ import annotations

import importlib.util
import gzip
import io
import json
import os
import tarfile
import subprocess
import sys
import tempfile
import tomllib
import unittest
import zipfile
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
EXPORTER = ROOT / "scripts" / "build_public_export.py"
RELEASE_BUILDER = ROOT / "scripts" / "build_release_artifacts.py"
DOC_LINK_CHECKER = ROOT / "scripts" / "check_doc_links.py"
PRIVATE_EXPORT_TEMPLATE = ROOT / "templates" / "public" / "AGENTS.md"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class PublicDistributionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.exporter = load_module("public_export_builder", EXPORTER)
        cls.release = load_module("public_release_builder", RELEASE_BUILDER)
        cls.doc_links = load_module("public_doc_link_checker", DOC_LINK_CHECKER)
        cls.head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
            text=True, encoding="utf-8", check=True,
        ).stdout.strip()

    @unittest.skipUnless(PRIVATE_EXPORT_TEMPLATE.is_file(), "private engineering export source required")
    def test_allowlisted_export_excludes_private_history_and_injects_license(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            license_file = root / "selected-license.txt"
            license_file.write_text("Synthetic test license.\n", encoding="utf-8")
            output = root / "export"
            receipt = self.exporter.prepare_export(
                output=output,
                source_commit=self.head,
                repository_url="https://github.com/example/agent-memory-sidecar",
                license_expression="LicenseRef-Synthetic-Test",
                license_file=license_file,
                require_clean=False,
            )
            self.assertEqual("public_repository_commit_required", receipt["status"])
            self.assertEqual(self.head, receipt["source_commit"])
            self.assertTrue((output / "AGENTS.md").is_file())
            self.assertEqual(
                "* text=auto eol=lf",
                (output / ".gitattributes").read_text(encoding="utf-8").splitlines()[-1],
            )
            self.assertTrue((output / "LICENSE").is_file())
            self.assertTrue((output / "specs" / "public-authority-cutover-v1.md").is_file())
            self.assertTrue((output / "docs" / "decisions" / "0073-public-engineering-authority-cutover.zh.md").is_file())
            self.assertFalse((output / "docs/codex-desktop-hook-runtime-repro.md").exists())
            self.assertFalse((output / "specs/portable-global-instruction-source-v1.md").exists())
            pyproject = (output / "pyproject.toml").read_text(encoding="utf-8")
            self.assertIn('license = "LicenseRef-Synthetic-Test"', pyproject)
            self.assertIn('license-files = ["LICENSE"]', pyproject)
            readme = (output / "README.md").read_text(encoding="utf-8")
            self.assertNotIn("No open-source license has been selected yet", readme)
            self.assertIn("root `LICENSE` and `pyproject.toml` SPDX metadata", readme)
            agents = (output / "AGENTS.md").read_text(encoding="utf-8")
            self.assertNotRegex(agents, r"[A-Za-z]:[\\/]")
            for path in output.rglob("*"):
                if path.is_file():
                    self.assertNotIn(b"\r", path.read_bytes(), path.as_posix())
            self.exporter.scan_private_content(output)

    def test_public_text_normalization_is_checkout_independent(self) -> None:
        self.assertEqual(
            b"first\nsecond\nthird\n",
            self.exporter.normalize_public_text(
                b"first\r\nsecond\rthird\n",
                label="fixture.txt",
            ),
        )
        with self.assertRaisesRegex(self.exporter.ExportError, "public_export_binary_forbidden:fixture.bin"):
            self.exporter.normalize_public_text(b"prefix\x00suffix", label="fixture.bin")
        with self.assertRaisesRegex(self.exporter.ExportError, "public_export_binary_forbidden:fixture.bin"):
            self.exporter.normalize_public_text(b"prefix\xffsuffix", label="fixture.bin")

    def test_recursive_allowlist_is_independent_of_trailing_double_star_glob(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            nested = root / "nested"
            (nested / "child").mkdir(parents=True)
            (nested / "child" / "file.txt").write_text("selected", encoding="utf-8")
            (root / "template.txt").write_text("mapped", encoding="utf-8")
            specs = root / "specs"
            specs.mkdir()
            (specs / "public-export-allowlist-v1.json").write_text(
                json.dumps(
                    {
                        "contract_version": "public_export_allowlist_v1",
                        "copy": ["nested/**"],
                        "map": {"template.txt": "mapped.txt"},
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.object(Path, "glob", return_value=iter((nested,))):
                selected = self.exporter.resolve_files(root)
            self.assertEqual(
                {"nested/child/file.txt", "mapped.txt"},
                {path.as_posix() for path in selected.values()},
            )
            (specs / "public-export-allowlist-v1.json").write_text(
                json.dumps(
                    {
                        "contract_version": "public_export_allowlist_v1",
                        "copy": ["nested/**/file.txt"],
                        "map": {"template.txt": "mapped.txt"},
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                self.exporter.ExportError,
                "public_export_allowlist_invalid",
            ):
                self.exporter.resolve_files(root)

    def test_export_rejects_binary_private_literals_hardlinks_and_private_url_case(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            binary = root / "binary.txt"
            binary.write_bytes(b"safe\x00secret")
            with self.assertRaisesRegex(self.exporter.ExportError, "public_export_binary_forbidden"):
                self.exporter.scan_private_content(root)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            text = root / "text.txt"
            text.write_text("private-marker", encoding="utf-8")
            with self.assertRaisesRegex(self.exporter.ExportError, "private_literal"):
                self.exporter.scan_private_content(root, deny_literals=("private-marker",))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "first.txt"
            second = root / "second.txt"
            first.write_text("safe", encoding="utf-8")
            try:
                second.hardlink_to(first)
            except OSError as exc:
                self.skipTest(f"hard links unavailable: {exc}")
            with self.assertRaisesRegex(self.exporter.ExportError, "public_export_file_unsafe"):
                self.exporter.scan_private_content(root)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            physical = root / "physical"
            physical.mkdir()
            (physical / "outside.txt").write_text("outside", encoding="utf-8")
            alias = root / "alias"
            try:
                alias.symlink_to(physical, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"directory symbolic links unavailable: {exc}")
            with self.assertRaisesRegex(self.exporter.ExportError, "public_export_alias_forbidden"):
                self.exporter._assert_physical(root, alias / "outside.txt", regular_file=True)
            safe = root / "safe"
            safe.mkdir()
            (safe / "inside.txt").write_text("inside", encoding="utf-8")
            nested_alias = safe / "nested-alias"
            nested_alias.symlink_to(physical, target_is_directory=True)
            with self.assertRaisesRegex(self.exporter.ExportError, "public_export_alias_forbidden"):
                self.exporter.scan_private_content(safe)
            with self.assertRaisesRegex(self.release.ReleaseError, "release_alias_forbidden"):
                self.release._archive_files([safe], root)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            license_file = root / "license.txt"
            license_file.write_text("Synthetic test license.\n", encoding="utf-8")
            current_url = tomllib.loads(
                (ROOT / "pyproject.toml").read_text(encoding="utf-8")
            )["project"]["urls"]["Homepage"]
            case_variant = current_url.replace("https://github.com/", "https://GITHUB.COM/")
            with self.assertRaisesRegex(self.exporter.ExportError, "public_export_repository_url_invalid"):
                self.exporter.prepare_export(
                    output=root / "export",
                    source_commit=self.head,
                    repository_url=case_variant,
                    license_expression="MIT",
                    license_file=license_file,
                    require_clean=False,
                )

    def test_export_requires_real_license_file_and_new_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(
                self.exporter.ExportError,
                "public_export_license_missing",
            ):
                self.exporter.prepare_export(
                    output=root / "export",
                    source_commit=self.head,
                    repository_url="https://github.com/example/agent-memory-sidecar",
                    license_expression="MIT",
                    license_file=root / "missing",
                    require_clean=False,
                )

    def test_component_versions_and_release_boundaries_are_consistent(self) -> None:
        facts = self.release.version_facts(ROOT)
        self.assertEqual(
            {"core": "0.3.6", "plugin": "1.4.0", "bootstrap": "1.9.0", "scout": "5.6.0"},
            facts,
        )
        allowlist = json.loads(
            (ROOT / "specs/public-export-allowlist-v1.json").read_text(encoding="utf-8")
        )
        self.assertNotIn("AGENTS.md", allowlist["copy"])
        self.assertEqual("AGENTS.md", allowlist["map"]["templates/public/AGENTS.md"])

    def test_repo_and_plugin_anchor_are_byte_identical(self) -> None:
        repo_anchor = ROOT / ".agents" / "skills" / "agent-memory-bootstrap-anchor"
        plugin_anchor = ROOT / "plugins" / "agent-memory-sidecar" / "skills" / "agent-memory-bootstrap-anchor"
        repo_files = {
            path.relative_to(repo_anchor).as_posix(): path.read_bytes()
            for path in repo_anchor.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts
        }
        plugin_files = {
            path.relative_to(plugin_anchor).as_posix(): path.read_bytes()
            for path in plugin_anchor.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts
        }
        self.assertEqual(repo_files, plugin_files)

    def test_public_context_preserves_active_rationale_and_archive_boundary(self) -> None:
        decision = ROOT / "docs/decisions/0058-persistent-runtime-journal.zh.md"
        docs_index = (ROOT / "docs/README.md").read_text(encoding="utf-8")
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        active_documents = set(self.doc_links.ACTIVE_DOCUMENTS)

        self.assertTrue(decision.is_file())
        self.assertIn(decision, active_documents)
        self.assertLessEqual(
            set((ROOT / "docs/decisions").glob("*.md")),
            active_documents,
        )
        self.assertIn(ROOT / "specs/public-authority-cutover-v1.md", active_documents)
        self.assertIn("0058-persistent-runtime-journal.zh.md", docs_index)
        self.assertIn("冻结的私有工程归档", docs_index)
        self.assertIn("ADR 0052", docs_index)
        self.assertIn("ADR 0061", docs_index)
        self.assertIn("ADR 0062", docs_index)
        self.assertIn("cross-session key memory continuity", agents)
        self.assertIn("Historical archives can", agents)
        self.assertIn("real Codex Desktop new-task check", agents)

    @unittest.skipUnless(PRIVATE_EXPORT_TEMPLATE.is_file(), "private engineering export source required")
    def test_public_active_marker_requires_tracked_ancestral_release(self) -> None:
        repository_url = "https://github.com/example/agent-memory-sidecar"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            license_file = root / "selected-license.txt"
            license_file.write_text("Synthetic test license.\n", encoding="utf-8")
            public_root = root / "public"
            receipt = self.exporter.prepare_export(
                output=public_root,
                source_commit=self.head,
                repository_url=repository_url,
                license_expression="LicenseRef-Synthetic-Test",
                license_file=license_file,
                require_clean=False,
            )
            commands = (
                ["git", "init", "-b", "main"],
                ["git", "config", "user.name", "Public Authority Test"],
                ["git", "config", "user.email", "public-authority@example.invalid"],
                ["git", "add", "."],
                ["git", "commit", "-m", "Synthetic public snapshot"],
                ["git", "remote", "add", "origin", repository_url + ".git"],
                ["git", "tag", "v0.3.0"],
            )
            for command in commands:
                subprocess.run(command, cwd=public_root, check=True, capture_output=True)
            initial_commit = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=public_root, check=True,
                capture_output=True, text=True, encoding="utf-8",
            ).stdout.strip()
            marker = {
                "contract_version": "agent_memory_public_authority_v1",
                "status": "public_active",
                "repository": repository_url,
                "engineering_source_commit": receipt["source_commit"],
                "initial_public_release": {
                    "ref": "v0.3.0",
                    "commit": initial_commit,
                    "snapshot_sha256": receipt["source_snapshot_sha256"],
                },
                "activated_at": "2026-08-14T00:00:00Z",
            }
            marker_path = public_root / "PUBLIC_AUTHORITY.json"
            marker_path.write_text(json.dumps(marker), encoding="utf-8")
            with self.assertRaisesRegex(
                self.release.ReleaseError,
                "release_authority_marker_untracked",
            ):
                self.release.resolve_release_authority(
                    root=public_root,
                    repository_url=repository_url,
                    source_ref="v0.3.0",
                    commit=initial_commit,
                )
            subprocess.run(["git", "add", "PUBLIC_AUTHORITY.json"], cwd=public_root, check=True)
            subprocess.run(
                ["git", "commit", "-m", "Activate public authority"],
                cwd=public_root, check=True, capture_output=True,
            )
            active_commit = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=public_root, check=True,
                capture_output=True, text=True, encoding="utf-8",
            ).stdout.strip()
            authority = self.release.resolve_release_authority(
                root=public_root,
                repository_url=repository_url,
                source_ref="v0.3.1",
                commit=active_commit,
            )
            self.assertEqual("public_active", authority["authority_epoch"])
            self.assertEqual(initial_commit, authority["initial_public_release"]["commit"])
            marker["repository"] = "https://github.com/example/different-repository"
            marker_path.write_text(json.dumps(marker), encoding="utf-8")
            with self.assertRaises(self.release.ReleaseError):
                self.release.resolve_release_authority(
                    root=public_root,
                    repository_url=repository_url,
                    source_ref="v0.3.1",
                    commit=active_commit,
                )
            marker["repository"] = repository_url
            marker["initial_public_release"]["ref"] = "v9.9.9"
            marker["initial_public_release"]["commit"] = "f" * 40
            marker_path.write_text(json.dumps(marker), encoding="utf-8")
            with self.assertRaisesRegex(
                self.release.ReleaseError,
                "release_authority_initial_ref_unresolved",
            ):
                self.release.resolve_release_authority(
                    root=public_root,
                    repository_url=repository_url,
                    source_ref="v0.3.1",
                    commit=active_commit,
                )
            tree = subprocess.run(
                ["git", "rev-parse", "HEAD^{tree}"], cwd=public_root, check=True,
                capture_output=True, text=True, encoding="utf-8",
            ).stdout.strip()
            unrelated_commit = subprocess.run(
                ["git", "commit-tree", tree, "-m", "Unrelated release"],
                cwd=public_root, check=True, capture_output=True,
                text=True, encoding="utf-8",
            ).stdout.strip()
            subprocess.run(
                ["git", "tag", "v0.1.0", unrelated_commit],
                cwd=public_root, check=True, capture_output=True,
            )
            marker["initial_public_release"]["ref"] = "v0.1.0"
            marker["initial_public_release"]["commit"] = unrelated_commit
            marker_path.write_text(json.dumps(marker), encoding="utf-8")
            with self.assertRaisesRegex(
                self.release.ReleaseError,
                "release_authority_ancestry_invalid",
            ):
                self.release.resolve_release_authority(
                    root=public_root,
                    repository_url=repository_url,
                    source_ref="v0.3.1",
                    commit=active_commit,
                )

    def test_release_workflow_is_public_only_and_stops_at_complete_draft(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "release-artifacts.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("github.event.repository.visibility == 'public'", workflow)
        draft_create = workflow.index("gh release create")
        asset_upload = workflow.index("gh release upload")
        draft_readback = workflow.index("Keep release draft")
        draft_job = workflow.split("  draft-release:", 1)[1]
        self.assertLess(draft_job.index("actions/checkout@"), draft_job.index("gh release create"))
        self.assertLess(draft_create, asset_upload)
        self.assertLess(asset_upload, draft_readback)
        self.assertIn('= "true"', workflow)
        self.assertNotIn("gh release edit", workflow)
        self.assertNotIn("ADMIN_TOKEN", workflow)

    @unittest.skipIf((ROOT / "LICENSE").is_file(), "public checkout already has its selected license")
    def test_release_builder_fails_closed_without_selected_license(self) -> None:
        with self.assertRaisesRegex(
            self.release.ReleaseError,
            "release_source_dirty|release_license_missing",
        ):
            self.release.validate_release_source(root=ROOT)

    def test_sdist_normalization_is_reproducible(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = (root / "one.tar.gz", root / "two.tar.gz")
            for index, path in enumerate(paths):
                with path.open("wb") as raw:
                    with gzip.GzipFile(filename="source.tar", mode="wb", fileobj=raw, mtime=100 + index) as compressed:
                        with tarfile.open(fileobj=compressed, mode="w") as archive:
                            info = tarfile.TarInfo("package/file.txt")
                            payload = b"same bytes"
                            info.size = len(payload)
                            info.mtime = 200 + index
                            archive.addfile(info, io.BytesIO(payload))
                self.release.normalize_sdist(path, source_date_epoch=300)
            self.assertEqual(paths[0].read_bytes(), paths[1].read_bytes())

    def test_release_archive_prunes_untracked_noise_and_rejects_tracked_noise(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            cache = source / "__pycache__"
            cache.mkdir(parents=True)
            safe = source / "safe.py"
            safe.write_text("safe\n", encoding="utf-8")
            noise = cache / "safe.cpython-313.pyc"
            noise.write_bytes(b"ignored cache")
            log = source / "execution.log"
            log.write_text("ignored log\n", encoding="utf-8")

            archived = self.release._archive_files([source], root)
            self.assertEqual([safe], archived)

            subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, capture_output=True)
            subprocess.run(["git", "add", "--force", "."], cwd=root, check=True, capture_output=True)
            with self.assertRaisesRegex(
                self.release.ReleaseError,
                "release_tracked_noise_forbidden",
            ):
                self.release.validate_tracked_noise(root=root)

    @unittest.skipUnless(
        os.environ.get("AGENT_MEMORY_PUBLIC_RELEASE_SMOKE") == "1",
        "positive release smoke runs in its dedicated CI job",
    )
    def test_positive_public_release_lane(self) -> None:
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
        version = project["version"]
        source_ref = f"v{version}"

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            public_root = root / "public"
            if PRIVATE_EXPORT_TEMPLATE.is_file():
                repository_url = "https://github.com/example/agent-memory-sidecar"
                expected_authority_epoch = "private_engineering"
                license_file = root / "selected-license.txt"
                license_file.write_text("Synthetic test license.\n", encoding="utf-8")
                receipt = self.exporter.prepare_export(
                    output=public_root,
                    source_commit=self.head,
                    repository_url=repository_url,
                    license_expression="LicenseRef-Synthetic-Test",
                    license_file=license_file,
                    require_clean=False,
                )
                commands = (
                    ["git", "init", "-b", "main"],
                    ["git", "config", "user.name", "Public Lane Test"],
                    ["git", "config", "user.email", "public-lane@example.invalid"],
                    ["git", "add", "."],
                    ["git", "commit", "-m", "Synthetic public snapshot"],
                    ["git", "remote", "add", "origin", repository_url + ".git"],
                    ["git", "tag", source_ref],
                )
            else:
                repository_url = project["urls"]["Homepage"]
                expected_authority_epoch = "public_active"
                subprocess.run(
                    ["git", "clone", "--no-hardlinks", str(ROOT), str(public_root)],
                    check=True,
                    capture_output=True,
                )
                receipt = None
                commands = (
                    ["git", "remote", "set-url", "origin", repository_url + ".git"],
                    ["git", "tag", "--force", source_ref],
                )
            for command in commands:
                subprocess.run(command, cwd=public_root, check=True, capture_output=True)

            if (public_root / "PUBLIC_AUTHORITY.json").is_file():
                commit, _ = self.release.validate_release_source(root=public_root)
                authority = self.release.resolve_release_authority(
                    root=public_root,
                    repository_url=repository_url,
                    source_ref=source_ref,
                    commit=commit,
                )
                self.assertEqual("public_active", authority["authority_epoch"])
                receipt = {"source_commit": authority["engineering_source_commit"]}
            elif receipt is None:
                receipt = json.loads((public_root / "PUBLIC_EXPORT_RECEIPT.json").read_text(encoding="utf-8"))

            release_root = public_root / "dist" / "release"
            manifest = self.release.build(
                output=release_root,
                repository_url=repository_url,
                source_ref=source_ref,
                root=public_root,
            )
            self.assertEqual("public_artifact_verified", manifest["status"])
            self.assertEqual(receipt["source_commit"], manifest["source"]["engineering_source_commit"])
            self.assertEqual(expected_authority_epoch, manifest["source"]["authority_epoch"])
            self.assertTrue(all(manifest["verification"].values()))
            portable = release_root / f"agent-memory-portable-{version}.zip"
            self.assertTrue(portable.is_file())
            with zipfile.ZipFile(portable) as archive:
                self.assertIn(
                    ".agents/skills/global-owner-scout/scripts/prepare_delivery.py",
                    archive.namelist(),
                )
            for line in (release_root / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
                expected, relative = line.split("  ", 1)
                self.assertEqual(expected, self.release.digest(release_root / relative))


if __name__ == "__main__":
    unittest.main()
