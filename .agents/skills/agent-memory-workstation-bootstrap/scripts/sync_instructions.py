#!/usr/bin/env python3
"""Invoke instruction sync from the Core wheel in a Resolver-verified portable bundle.

This script deliberately does not install or import the user's ambient Core package.
The caller must first complete the existing immutable Release Resolver.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--portable-root", type=Path, required=True)
    args, remaining = parser.parse_known_args()
    root = args.portable_root
    try:
        resolution = json.loads((root.parent / "resolution.json").read_bytes())
        if resolution.get("status") != "verified" or resolution.get("portable_root") != root.name:
            raise ValueError("unverified resolution")
        wheels = list((root / "core").glob("*.whl"))
        if len(wheels) != 1 or wheels[0].is_symlink():
            raise ValueError("ambiguous Core wheel")
        portable_assets = [(name, metadata) for name, metadata in resolution["assets"].items()
                           if name.startswith("agent-memory-portable-") and name.endswith(".zip")]
        if len(portable_assets) != 1:
            raise ValueError("ambiguous portable archive")
        name, metadata = portable_assets[0]
        archive = root.parent / name
        if archive.name != name or archive.is_symlink():
            raise ValueError("unsafe archive")
        if hashlib.sha256(archive.read_bytes()).hexdigest() != metadata["sha256"]:
            raise ValueError("archive drift")
        with zipfile.ZipFile(archive) as bundle:
            if bundle.read("core/" + wheels[0].name) != wheels[0].read_bytes():
                raise ValueError("Core wheel drift")
    except (OSError, ValueError, KeyError, zipfile.BadZipFile):
        print(json.dumps({"status": "error", "error": "instruction_sync_release_unverified"}))
        return 1
    command = [sys.executable, "-I", "-B", "-c",
               "import sys; sys.path.insert(0, sys.argv.pop(1)); from agent_memory_sidecar.cli import main; raise SystemExit(main(sys.argv[1:]))",
               str(wheels[0].absolute()), "instructions", "sync", *remaining]
    return subprocess.run(command, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
