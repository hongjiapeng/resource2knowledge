# -*- coding: utf-8 -*-
"""
Cloud transcription provider — OpenAI Whisper API.

Requires:
    pip install openai
    OPENAI_API_KEY set in environment / .env
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from ...models.transcript import TranscriptResult, TranscriptSegment
from ..base import Transcriber


class OpenAIWhisperTranscriber(Transcriber):
    """Transcribe audio via the OpenAI Whisper API (cloud)."""

    # Maximum file size the API accepts (25 MB)
    MAX_FILE_SIZE = 25 * 1024 * 1024

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "whisper-1",
        base_url: Optional[str] = None,
    ) -> None:
        self._api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self._model = model
        self._base_url = base_url or os.getenv("OPENAI_BASE_URL")
        self._client = None

    # ── Transcriber interface ─────────────────────────────

    def load(self, *, device: Optional[str] = None) -> None:
        """Initialise the OpenAI client (lazy)."""
        if self._client is not None:
            return
        try:
            from openai import OpenAI
        except ImportError:
            raise RuntimeError("openai package required: pip install openai")

        kwargs: dict = {"api_key": self._api_key}
        if self._base_url:
            kwargs["base_url"] = self._base_url
        self._client = OpenAI(**kwargs)

    def transcribe(
        self,
        audio_path: str,
        *,
        language: Optional[str] = None,
        task: str = "transcribe",
    ) -> TranscriptResult:
        if self._client is None:
            self.load()
        assert self._client is not None

        file_size = Path(audio_path).stat().st_size
        if file_size > self.MAX_FILE_SIZE:
            raise RuntimeError(
                f"Audio file too large for OpenAI API ({file_size / 1024 / 1024:.1f} MB > 25 MB). "
                "Consider splitting or using the local whisper provider."
            )

        with open(audio_path, "rb") as f:
            if task == "translate":
                resp = self._client.audio.translations.create(
                    model=self._model,
                    file=f,
                    response_format="verbose_json",
                )
            else:
                kwargs: dict = {
                    "model": self._model,
                    "file": f,
                    "response_format": "verbose_json",
                }
                if language:
                    kwargs["language"] = language
                resp = self._client.audio.transcriptions.create(**kwargs)

        # Parse the verbose_json response
        segments = []
        if hasattr(resp, "segments") and resp.segments:
            for seg in resp.segments:
                segments.append(TranscriptSegment(
                    start=seg.get("start", 0.0) if isinstance(seg, dict) else getattr(seg, "start", 0.0),
                    end=seg.get("end", 0.0) if isinstance(seg, dict) else getattr(seg, "end", 0.0),
                    text=(seg.get("text", "") if isinstance(seg, dict) else getattr(seg, "text", "")).strip(),
                ))

        text = resp.text if hasattr(resp, "text") else str(resp)
        duration = getattr(resp, "duration", 0.0) or 0.0
        detected_lang = getattr(resp, "language", language or "unknown")

        return TranscriptResult(
            text=text.strip(),
            segments=segments,
            language=detected_lang,
            duration=duration,
            device="cloud/openai",
        )

    def unload(self) -> None:
        self._client = None
