# -*- coding: utf-8 -*-
"""Tests for domain logic (transcript cleaner)."""

from clipvault.domain.transcript_cleaner import TranscriptCleaner


class TestTranscriptCleaner:
    def test_disabled(self):
        c = TranscriptCleaner(enabled=False)
        assert c.clean("嗯 嗯 嗯 hello") == "嗯 嗯 嗯 hello"

    def test_filler_collapse(self):
        c = TranscriptCleaner()
        assert c.clean("嗯 嗯 嗯 hello") == "嗯 hello"

    def test_timestamp_removal(self):
        c = TranscriptCleaner()
        result = c.clean("[0.0s - 1.5s] hello world")
        assert "hello world" in result
        assert "[" not in result

    def test_multiline_normalize(self):
        c = TranscriptCleaner()
        result = c.clean("hello\n\n\n\n\nworld")
        assert result == "hello\nworld"
