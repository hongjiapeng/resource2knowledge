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
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name)
        if isinstance(stream, io.TextIOWrapper):
            if stream.encoding and stream.encoding.lower().replace("-", "") == "utf8":
                continue
            # Re-wrap with UTF-8 — flush first to avoid data loss
            stream.flush()
            setattr(
                sys, name,
                io.TextIOWrapper(
                    stream.buffer, encoding="utf-8", errors="replace",
                ),
            )
        else:
            setattr(
                sys, name,
                io.TextIOWrapper(
                    stream.buffer, encoding="utf-8", errors="replace",
                ),
            )
