# -*- coding: utf-8 -*-
"""Lightweight transcript cleaning utilities for summary-ready text."""

from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass
class TranscriptCleaner:
    """Apply low-risk cleanup rules to ASR output before summarization."""

    enabled: bool = True

    FILLER_TOKENS = {
        "ah",
        "eh",
        "em",
        "erm",
        "hmm",
        "mm",
        "uh",
        "uhh",
        "um",
        "umm",
        "啊",
        "嗯",
        "呃",
        "欸",
        "诶",
    }

    TIMESTAMP_PATTERN = re.compile(
        r"\[(?:\d+(?:\.\d+)?s?)\s*(?:-|->|–|—)\s*(?:\d+(?:\.\d+)?s?)\]"
    )
    MULTISPACE_PATTERN = re.compile(r"[ \t]+")
    MULTIBREAK_PATTERN = re.compile(r"\n{3,}")

    def clean(self, text: str) -> str:
        """Return cleaned transcript text or the original text if disabled."""
        if not self.enabled or not text:
            return text

        cleaned = text
        cleaned = self._remove_timestamps(cleaned)
        cleaned = self._normalize_line_breaks(cleaned)
        cleaned = self._collapse_repeated_tokens(cleaned)
        cleaned = self._normalize_whitespace(cleaned)
        return cleaned.strip()

    def _remove_timestamps(self, text: str) -> str:
        return self.TIMESTAMP_PATTERN.sub(" ", text)

    def _normalize_line_breaks(self, text: str) -> str:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        return self.MULTIBREAK_PATTERN.sub("\n\n", text)

    def _normalize_whitespace(self, text: str) -> str:
        normalized_lines = []
        for line in text.split("\n"):
            stripped = self.MULTISPACE_PATTERN.sub(" ", line).strip()
            if stripped:
                normalized_lines.append(stripped)
        return "\n".join(normalized_lines)

    def _collapse_repeated_tokens(self, text: str) -> str:
        lines = []
        for line in text.split("\n"):
            tokens = line.split()
            if not tokens:
                continue

            compact_tokens: list[str] = []
            index = 0
            while index < len(tokens):
                token = tokens[index]
                run_end = index + 1
                while run_end < len(tokens) and tokens[run_end] == token:
                    run_end += 1

                run_length = run_end - index
                lowered = token.lower()
                if lowered in self.FILLER_TOKENS:
                    keep = 1
                elif run_length >= 3:
                    keep = 1
                else:
                    keep = run_length

                compact_tokens.extend([token] * keep)
                index = run_end

            lines.append(" ".join(compact_tokens))

        return "\n".join(lines)