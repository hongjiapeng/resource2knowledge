# -*- coding: utf-8 -*-
"""Tests for core data models."""

from clipvault.models.resource import ContentType, Platform, ResourceInput
from clipvault.models.pipeline import PipelineResult, StepStatus


class TestPlatformDetection:
    def test_youtube(self):
        assert Platform.from_url("https://www.youtube.com/watch?v=abc") == Platform.YOUTUBE

    def test_bilibili(self):
        assert Platform.from_url("https://bilibili.com/video/BV123") == Platform.BILIBILI

    def test_unknown(self):
        assert Platform.from_url("https://example.com/some") == Platform.UNKNOWN


class TestResourceInput:
    def test_auto_platform(self):
        r = ResourceInput(url="https://youtu.be/abc")
        assert r.platform == Platform.YOUTUBE


class TestPipelineResult:
    def test_roundtrip_checkpoint(self):
        result = PipelineResult(url="https://example.com", title="Test")
        result.status = StepStatus.PENDING
        step = result.add_step("download")
        step.mark_success(platform="YouTube")

        cp = result.to_checkpoint()
        restored = PipelineResult.from_checkpoint(cp)

        assert restored.url == result.url
        assert restored.title == "Test"
        assert len(restored.steps) == 1
        assert restored.steps[0].status == StepStatus.SUCCESS
