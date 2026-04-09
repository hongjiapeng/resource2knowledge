# -*- coding: utf-8 -*-
"""
Thin CLI entry point.

All business logic lives in PipelineService / SkillService.
This module only handles argument parsing and human-readable output.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import torch

from ..config.settings import AppSettings
from ..config.runtime import RuntimeConfig
from ..platform import fix_encoding
from ..services.factory import create_pipeline_service


def _setup_logging(settings: AppSettings, level: str) -> logging.Logger:
    settings.log_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("clipvault")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    fh = logging.FileHandler(settings.log_dir / f"pipeline_{stamp}.log", encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))

    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger


def _log_runtime_environment(logger: logging.Logger, project_dir: Path) -> None:
    """Log interpreter, torch, and CUDA info; warn if not using project venv."""
    current_exe = Path(sys.executable).resolve()
    expected_venv = (project_dir / "venv" / "Scripts" / "python.exe").resolve()

    logger.info(
        "Runtime environment: executable=%s, torch=%s, cuda_available=%s",
        current_exe, torch.__version__, torch.cuda.is_available(),
    )

    if current_exe != expected_venv:
        logger.warning(
            "Current interpreter is not the project venv. "
            "expected=%s current=%s",
            expected_venv, current_exe,
        )
        if not torch.cuda.is_available() and "cpu" in torch.__version__:
            logger.warning(
                "PyTorch is CPU-only (%s). Whisper will run on CPU "
                "(very slow). Use the venv python to get CUDA support.",
                torch.__version__,
            )
    elif not torch.cuda.is_available():
        logger.warning(
            "Running from project venv but CUDA is not available "
            "(torch=%s). Whisper will fall back to CPU.",
            torch.__version__,
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="clipvault",
        description="ClipVault — Turn online content into knowledge",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  clipvault "https://www.youtube.com/watch?v=xxx"
  clipvault "https://bilibili.com/video/xxx" --log-level DEBUG
  clipvault "https://example.com/video" --skip transcribe
  clipvault "https://example.com/video" --dry-run
""",
    )

    parser.add_argument("url", nargs="?", help="Resource URL to process")

    parser.add_argument(
        "--skip",
        nargs="*",
        default=[],
        metavar="STEP",
        help="Steps to skip: download, transcribe, summarize, store",
    )
    parser.add_argument("--skip-notion", action="store_true", help="Skip Notion storage")
    parser.add_argument("--disable-cleaning", action="store_true", help="Disable transcript cleaning")
    parser.add_argument("--no-cleanup", action="store_true", help="Keep downloaded audio files")
    parser.add_argument("--no-resume", action="store_true", help="Ignore checkpoints, start fresh")
    parser.add_argument("--dry-run", action="store_true", help="Validate inputs only, do not execute")
    parser.add_argument("--force-download", action="store_true", help="Re-download even if file exists")
    parser.add_argument("--language", default=None, help="Override transcription language")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log level",
    )
    parser.add_argument("--json", action="store_true", dest="json_output", help="Output raw JSON only")

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    fix_encoding()

    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.url:
        parser.print_help()
        return 1

    # Build settings
    project_dir = Path(__file__).resolve().parents[3]  # src/clipvault/cli -> project root
    settings = AppSettings.from_env(project_dir=project_dir)

    logger = _setup_logging(settings, args.log_level)

    # Log runtime environment for debugging
    _log_runtime_environment(logger, project_dir)

    # Build runtime config
    skip = set(args.skip)
    if args.skip_notion:
        skip.add("store")

    rc = RuntimeConfig(
        skip_steps=skip,
        resume=not args.no_resume,
        dry_run=args.dry_run,
        force_download=args.force_download,
        language=args.language,
        disable_cleaning=args.disable_cleaning,
        skip_storage="store" in skip,
    )

    pipeline = create_pipeline_service(settings)

    # Separate pipeline execution from output display so that
    # a print/encoding error does not mask a successful pipeline
    # and cause the caller (agent) to retry indefinitely.
    try:
        result = pipeline.run(args.url, runtime=rc)
    except Exception as exc:
        if args.json_output:
            print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        else:
            logger.error("Pipeline failed: %s", exc)
        return 1

    try:
        if args.json_output:
            print(result.to_json())
        else:
            print()
            print("=" * 50)
            print(f"  Status:   {result.status.value}")
            if result.title:
                print(f"  Title:    {result.title}")
            if result.elapsed_seconds:
                print(f"  Elapsed:  {result.elapsed_seconds:.1f}s")
            print("=" * 50)
            print()
            print(result.to_json())
    except Exception as exc:
        logger.error("Failed to display result: %s", exc)

    return 0
