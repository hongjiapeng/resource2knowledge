# -*- coding: utf-8 -*-
"""Tests for provider factory wiring (local / cloud / hybrid)."""

from pathlib import Path

import pytest

from clipvault.config.settings import AppSettings, ProviderMode
from clipvault.services.factory import create_pipeline_service


class TestFactoryLocal:
    def test_local_mode_creates_service(self, tmp_path: Path):
        settings = AppSettings(
            project_dir=tmp_path,
            provider_mode=ProviderMode.LOCAL,
            disable_notion=True,
        )
        svc = create_pipeline_service(settings)
        assert svc is not None
        assert svc.transcriber is not None
        assert svc.summarizer is not None


class TestFactoryCloud:
    def test_cloud_mode_creates_transcriber(self, tmp_path: Path):
        settings = AppSettings(
            project_dir=tmp_path,
            provider_mode=ProviderMode.CLOUD,
            openai_api_key="sk-test-fake",
            disable_notion=True,
        )
        svc = create_pipeline_service(settings)
        # Should create OpenAI-based providers
        from clipvault.providers.transcription.openai_cloud import OpenAIWhisperTranscriber
        from clipvault.providers.summarization.openai_cloud import OpenAICloudSummarizer

        assert isinstance(svc.transcriber, OpenAIWhisperTranscriber)
        assert isinstance(svc.summarizer, OpenAICloudSummarizer)


class TestFactoryHybrid:
    def test_hybrid_mode_creates_hybrid_summarizer(self, tmp_path: Path):
        settings = AppSettings(
            project_dir=tmp_path,
            provider_mode=ProviderMode.HYBRID,
            openai_api_key="sk-test-fake",
            disable_notion=True,
        )
        svc = create_pipeline_service(settings)
        # Transcriber should be local (WhisperLocal)
        from clipvault.providers.transcription.whisper_local import WhisperLocalTranscriber

        assert isinstance(svc.transcriber, WhisperLocalTranscriber)
        # Summarizer should be the hybrid wrapper
        assert hasattr(svc.summarizer, "_primary")
        assert hasattr(svc.summarizer, "_fallback")
