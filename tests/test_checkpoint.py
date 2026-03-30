# -*- coding: utf-8 -*-
"""Tests for the checkpoint manager."""

import json
from pathlib import Path

from clipvault.models.pipeline import PipelineResult, StepStatus
from clipvault.services.checkpoint import CheckpointManager


class TestCheckpointManager:
    def test_save_and_load(self, tmp_path: Path):
        mgr = CheckpointManager(tmp_path / "ckpts")
        result = PipelineResult(url="https://example.com/video1", title="Test")
        result.status = StepStatus.ERROR
        step = result.add_step("download")
        step.mark_success(platform="YouTube")

        mgr.save(result)
        loaded = mgr.load("https://example.com/video1")

        assert loaded is not None
        assert loaded.url == result.url
        assert loaded.title == "Test"
        assert len(loaded.steps) == 1

    def test_load_returns_none_for_success(self, tmp_path: Path):
        """Completed checkpoints should not be resumed."""
        mgr = CheckpointManager(tmp_path / "ckpts")
        result = PipelineResult(url="https://example.com/done")
        result.status = StepStatus.SUCCESS
        mgr.save(result)

        loaded = mgr.load("https://example.com/done")
        assert loaded is None

    def test_load_returns_none_for_missing(self, tmp_path: Path):
        mgr = CheckpointManager(tmp_path / "ckpts")
        assert mgr.load("https://example.com/nonexistent") is None

    def test_remove(self, tmp_path: Path):
        mgr = CheckpointManager(tmp_path / "ckpts")
        result = PipelineResult(url="https://example.com/remove", status=StepStatus.ERROR)
        mgr.save(result)
        assert mgr.path_for("https://example.com/remove").exists()

        mgr.remove("https://example.com/remove")
        assert not mgr.path_for("https://example.com/remove").exists()
