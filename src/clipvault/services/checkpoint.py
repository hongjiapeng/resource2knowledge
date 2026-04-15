# -*- coding: utf-8 -*-
"""
Checkpoint manager — save / restore pipeline state for resume.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Optional

from ..models.pipeline import PipelineResult, StepStatus


class CheckpointManager:
    """Persist and restore PipelineResult checkpoints by URL hash."""

    def __init__(self, checkpoint_dir: Path) -> None:
        self.dir = checkpoint_dir
        self.dir.mkdir(parents=True, exist_ok=True)

    def path_for(self, url: str) -> Path:
        h = hashlib.md5(url.encode()).hexdigest()[:8]
        return self.dir / f"{h}.json"

    def save(self, result: PipelineResult) -> None:
        path = self.path_for(result.url)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result.to_checkpoint(), f, ensure_ascii=False, indent=2)

    def load(self, url: str) -> Optional[PipelineResult]:
        """Load checkpoint for a URL. Returns the result regardless of status."""
        path = self.path_for(url)
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return PipelineResult.from_checkpoint(data)
        except (json.JSONDecodeError, KeyError):
            return None

    def is_completed(self, url: str) -> bool:
        """Check if a URL has been successfully processed."""
        result = self.load(url)
        return result is not None and result.status == StepStatus.SUCCESS

    def remove(self, url: str) -> None:
        path = self.path_for(url)
        if path.exists():
            path.unlink(missing_ok=True)
