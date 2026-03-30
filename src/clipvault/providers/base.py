# -*- coding: utf-8 -*-
"""
Abstract provider interfaces.

Every concrete provider implements one of these ABCs.
The pipeline never imports a concrete provider directly — it receives
providers through dependency injection (constructor or factory).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from ..models.resource import ResourceInput
from ..models.transcript import TranscriptResult
from ..models.summary import SummaryResult


# ── Download / Content Acquisition ────────────────────────


class Downloader(ABC):
    """Acquire content (audio, video, or text) from a URL."""

    @abstractmethod
    def download(self, resource: ResourceInput, *, force: bool = False) -> Dict[str, Any]:
        """
        Download or scrape content.

        Returns a dict with at least:
          - audio_path (str | None)
          - title (str)
          - platform (str)
          - content_type (str): "video" | "image_text"
        Extra keys are provider-specific and stored in ResourceInput.metadata.
        """

    @abstractmethod
    def cleanup(self, path: str) -> None:
        """Remove a temporary file created by download."""


# ── Transcription ─────────────────────────────────────────


class Transcriber(ABC):
    """Speech-to-text provider."""

    @abstractmethod
    def load(self, *, device: Optional[str] = None) -> None:
        """Pre-load the model (optional warm-up)."""

    @abstractmethod
    def transcribe(
        self,
        audio_path: str,
        *,
        language: Optional[str] = None,
        task: str = "transcribe",
    ) -> TranscriptResult:
        """Transcribe an audio file and return structured result."""

    @abstractmethod
    def unload(self) -> None:
        """Release model resources (VRAM, memory, handles)."""

    # Context-manager support (load / unload)
    def __enter__(self) -> Transcriber:
        self.load()
        return self

    def __exit__(self, *exc: object) -> None:
        self.unload()


# ── Summarization ─────────────────────────────────────────


class Summarizer(ABC):
    """Text summarization provider."""

    @abstractmethod
    def summarize(
        self,
        text: str,
        *,
        content_type: str = "video",
        max_length: int = 5000,
    ) -> SummaryResult:
        """Generate a structured summary from text."""

    @abstractmethod
    def check_available(self) -> bool:
        """Return True if the backend is reachable and ready."""

    def unload(self) -> None:  # noqa: B027
        """Release resources (optional — not all providers need this)."""


# ── Storage ───────────────────────────────────────────────


class StorageWriter(ABC):
    """Persist pipeline results to an external store."""

    @abstractmethod
    def write(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Write a result payload.

        Returns provider-specific metadata (e.g. page id, file path).
        """

    @abstractmethod
    def check_duplicate(self, url: str) -> bool:
        """Return True if the URL has already been stored."""

    def test_connection(self) -> bool:
        """Verify the backend is reachable. Default: True."""
        return True
