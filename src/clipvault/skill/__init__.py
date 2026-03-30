# -*- coding: utf-8 -*-
"""
Skill / Agent adapter — headless, structured entry point.

This module provides the interface that VS Code skills, workflow
orchestrators, or future API endpoints should call.  It wraps
PipelineService with a pure-data contract (dicts in, dicts out)
and never touches stdout or interactive I/O.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, Optional, Set

from ..config.runtime import RuntimeConfig
from ..config.settings import AppSettings
from ..services.factory import create_pipeline_service
from ..services.pipeline import PipelineService


class SkillService:
    """
    Headless facade for agent / skill consumption.

    Usage from a skill::

        from clipvault.skill import SkillService

        svc = SkillService()
        result = svc.process("https://youtube.com/watch?v=xxx")
        # result is a plain dict — no side-effects
    """

    def __init__(
        self,
        settings: Optional[AppSettings] = None,
        pipeline: Optional[PipelineService] = None,
    ) -> None:
        self._settings = settings or AppSettings.from_env()
        self._pipeline = pipeline or create_pipeline_service(self._settings)

    def process(
        self,
        url: str,
        *,
        skip_steps: Optional[Set[str]] = None,
        language: Optional[str] = None,
        dry_run: bool = False,
        resume: bool = True,
        skip_storage: bool = False,
    ) -> Dict[str, Any]:
        """
        Run the full pipeline and return a flat dict result.

        This is the single method that skills / agents call.
        """
        rc = RuntimeConfig(
            skip_steps=skip_steps or set(),
            language=language,
            dry_run=dry_run,
            resume=resume,
            skip_storage=skip_storage,
        )

        result = self._pipeline.run(url, runtime=rc)
        return result.to_dict()

    def check_health(self) -> Dict[str, Any]:
        """Quick health check — useful for pre-flight validation."""
        checks: Dict[str, Any] = {
            "summarizer_available": False,
            "storage_available": False,
        }
        try:
            checks["summarizer_available"] = self._pipeline.summarizer.check_available()
        except Exception:
            pass
        try:
            if self._pipeline.storage:
                checks["storage_available"] = self._pipeline.storage.test_connection()
        except Exception:
            pass
        return checks
