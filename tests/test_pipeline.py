# -*- coding: utf-8 -*-
"""Tests for the pipeline service (all providers stubbed)."""

from pathlib import Path

from clipvault.config.runtime import RuntimeConfig
from clipvault.config.settings import AppSettings
from clipvault.models.pipeline import PipelineResult, StepStatus
from clipvault.services.checkpoint import CheckpointManager
from clipvault.services.pipeline import PipelineService


def _make_service(tmp_path, downloader, transcriber, summarizer, storage):
    settings = AppSettings(project_dir=tmp_path)
    return PipelineService(
        settings=settings,
        downloader=downloader,
        transcriber=transcriber,
        summarizer=summarizer,
        storage=storage,
        checkpoint_mgr=CheckpointManager(tmp_path / "checkpoints"),
    )


class TestPipelineService:
    def test_full_pipeline(
        self, tmp_path, stub_downloader, stub_transcriber, stub_summarizer, stub_storage
    ):
        svc = _make_service(tmp_path, stub_downloader, stub_transcriber, stub_summarizer, stub_storage)
        result = svc.run("https://www.youtube.com/watch?v=test")

        assert result.status == StepStatus.SUCCESS
        assert result.title == "Test Video"
        assert result.transcript is not None
        assert result.summary is not None
        assert result.summary.summary == "测试摘要"
        assert len(stub_storage.pages) == 1

    def test_skip_summarize(
        self, tmp_path, stub_downloader, stub_transcriber, stub_summarizer, stub_storage
    ):
        svc = _make_service(tmp_path, stub_downloader, stub_transcriber, stub_summarizer, stub_storage)
        rc = RuntimeConfig(skip_steps={"summarize"})
        result = svc.run("https://www.youtube.com/watch?v=test", runtime=rc)

        assert result.status == StepStatus.SUCCESS
        assert result.summary is None

    def test_dry_run(
        self, tmp_path, stub_downloader, stub_transcriber, stub_summarizer, stub_storage
    ):
        svc = _make_service(tmp_path, stub_downloader, stub_transcriber, stub_summarizer, stub_storage)
        rc = RuntimeConfig(dry_run=True)
        result = svc.run("https://www.youtube.com/watch?v=test", runtime=rc)

        assert result.status == StepStatus.SKIPPED
        assert result.metadata.get("dry_run") is True
        assert len(stub_storage.pages) == 0

    def test_no_duplicate_steps_on_resume(
        self, tmp_path, stub_downloader, stub_transcriber, stub_summarizer, stub_storage
    ):
        """A resumed pipeline must NOT create duplicate step records."""
        svc = _make_service(tmp_path, stub_downloader, stub_transcriber, stub_summarizer, stub_storage)
        url = "https://www.youtube.com/watch?v=resume_test"

        # Simulate a partial checkpoint: download done, transcribe failed
        partial = PipelineResult(url=url, started_at="2026-01-01T00:00:00")
        step_dl = partial.add_step("download")
        step_dl.mark_success(platform="YouTube")
        step_tr = partial.add_step("transcribe")
        step_tr.mark_error(RuntimeError("CUDA OOM"))
        svc.ckpt.save(partial)

        # Run again — should resume and NOT duplicate steps
        result = svc.run(url)
        step_names = [s.name for s in result.steps]
        assert step_names.count("download") == 1, f"duplicate download steps: {step_names}"
        assert step_names.count("transcribe") == 1, f"duplicate transcribe steps: {step_names}"
        assert result.status == StepStatus.SUCCESS

    def test_step_count_consistency(
        self, tmp_path, stub_downloader, stub_transcriber, stub_summarizer, stub_storage
    ):
        """Each step name must appear at most once per pipeline run."""
        svc = _make_service(tmp_path, stub_downloader, stub_transcriber, stub_summarizer, stub_storage)
        result = svc.run("https://www.youtube.com/watch?v=count_test")

        names = [s.name for s in result.steps]
        assert len(names) == len(set(names)), f"duplicate steps: {names}"
