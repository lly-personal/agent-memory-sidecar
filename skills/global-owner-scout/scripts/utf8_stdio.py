from __future__ import annotations

import sys
import os
from contextlib import contextmanager


def configure_utf8_stdio() -> None:
    """Keep the stdin/stdout contract deterministic across host locales."""
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="strict")


@contextmanager
def native_line_input():
    """Read one JSON line on an owned terminal without echo or line-size clipping."""
    if not sys.stdin.isatty():
        yield
        return
    if os.name == 'nt':
        import ctypes
        import msvcrt
        from ctypes import wintypes
        api = ctypes.WinDLL('kernel32', use_last_error=True)
        get_mode, set_mode = api.GetConsoleMode, api.SetConsoleMode
        get_mode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        get_mode.restype = wintypes.BOOL
        set_mode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        set_mode.restype = wintypes.BOOL
        handle = wintypes.HANDLE(msvcrt.get_osfhandle(sys.stdin.fileno()))
        previous = wintypes.DWORD()
        if not get_mode(handle, ctypes.byref(previous)):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            # Disable line input/echo only; keep processed input (including cancellation).
            if not set_mode(handle, previous.value & ~(0x2 | 0x4)):
                raise ctypes.WinError(ctypes.get_last_error())
            yield
        finally:
            if not set_mode(handle, previous.value):
                raise ctypes.WinError(ctypes.get_last_error())
    else:
        import signal
        import termios
        descriptor = sys.stdin.fileno()
        previous = termios.tcgetattr(descriptor)
        current = list(previous); current[6] = list(previous[6])
        current[3] &= ~(termios.ICANON | termios.ECHO)
        current[6][termios.VMIN], current[6][termios.VTIME] = 1, 0
        previous_handler = signal.getsignal(signal.SIGTERM)
        signal.signal(signal.SIGTERM, lambda signum, frame: sys.exit(128 + signum))
        try:
            termios.tcsetattr(descriptor, termios.TCSANOW, current)
            yield
        finally:
            try:
                termios.tcsetattr(descriptor, termios.TCSANOW, previous)
            finally:
                signal.signal(signal.SIGTERM, previous_handler)
