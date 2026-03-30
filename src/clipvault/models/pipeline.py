# -*- coding: utf-8 -*-
"""Pipeline execution result and step tracking models."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from .resource import ResourceInput, ContentType, Platform
from .transcript import TranscriptResult
from .summary import SummaryResult


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class StepRecord:
    """Tracks the outcome of a single pipeline step."""
    name: str
    status: StepStatus = StepStatus.PENDING
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    started_at: Optional[str] = None
    finished_at: Optional[str] = None

    def mark_running(self) -> None:
        self.status = StepStatus.RUNNING
        self.started_at = datetime.now().isoformat()

    def mark_success(self, **meta: Any) -> None:
        self.status = StepStatus.SUCCESS
        self.finished_at = datetime.now().isoformat()
        self.metadata.update(meta)

    def mark_skipped(self, reason: str = "") -> None:
        self.status = StepStatus.SKIPPED
        self.metadata["reason"] = reason

    def mark_error(self, error: Exception) -> None:
        self.status = StepStatus.ERROR
        self.error = str(error)
        self.finished_at = datetime.now().isoformat()

    def reset(self) -> None:
        """Reset the record so the step can be retried."""
        self.status = StepStatus.PENDING
        self.error = None
        self.metadata = {}
        self.started_at = None
        self.finished_at = None


@dataclass
class PipelineResult:
    """
    Complete pipeline execution result — serialisable, checkpoint-friendly.
    """

    url: str
    status: StepStatus = StepStatus.PENDING
    content_type: ContentType = ContentType.VIDEO
    platform: Platform = Platform.UNKNOWN

    title: Optional[str] = None
    audio_path: Optional[str] = None

    transcript: Optional[TranscriptResult] = None
    cleaned_transcript: Optional[str] = None
    summary: Optional[SummaryResult] = None

    steps: List[StepRecord] = field(default_factory=list)

    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    elapsed_seconds: Optional[float] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    # ── helpers ────────────────────────────────────────────
    def get_step(self, name: str) -> Optional[StepRecord]:
        for s in self.steps:
            if s.name == name:
                return s
        return None

    def add_step(self, name: str) -> StepRecord:
        rec = StepRecord(name=name)
        self.steps.append(rec)
        return rec

    def ensure_step(self, name: str) -> StepRecord:
        """Return existing step record, or create a new one.

        This avoids duplicate step entries on checkpoint resume.
        """
        existing = self.get_step(name)
        if existing is not None:
            existing.reset()
            return existing
        return self.add_step(name)

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a JSON-safe dict."""
        d: Dict[str, Any] = {
            "url": self.url,
            "status": self.status.value,
            "content_type": self.content_type.value,
            "platform": self.platform.value,
            "title": self.title,
            "audio_path": self.audio_path,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "elapsed_seconds": self.elapsed_seconds,
            "error": self.error,
            "metadata": self.metadata,
        }
        if self.transcript:
            d["transcript"] = {
                "text": self.transcript.text,
                "language": self.transcript.language,
                "duration": self.transcript.duration,
                "device": self.transcript.device,
                "segment_count": len(self.transcript.segments),
            }
        if self.cleaned_transcript is not None:
            d["cleaned_transcript_length"] = len(self.cleaned_transcript)
        if self.summary:
            d["summary"] = asdict(self.summary)
        d["steps"] = [asdict(s) for s in self.steps]
        return d

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    # ── checkpoint serialisation ───────────────────────────
    def to_checkpoint(self) -> Dict[str, Any]:
        """Full checkpoint data including raw transcript text."""
        cp = self.to_dict()
        if self.transcript:
            cp["transcript_text"] = self.transcript.text
        if self.cleaned_transcript:
            cp["cleaned_transcript"] = self.cleaned_transcript
        return cp

    @classmethod
    def from_checkpoint(cls, data: Dict[str, Any]) -> PipelineResult:
        """Restore from a checkpoint dict (best-effort)."""
        result = cls(
            url=data["url"],
            status=StepStatus(data.get("status", "pending")),
            content_type=ContentType(data.get("content_type", "video")),
            platform=Platform(data.get("platform", "Unknown")),
            title=data.get("title"),
            audio_path=data.get("audio_path"),
            started_at=data.get("started_at"),
            finished_at=data.get("finished_at"),
            elapsed_seconds=data.get("elapsed_seconds"),
            error=data.get("error"),
            metadata=data.get("metadata", {}),
        )
        # Restore transcript
        transcript_text = data.get("transcript_text")
        if transcript_text:
            t_meta = data.get("transcript", {})
            result.transcript = TranscriptResult(
                text=transcript_text,
                language=t_meta.get("language", "zh"),
                duration=t_meta.get("duration", 0.0),
                device=t_meta.get("device"),
            )
        # Restore cleaned transcript
        result.cleaned_transcript = data.get("cleaned_transcript")
        # Restore summary
        summary_data = data.get("summary")
        if summary_data and isinstance(summary_data, dict):
            result.summary = SummaryResult(**summary_data)
        # Restore steps
        for s in data.get("steps", []):
            rec = StepRecord(
                name=s["name"],
                status=StepStatus(s.get("status", "pending")),
                error=s.get("error"),
                metadata=s.get("metadata", {}),
                started_at=s.get("started_at"),
                finished_at=s.get("finished_at"),
            )
            result.steps.append(rec)
        return result
