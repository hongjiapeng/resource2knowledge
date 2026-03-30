# -*- coding: utf-8 -*-
"""Transcript data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class TranscriptSegment:
    """A single timed segment of speech."""
    start: float
    end: float
    text: str


@dataclass
class TranscriptResult:
    """Full transcription output."""
    text: str
    segments: List[TranscriptSegment] = field(default_factory=list)
    language: str = "zh"
    duration: float = 0.0
    device: Optional[str] = None

    @property
    def char_count(self) -> int:
        return len(self.text)
