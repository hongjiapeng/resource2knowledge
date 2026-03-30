# -*- coding: utf-8 -*-
"""Summary data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class SummaryResult:
    """Structured summary output."""
    summary: str = ""
    key_points: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    category: str = "未分类"
    sentiment: str = "neutral"
    language: str = "zh"
