# -*- coding: utf-8 -*-
"""
Cloud summarization provider — OpenAI-compatible Chat Completions API.

Works with:
  - OpenAI  (api.openai.com)
  - Azure OpenAI
  - Any OpenAI-compatible endpoint (vLLM, LM Studio, Ollama's /v1, etc.)

Requires:
    pip install openai
    OPENAI_API_KEY set in environment / .env
"""

from __future__ import annotations

import json
import os
from typing import Dict, Optional

from ...models.summary import SummaryResult
from ..base import Summarizer

_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "key_points": {"type": "array", "items": {"type": "string"}},
        "tags": {"type": "array", "items": {"type": "string"}},
        "category": {"type": "string"},
        "sentiment": {"type": "string"},
        "language": {"type": "string"},
    },
    "required": ["summary", "key_points", "tags", "category", "sentiment", "language"],
}

_SYSTEM_PROMPT = """\
你是一个专业的内容分析师。请对以下文本进行总结。

严格按以下 JSON 格式输出，不要附加其他文字：
{
    "summary": "详细总结 (100-500字)",
    "key_points": ["要点1", "要点2", "要点3", "要点4", "要点5"],
    "tags": ["标签1", "标签2", "标签3"],
    "category": "分类",
    "sentiment": "positive/negative/neutral",
    "language": "zh/en/mixed"
}"""


def _parse_json(text: str) -> Dict:
    text = text.strip()
    decoder = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(text[i:])
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            continue
    raise ValueError("No valid JSON object in response")


class OpenAICloudSummarizer(Summarizer):
    """Summarize text via OpenAI-compatible Chat Completions API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-4o-mini",
        base_url: Optional[str] = None,
    ) -> None:
        self._api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.model = model
        self._base_url = base_url or os.getenv("OPENAI_BASE_URL")
        self._client = None

    def _ensure_client(self) -> None:
        if self._client is not None:
            return
        try:
            from openai import OpenAI
        except ImportError:
            raise RuntimeError("openai package required: pip install openai")

        kwargs: dict = {"api_key": self._api_key}
        if self._base_url:
            kwargs["base_url"] = self._base_url
        self._client = OpenAI(**kwargs)

    # ── Summarizer interface ──────────────────────────────

    def check_available(self) -> bool:
        try:
            self._ensure_client()
            assert self._client is not None
            self._client.models.list()
            return True
        except Exception:
            return False

    def summarize(
        self,
        text: str,
        *,
        content_type: str = "video",
        max_length: int = 5000,
    ) -> SummaryResult:
        self._ensure_client()
        assert self._client is not None

        if len(text) > max_length:
            text = text[:max_length] + "..."

        label = "图文笔记" if content_type == "image_text" else "视频转录文本"
        user_msg = f"以下是{label}:\n\n{text}"

        # Try structured JSON mode first (OpenAI supports response_format)
        try:
            resp = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0,
                max_tokens=1500,
                response_format={"type": "json_object"},
            )
            raw = resp.choices[0].message.content or ""
            return self._to_result(_parse_json(raw))
        except Exception:
            pass

        # Fallback: plain text extraction
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0,
            max_tokens=1500,
        )
        raw = resp.choices[0].message.content or ""
        return self._to_result(_parse_json(raw))

    def unload(self) -> None:
        pass  # No local resources to release

    # ── internal ──────────────────────────────────────────

    @staticmethod
    def _to_result(data: Dict) -> SummaryResult:
        return SummaryResult(
            summary=data.get("summary", ""),
            key_points=data.get("key_points", []),
            tags=data.get("tags", []),
            category=data.get("category", "未分类"),
            sentiment=data.get("sentiment", "neutral"),
            language=data.get("language", "zh"),
        )
