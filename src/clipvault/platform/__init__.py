# -*- coding: utf-8 -*-
"""
Platform abstraction layer.

Collects all OS-specific workarounds into a single place so the rest
of the codebase stays platform-agnostic.
"""

from __future__ import annotations

import io
import sys


def fix_encoding() -> None:
    """Ensure UTF-8 stdout/stderr on Windows."""
    if sys.platform != "win32":
        return
    if not isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace"
        )
    if not isinstance(sys.stderr, io.TextIOWrapper):
        sys.stderr = io.TextIOWrapper(
            sys.stderr.buffer, encoding="utf-8", errors="replace"
        )
