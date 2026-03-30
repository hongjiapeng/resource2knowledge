# -*- coding: utf-8 -*-
"""
Local Whisper transcription provider (faster-whisper).
"""

from __future__ import annotations

import gc
import logging
from typing import Optional

import torch

from ...models.transcript import TranscriptResult, TranscriptSegment
from ..base import Transcriber

logger = logging.getLogger("clipvault.transcription")


class WhisperLocalTranscriber(Transcriber):
    """Local faster-whisper transcriber with CUDA/CPU auto-detection."""

    def __init__(
        self,
        model_size: str = "medium",
        compute_type: Optional[str] = None,
        download_root: Optional[str] = None,
    ) -> None:
        self.model_size = model_size
        self._compute_type_override = compute_type
        self.download_root = download_root
        self._model = None
        self._device: Optional[str] = None

    # ── Transcriber interface ─────────────────────────────

    def load(self, *, device: Optional[str] = None) -> None:
        if self._model is not None:
            return

        import platform as platmod
        from faster_whisper import WhisperModel

        if device is None:
            if torch.cuda.is_available():
                device = "cuda"
            elif platmod.system() == "Darwin" and platmod.machine() == "arm64":
                device = "cpu"
            else:
                device = "cpu"

        compute_type = self._compute_type_override
        if compute_type is None:
            compute_type = "float16" if device == "cuda" else "int8"

        self._device = device
        self._model = WhisperModel(
            self.model_size,
            device=device,
            compute_type=compute_type,
            download_root=self.download_root,
        )
        logger.info("Whisper model loaded: size=%s, device=%s, compute_type=%s", self.model_size, device, compute_type)

    def transcribe(
        self,
        audio_path: str,
        *,
        language: Optional[str] = None,
        task: str = "transcribe",
    ) -> TranscriptResult:
        if self._model is None:
            self.load()

        lang = language or "zh"
        segments_iter, info = self._model.transcribe(
            audio_path,
            language=lang,
            task=task,
            beam_size=5,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
        )

        segments = []
        texts = []
        for seg in segments_iter:
            text = seg.text.strip()
            segments.append(TranscriptSegment(start=seg.start, end=seg.end, text=text))
            texts.append(text)

        return TranscriptResult(
            text=" ".join(texts),
            segments=segments,
            language=getattr(info, "language", lang),
            duration=getattr(info, "duration", 0.0),
            device=self._device,
        )

    def unload(self) -> None:
        if self._model is not None:
            del self._model
            self._model = None
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.synchronize()
            self._device = None
