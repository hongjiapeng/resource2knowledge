# -*- coding: utf-8 -*-
"""
Per-run configuration — mutable overrides on top of AppSettings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Set


@dataclass
class RuntimeConfig:
    """
    Per-invocation overrides.

    Passed into PipelineService.run() to control a single execution
    without mutating the global AppSettings.
    """

    # Steps to skip entirely
    skip_steps: Set[str] = field(default_factory=set)

    # Resume from the last checkpoint (default: True)
    resume: bool = True

    # Dry-run mode — validate inputs and plan but do not execute
    dry_run: bool = False

    # Force fresh download even if file exists
    force_download: bool = False

    # Override language for this run
    language: Optional[str] = None

    # Disable transcript cleaning for this run
    disable_cleaning: bool = False

    # Disable storage write for this run
    skip_storage: bool = False

    def should_skip(self, step_name: str) -> bool:
        return step_name in self.skip_steps
