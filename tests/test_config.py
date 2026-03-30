# -*- coding: utf-8 -*-
"""Tests for config loading."""

from pathlib import Path

from clipvault.config.settings import AppSettings, ProviderMode
from clipvault.config.runtime import RuntimeConfig


class TestAppSettings:
    def test_defaults(self, tmp_path: Path):
        s = AppSettings(project_dir=tmp_path)
        assert s.provider_mode == ProviderMode.LOCAL
        assert s.whisper_model == "medium"
        assert s.enable_transcript_cleaning is True
        assert s.disable_notion is False

    def test_paths_relative_to_project(self, tmp_path: Path):
        s = AppSettings(project_dir=tmp_path)
        assert s.download_dir == tmp_path / "downloads"
        assert s.checkpoint_dir == tmp_path / "checkpoints"
        assert s.output_dir == tmp_path / "outputs"


class TestRuntimeConfig:
    def test_skip(self):
        rc = RuntimeConfig(skip_steps={"transcribe", "summarize"})
        assert rc.should_skip("transcribe") is True
        assert rc.should_skip("download") is False

    def test_defaults(self):
        rc = RuntimeConfig()
        assert rc.resume is True
        assert rc.dry_run is False
        assert rc.skip_steps == set()
