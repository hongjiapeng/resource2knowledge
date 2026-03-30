# -*- coding: utf-8 -*-
"""Tests for the skill service."""

from clipvault.config.settings import AppSettings
from clipvault.services.pipeline import PipelineService
from clipvault.services.checkpoint import CheckpointManager
from clipvault.skill import SkillService


def _make_skill(tmp_path, downloader, transcriber, summarizer, storage):
    settings = AppSettings(project_dir=tmp_path)
    pipeline = PipelineService(
        settings=settings,
        downloader=downloader,
        transcriber=transcriber,
        summarizer=summarizer,
        storage=storage,
        checkpoint_mgr=CheckpointManager(tmp_path / "checkpoints"),
    )
    return SkillService(settings=settings, pipeline=pipeline)


class TestSkillService:
    def test_process_returns_dict(
        self, tmp_path, stub_downloader, stub_transcriber, stub_summarizer, stub_storage
    ):
        svc = _make_skill(tmp_path, stub_downloader, stub_transcriber, stub_summarizer, stub_storage)
        result = svc.process("https://www.youtube.com/watch?v=skill_test")

        assert isinstance(result, dict)
        assert result["status"] == "success"
        assert result["platform"] == "YouTube"
        assert "summary" in result

    def test_dry_run(
        self, tmp_path, stub_downloader, stub_transcriber, stub_summarizer, stub_storage
    ):
        svc = _make_skill(tmp_path, stub_downloader, stub_transcriber, stub_summarizer, stub_storage)
        result = svc.process("https://www.youtube.com/watch?v=dry", dry_run=True)

        assert result["status"] == "skipped"
        assert result["metadata"]["dry_run"] is True

    def test_skip_steps(
        self, tmp_path, stub_downloader, stub_transcriber, stub_summarizer, stub_storage
    ):
        svc = _make_skill(tmp_path, stub_downloader, stub_transcriber, stub_summarizer, stub_storage)
        result = svc.process(
            "https://www.youtube.com/watch?v=skip",
            skip_steps={"summarize", "store"},
        )
        assert result["status"] == "success"
        # Summarize step should be skipped
        summarize_step = next((s for s in result["steps"] if s["name"] == "summarize"), None)
        assert summarize_step is not None
        assert summarize_step["status"] == "skipped"

    def test_health_check(
        self, tmp_path, stub_downloader, stub_transcriber, stub_summarizer, stub_storage
    ):
        svc = _make_skill(tmp_path, stub_downloader, stub_transcriber, stub_summarizer, stub_storage)
        health = svc.check_health()
        assert "summarizer_available" in health
        assert health["summarizer_available"] is True
