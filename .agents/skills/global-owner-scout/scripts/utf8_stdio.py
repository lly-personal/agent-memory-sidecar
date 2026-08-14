from __future__ import annotations

import sys


def configure_utf8_stdio() -> None:
    """Keep the stdin/stdout contract deterministic across host locales."""
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="strict")
