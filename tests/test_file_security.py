from __future__ import annotations

import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_memory_sidecar.errors import CoreError
from agent_memory_sidecar.file_security import hold_physical_directory
from agent_memory_sidecar.instructions import atomic_write


class PhysicalDirectoryHoldTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "posix", "POSIX directory descriptors")
    def test_relative_atomic_creation_refusal_does_not_remove_unowned_file(self) -> None:
        with tempfile.TemporaryDirectory() as fixture:
            target = Path(fixture) / "config.json"
            target.write_bytes(b"retain")
            with hold_physical_directory(target.parent) as descriptor:
                with patch.object(os, "open", side_effect=PermissionError("fixture exclusive creation refused")):
                    with self.assertRaises(CoreError) as caught:
                        atomic_write(target, b"replacement", directory_fd=descriptor)
            self.assertEqual("instruction_write_failed", caught.exception.code)
            self.assertEqual(b"retain", target.read_bytes())
            self.assertEqual([target], list(target.parent.iterdir()))

    def test_hold_preserves_access_and_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as fixture:
            home = Path(fixture) / "home"
            home.mkdir(mode=0o750)
            before = home.stat()
            acl_before = (
                subprocess.check_output(["icacls", str(home)])
                if os.name == "nt" else None
            )
            with hold_physical_directory(home) as descriptor:
                (home / "child").write_bytes(b"content")
                (home / "child").rename(home / "renamed")
                self.assertEqual((home / "renamed").read_bytes(), b"content")
                (home / "renamed").unlink()
                if os.name == "nt":
                    self.assertIsNone(descriptor)
                else:
                    self.assertEqual(os.fstat(descriptor).st_ino, before.st_ino)
            if os.name == "nt":
                self.assertEqual(
                    subprocess.check_output(["icacls", str(home)]), acl_before,
                )
            else:
                self.assertEqual(
                    stat.S_IMODE(home.stat().st_mode), stat.S_IMODE(before.st_mode),
                )
                with self.assertRaises(OSError):
                    os.fstat(descriptor)
            home.rename(home.with_name("released"))

    def test_missing_directory_and_regular_file_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as fixture:
            root = Path(fixture)
            regular = root / "file"
            regular.write_bytes(b"keep")
            for path in (root / "missing", regular):
                with self.subTest(path=path.name):
                    with self.assertRaises(CoreError) as raised:
                        with hold_physical_directory(path):
                            self.fail("unsafe directory was yielded")
                    self.assertEqual(raised.exception.code, "store_unsafe")
            self.assertEqual(regular.read_bytes(), b"keep")
            self.assertFalse((root / "missing").exists())

    def test_directory_symlink_and_symlink_ancestor_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as fixture:
            root = Path(fixture)
            physical = root / "physical"
            (physical / "nested").mkdir(parents=True)
            alias = root / "alias"
            try:
                alias.symlink_to(physical, target_is_directory=True)
            except OSError:
                self.skipTest("directory symlink creation is unavailable")
            for path in (alias, alias / "nested"):
                with self.subTest(path=path.name):
                    with self.assertRaises(CoreError) as raised:
                        with hold_physical_directory(path):
                            self.fail("directory alias was yielded")
                    self.assertEqual(raised.exception.code, "store_unsafe")

    @unittest.skipUnless(os.name == "posix", "POSIX directory descriptors")
    def test_relative_operations_survive_directory_or_ancestor_replacement(self) -> None:
        for replace_ancestor in (False, True):
            with self.subTest(replace_ancestor=replace_ancestor):
                with tempfile.TemporaryDirectory() as fixture:
                    root = Path(fixture)
                    parent = root / "parent"
                    home = parent / "home"
                    home.mkdir(parents=True)
                    (home / "target").write_bytes(b"approved")
                    with hold_physical_directory(home) as descriptor:
                        original = parent if replace_ancestor else home
                        original.rename(root / "moved")
                        home.mkdir(parents=True)
                        (home / "target").write_bytes(b"new user file")
                        os.rename(
                            "target", "captured",
                            src_dir_fd=descriptor, dst_dir_fd=descriptor,
                        )
                    moved_home = (
                        root / "moved" / "home" if replace_ancestor else root / "moved"
                    )
                    self.assertEqual((moved_home / "captured").read_bytes(), b"approved")
                    self.assertEqual((home / "target").read_bytes(), b"new user file")

    def test_body_error_propagates_and_releases_directory(self) -> None:
        with tempfile.TemporaryDirectory() as fixture:
            home = Path(fixture) / "home"
            home.mkdir()
            failure = RuntimeError("caller failure")
            with self.assertRaises(RuntimeError) as raised:
                with hold_physical_directory(home) as descriptor:
                    raise failure
            self.assertIs(raised.exception, failure)
            if descriptor is not None:
                with self.assertRaises(OSError):
                    os.fstat(descriptor)
            home.rename(home.with_name("released"))

    @unittest.skipUnless(os.name == "nt", "Windows directory sharing")
    def test_windows_prevents_directory_and_ancestor_rename_until_exit(self) -> None:
        with tempfile.TemporaryDirectory() as fixture:
            parent = Path(fixture) / "parent"
            home = parent / "home"
            home.mkdir(parents=True)
            with hold_physical_directory(home):
                for source in (home, parent):
                    destination = source.with_name("moved")
                    try:
                        source.rename(destination)
                    except OSError:
                        continue
                    destination.rename(source)
                    self.fail("held directory or ancestor could be renamed")
            home.rename(home.with_name("released"))
            parent.rename(parent.with_name("released"))

    @unittest.skipUnless(os.name == "nt", "Windows junction rejection")
    def test_windows_rejects_directory_junction(self) -> None:
        with tempfile.TemporaryDirectory() as fixture:
            root = Path(fixture)
            physical = root / "physical"
            physical.mkdir()
            (physical / "retained").write_bytes(b"keep")
            junction = root / "junction"
            subprocess.run(
                ["cmd", "/d", "/c", "mklink", "/J", str(junction), str(physical)],
                check=True, capture_output=True,
            )
            try:
                with self.assertRaises(CoreError) as raised:
                    with hold_physical_directory(junction):
                        self.fail("junction was yielded")
                self.assertEqual(raised.exception.code, "store_unsafe")
                self.assertEqual((physical / "retained").read_bytes(), b"keep")
            finally:
                junction.rmdir()


if __name__ == "__main__":
    unittest.main()
