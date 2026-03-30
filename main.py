# -*- coding: utf-8 -*-
"""
🌐 ClipVault Main Entry — Legacy Wrapper

This file preserves backward compatibility with `python main.py <url>`.
All logic now lives in the ``clipvault`` package under ``src/``.

Usage (unchanged):
    python main.py "https://www.youtube.com/watch?v=xxx"
    python main.py "https://bilibili.com/video/xxx" --skip-summary

For the new CLI:
    python -m clipvault "https://www.youtube.com/watch?v=xxx"
    clipvault "https://www.youtube.com/watch?v=xxx"
"""

import sys
from pathlib import Path

# Ensure the src/ directory is importable when running `python main.py` directly
_src = Path(__file__).parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from clipvault.platform import fix_encoding
fix_encoding()

from clipvault.cli import main as _cli_main


# ── backward-compatible argument translation ──────────────

def _translate_argv() -> list[str]:
    """
    Translate the old CLI flags to the new clipvault format so existing
    scripts and muscle-memory keep working.

    Old → New:
      --skip-transcribe  →  --skip transcribe
      --skip-summary     →  --skip summarize
      --skip-notion      →  --skip-notion  (unchanged)
      --no-cleanup       →  --no-cleanup   (unchanged)
      --no-resume        →  --no-resume    (unchanged)
      --disable-cleaning →  --disable-cleaning (unchanged)
      --log-level X      →  --log-level X  (unchanged)
    """
    raw = sys.argv[1:]
    translated: list[str] = []
    skip_set: list[str] = []
    i = 0
    while i < len(raw):
        arg = raw[i]
        if arg == "--skip-transcribe":
            skip_set.append("transcribe")
        elif arg == "--skip-summary":
            skip_set.append("summarize")
        else:
            translated.append(arg)
        i += 1

    if skip_set:
        translated = ["--skip"] + skip_set + translated
    return translated


def main():
    argv = _translate_argv()
    sys.exit(_cli_main(argv))


if __name__ == "__main__":
    main()
