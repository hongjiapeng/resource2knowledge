# -*- coding: utf-8 -*-
"""
Application-level settings loaded from environment / .env file.

Immutable after construction — per-run overrides go in RuntimeConfig.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class ProviderMode(str, Enum):
    """Execution mode for provider selection."""
    LOCAL = "local"
    CLOUD = "cloud"
    HYBRID = "hybrid"


def _env_bool(key: str, default: bool = False) -> bool:
    return os.getenv(key, str(default)).lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class AppSettings:
    """
    Global, immutable application settings derived from env vars.

    All paths resolve relative to ``project_dir``.
    """

    # ── Paths ──────────────────────────────────────────────
    project_dir: Path = field(default_factory=lambda: Path.cwd())

    @property
    def download_dir(self) -> Path:
        return self.project_dir / "downloads"

    @property
    def log_dir(self) -> Path:
        return self.project_dir / "logs"

    @property
    def checkpoint_dir(self) -> Path:
        return self.project_dir / "checkpoints"

    @property
    def output_dir(self) -> Path:
        return self.project_dir / "outputs"

    # ── Provider mode ──────────────────────────────────────
    provider_mode: ProviderMode = ProviderMode.LOCAL

    # ── Transcription ──────────────────────────────────────
    whisper_model: str = "medium"
    transcribe_language: str = "zh"

    # ── Summarization ──────────────────────────────────────
    llm_model: Optional[str] = None
    llm_model_fallback: Optional[str] = None

    # ── Cloud API ──────────────────────────────────────────
    openai_api_key: Optional[str] = None
    openai_base_url: Optional[str] = None
    openai_model: str = "gpt-4o-mini"
    openai_whisper_model: str = "whisper-1"

    # ── Storage / Notion ───────────────────────────────────
    notion_token: Optional[str] = None
    notion_database_id: Optional[str] = None
    disable_notion: bool = False

    # ── Feature flags ──────────────────────────────────────
    enable_transcript_cleaning: bool = True
    cleanup_audio: bool = True
    max_transcript_length: int = 5000

    # ── Logging ────────────────────────────────────────────
    log_level: str = "INFO"

    # ── Factory ────────────────────────────────────────────
    @classmethod
    def from_env(cls, project_dir: Optional[Path] = None) -> AppSettings:
        """Build settings from the current environment (and loaded .env)."""
        from dotenv import load_dotenv

        base = project_dir or Path.cwd()
        load_dotenv(base / ".env")

        mode_raw = os.getenv("PROVIDER_MODE", "local").lower()
        try:
            mode = ProviderMode(mode_raw)
        except ValueError:
            mode = ProviderMode.LOCAL

        return cls(
            project_dir=base,
            provider_mode=mode,
            whisper_model=os.getenv("WHISPER_MODEL", "medium"),
            transcribe_language=os.getenv("TRANSCRIBE_LANGUAGE", "zh"),
            llm_model=os.getenv("LLM_MODEL") or None,
            llm_model_fallback=os.getenv("LLM_MODEL_FALLBACK") or None,
            openai_api_key=os.getenv("OPENAI_API_KEY") or None,
            openai_base_url=os.getenv("OPENAI_BASE_URL") or None,
            openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            openai_whisper_model=os.getenv("OPENAI_WHISPER_MODEL", "whisper-1"),
            notion_token=os.getenv("NOTION_TOKEN") or None,
            notion_database_id=os.getenv("NOTION_DATABASE_ID") or None,
            disable_notion=_env_bool("DISABLE_NOTION"),
            enable_transcript_cleaning=_env_bool("ENABLE_TRANSCRIPT_CLEANING", default=True),
            cleanup_audio=not _env_bool("NO_CLEANUP_AUDIO"),
            max_transcript_length=int(os.getenv("MAX_TRANSCRIPT_LENGTH", "5000")),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        )
