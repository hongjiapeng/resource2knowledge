# -*- coding: utf-8 -*-
"""Shared test fixtures."""

from pathlib import Path
from typing import Any, Dict, Optional

import pytest

from clipvault.config.settings import AppSettings
from clipvault.models.resource import ResourceInput
from clipvault.models.summary import SummaryResult
from clipvault.models.transcript import TranscriptResult
from clipvault.providers.base import Downloader, StorageWriter, Summarizer, Transcriber


# ── Stub providers for unit tests ─────────────────────────


class StubDownloader(Downloader):
    def __init__(self, title: str = "Test Video") -> None:
        self._title = title
        self.cleaned: list[str] = []

    def download(self, resource: ResourceInput, *, force: bool = False) -> Dict[str, Any]:
        return {
            "audio_path": "/tmp/test.m4a",
            "platform": resource.platform.value,
            "title": self._title,
            "url": resource.url,
            "content_type": "video",
        }

    def cleanup(self, path: str) -> None:
        self.cleaned.append(path)


class StubTranscriber(Transcriber):
    def __init__(self, text: str = "这是测试转录文本") -> None:
        self._text = text
        self._loaded = False

    def load(self, *, device: Optional[str] = None) -> None:
        self._loaded = True

    def transcribe(self, audio_path: str, *, language: Optional[str] = None, task: str = "transcribe") -> TranscriptResult:
        return TranscriptResult(text=self._text, language=language or "zh", duration=60.0, device="cpu")

    def unload(self) -> None:
        self._loaded = False


class StubSummarizer(Summarizer):
    def summarize(self, text: str, *, content_type: str = "video", max_length: int = 5000) -> SummaryResult:
        return SummaryResult(
            summary="测试摘要",
            key_points=["要点1", "要点2"],
            tags=["测试"],
            category="测试分类",
        )

    def check_available(self) -> bool:
        return True


class StubStorage(StorageWriter):
    def __init__(self) -> None:
        self.pages: list[dict] = []

    def write(self, data: Dict[str, Any]) -> Dict[str, Any]:
        self.pages.append(data)
        return {"id": f"mock-{len(self.pages)}"}

    def check_duplicate(self, url: str) -> bool:
        return any(p.get("url") == url for p in self.pages)


# ── Fixtures ──────────────────────────────────────────────


@pytest.fixture
def tmp_settings(tmp_path: Path) -> AppSettings:
    return AppSettings(project_dir=tmp_path)


@pytest.fixture
def stub_downloader() -> StubDownloader:
    return StubDownloader()


@pytest.fixture
def stub_transcriber() -> StubTranscriber:
    return StubTranscriber()


@pytest.fixture
def stub_summarizer() -> StubSummarizer:
    return StubSummarizer()


@pytest.fixture
def stub_storage() -> StubStorage:
    return StubStorage()
