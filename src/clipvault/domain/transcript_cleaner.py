# -*- coding: utf-8 -*-
"""Lightweight transcript cleaning — pure domain logic, no I/O."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class TranscriptCleaner:
    """Apply low-risk cleanup rules to ASR output before summarization."""

    enabled: bool = True

    FILLER_TOKENS = {
        "ah", "eh", "em", "erm", "hmm", "mm", "uh", "uhh", "um", "umm",
        "啊", "嗯", "呃", "欸", "诶",
    }

    _TS = re.compile(r"\[(?:\d+(?:\.\d+)?s?)\s*(?:-|->|–|—)\s*(?:\d+(?:\.\d+)?s?)\]")
    _MULTISPACE = re.compile(r"[ \t]+")
    _MULTIBREAK = re.compile(r"\n{3,}")

    def clean(self, text: str) -> str:
        if not self.enabled or not text:
            return text
        text = self._TS.sub(" ", text)
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = self._MULTIBREAK.sub("\n\n", text)
        text = self._collapse_repeated(text)
        text = self._normalize_ws(text)
        return text.strip()

    def _normalize_ws(self, text: str) -> str:
        lines = []
        for line in text.split("\n"):
            stripped = self._MULTISPACE.sub(" ", line).strip()
            if stripped:
                lines.append(stripped)
        return "\n".join(lines)

    def _collapse_repeated(self, text: str) -> str:
        out = []
        for line in text.split("\n"):
            tokens = line.split()
            if not tokens:
                continue
            compact = []
            i = 0
            while i < len(tokens):
                tok = tokens[i]
                j = i + 1
                while j < len(tokens) and tokens[j] == tok:
                    j += 1
                run = j - i
                low = tok.lower()
                keep = 1 if low in self.FILLER_TOKENS else (1 if run >= 3 else run)
                compact.extend([tok] * keep)
                i = j
            out.append(" ".join(compact))
        return "\n".join(out)
