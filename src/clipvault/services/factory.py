# -*- coding: utf-8 -*-
"""
Factory — wire up providers according to AppSettings.

This is the single composition root: the only file that knows about
concrete provider classes.
"""

from __future__ import annotations

import logging
from typing import Optional

from ..config.settings import AppSettings, ProviderMode
from ..providers.base import Downloader, StorageWriter, Summarizer, Transcriber
from .checkpoint import CheckpointManager
from .pipeline import PipelineService

logger = logging.getLogger("clipvault.factory")


def _build_downloader(settings: AppSettings) -> Downloader:
    from ..providers.download.ytdlp import YtdlpDownloader

    return YtdlpDownloader(output_dir=settings.download_dir)


def _build_transcriber(settings: AppSettings) -> Transcriber:
    mode = settings.provider_mode

    if mode == ProviderMode.CLOUD:
        from ..providers.transcription.openai_cloud import OpenAIWhisperTranscriber

        return OpenAIWhisperTranscriber(
            api_key=settings.openai_api_key,
            model=settings.openai_whisper_model,
            base_url=settings.openai_base_url,
        )

    # LOCAL and HYBRID both use local whisper
    # (HYBRID can optionally fall back to cloud in the future)
    from ..providers.transcription.whisper_local import WhisperLocalTranscriber

    return WhisperLocalTranscriber(model_size=settings.whisper_model)


def _build_summarizer(settings: AppSettings) -> Summarizer:
    mode = settings.provider_mode

    if mode == ProviderMode.CLOUD:
        from ..providers.summarization.openai_cloud import OpenAICloudSummarizer

        return OpenAICloudSummarizer(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            base_url=settings.openai_base_url,
        )

    if mode == ProviderMode.HYBRID:
        # HYBRID: try local first, wrap with cloud fallback
        from ..providers.summarization.ollama_local import OllamaLocalSummarizer
        from ..providers.summarization.openai_cloud import OpenAICloudSummarizer

        local = OllamaLocalSummarizer(
            model=settings.llm_model,
            model_fallback=settings.llm_model_fallback,
        )
        cloud = OpenAICloudSummarizer(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            base_url=settings.openai_base_url,
        )
        return _HybridSummarizer(primary=local, fallback=cloud)

    # LOCAL
    from ..providers.summarization.ollama_local import OllamaLocalSummarizer

    return OllamaLocalSummarizer(
        model=settings.llm_model,
        model_fallback=settings.llm_model_fallback,
    )


def _build_storage(settings: AppSettings) -> Optional[StorageWriter]:
    if settings.disable_notion:
        from ..providers.storage.json_local import JsonStorageWriter

        return JsonStorageWriter(output_dir=settings.output_dir)

    if settings.notion_token and settings.notion_database_id:
        try:
            from ..providers.storage.notion import NotionStorageWriter

            writer = NotionStorageWriter(
                token=settings.notion_token,
                database_id=settings.notion_database_id,
            )
            if writer.test_connection():
                return writer
            else:
                logger.warning("Notion connection failed — falling back to local JSON")
        except Exception as exc:
            logger.warning("Notion init failed: %s — falling back to local JSON", exc)

    from ..providers.storage.json_local import JsonStorageWriter

    return JsonStorageWriter(output_dir=settings.output_dir)


def create_pipeline_service(settings: Optional[AppSettings] = None) -> PipelineService:
    """
    Assemble a fully-wired PipelineService from settings.

    This is the recommended way to create a pipeline — both CLI
    and skill adapter call this function.
    """
    if settings is None:
        settings = AppSettings.from_env()

    return PipelineService(
        settings=settings,
        downloader=_build_downloader(settings),
        transcriber=_build_transcriber(settings),
        summarizer=_build_summarizer(settings),
        storage=_build_storage(settings),
        checkpoint_mgr=CheckpointManager(settings.checkpoint_dir),
    )


# ── Hybrid wrapper ────────────────────────────────────────


class _HybridSummarizer(Summarizer):
    """Try the primary (local) summarizer; fall back to secondary (cloud) on failure."""

    def __init__(self, primary: Summarizer, fallback: Summarizer) -> None:
        self._primary = primary
        self._fallback = fallback

    def check_available(self) -> bool:
        return self._primary.check_available() or self._fallback.check_available()

    def summarize(self, text: str, *, content_type: str = "video", max_length: int = 5000):
        try:
            if self._primary.check_available():
                return self._primary.summarize(text, content_type=content_type, max_length=max_length)
        except Exception as exc:
            logger.warning("Primary (local) summarizer failed: %s — trying cloud fallback", exc)

        return self._fallback.summarize(text, content_type=content_type, max_length=max_length)

    def unload(self) -> None:
        self._primary.unload()
        self._fallback.unload()
