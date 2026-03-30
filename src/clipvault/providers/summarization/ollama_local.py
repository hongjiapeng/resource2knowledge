# -*- coding: utf-8 -*-
"""
Local Ollama summarization provider.
"""

from __future__ import annotations

import gc
import json
import os
from typing import Dict, List, Optional, Tuple

import ollama
import torch

from ...models.summary import SummaryResult
from ..base import Summarizer


# Model selection priority
_MODEL_PRIORITY: List[Tuple[List[str], str]] = [
    (["qwen2.5", "7b"], "qwen2.5 7B"),
    (["qwen2.5", "14b"], "qwen2.5 14B"),
    (["qwen2.5", "3b"], "qwen2.5 3B"),
    (["qwen3", "8b"], "qwen3 8B"),
    (["qwen3", "4b"], "qwen3 4B"),
    (["llama3", "8b"], "llama3 8B"),
    (["llama3", "3b"], "llama3 3B"),
    (["mistral", "7b"], "mistral 7B"),
    (["phi3"], "phi3"),
    (["phi"], "phi"),
]

RESPONSE_SCHEMA = {
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

_VIDEO_SYSTEM = """你是一个专业的视频内容分析师。你的任务是对视频 transcript（转录文本）进行总结。

请按以下格式输出 JSON：
{
    "summary": "视频内容的详细总结 (100-500字)",
    "key_points": ["要点1", "要点2", "要点3", "要点4", "要点5"],
    "tags": ["标签1", "标签2", "标签3"],
    "category": "视频分类",
    "sentiment": "positive/negative/neutral",
    "language": "zh/en/mixed"
}

要求：
- summary 需要覆盖视频的核心内容和结论
- key_points 提取最重要的 5 个要点
- tags 基于内容自动生成相关标签
- category 使用简短的中文分类
- 直接输出 JSON，不要其他内容
- 不要输出 markdown 代码块"""

_IMAGE_TEXT_SYSTEM = """你是一个专业的小红书内容分析师。你的任务是对图文笔记内容进行分析总结。

请按以下格式输出 JSON：
{
    "summary": "内容的详细总结 (100-500字)",
    "key_points": ["要点1", "要点2", "要点3", "要点4", "要点5"],
    "tags": ["标签1", "标签2", "标签3"],
    "category": "内容分类",
    "sentiment": "positive/negative/neutral",
    "language": "zh/en/mixed"
}

要求：
- summary 需要覆盖图文的核心内容和作者观点
- key_points 提取最重要的 5 个要点
- tags 基于内容自动生成相关标签
- category 使用简短的中文分类
- 直接输出 JSON，不要其他内容
- 不要输出 markdown 代码块"""


def _detect_model(primary: Optional[str], fallback: Optional[str]) -> str:
    """Pick the best installed Ollama model."""
    default_fallback = "qwen2.5:7b-instruct-q4_K_M"
    try:
        raw = getattr(ollama.list(), "models", None) or ollama.list().get("models", [])
        installed = []
        for m in raw:
            name = getattr(m, "model", None) or getattr(m, "name", None) or m.get("model", "") or m.get("name", "")
            if name:
                installed.append(name)
        if not installed:
            return fallback or default_fallback

        # Try explicit primary
        if primary and primary != "auto":
            for n in installed:
                if primary.lower() in n.lower():
                    return n

        # Try explicit fallback
        if fallback:
            for n in installed:
                if fallback.lower() in n.lower():
                    return n

        # Priority list
        for keywords, _ in _MODEL_PRIORITY:
            for n in installed:
                nl = n.lower()
                if all(k in nl for k in keywords):
                    return n

        return installed[0]
    except Exception:
        return fallback or default_fallback


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


class OllamaLocalSummarizer(Summarizer):
    """Ollama-backed local LLM summarizer."""

    def __init__(
        self,
        model: Optional[str] = None,
        model_fallback: Optional[str] = None,
    ) -> None:
        primary = model or os.getenv("LLM_MODEL")
        fb = model_fallback or os.getenv("LLM_MODEL_FALLBACK")
        self.model = _detect_model(primary, fb)
        self._fallback = fb

    # ── Summarizer interface ──────────────────────────────

    def check_available(self) -> bool:
        try:
            ollama.list()
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
        if len(text) > max_length:
            text = text[:max_length] + "..."

        system = _IMAGE_TEXT_SYSTEM if content_type == "image_text" else _VIDEO_SYSTEM
        label = "图文笔记内容" if content_type == "image_text" else "视频转录文本"
        prompt = (
            f"{system}\n\n以下是{label}:\n\n{text}\n\n"
            "请严格返回一个 JSON 对象，不要附加解释、前后缀文本或 markdown 代码块。"
        )

        candidates = [self.model]
        if self._fallback and self._fallback not in candidates:
            candidates.append(self._fallback)

        errors = []
        for model_name in candidates:
            # Structured output
            try:
                resp = ollama.generate(
                    model=model_name,
                    prompt=prompt,
                    format=RESPONSE_SCHEMA,
                    options={"temperature": 0, "num_predict": 1000},
                )
                return self._to_result(_parse_json(resp.response))
            except Exception as e:
                errors.append(f"{model_name}/structured: {e}")

            # Unstructured fallback
            try:
                resp = ollama.generate(
                    model=model_name,
                    prompt=prompt,
                    options={"temperature": 0, "num_predict": 1000},
                )
                return self._to_result(_parse_json(resp.response))
            except Exception as e:
                errors.append(f"{model_name}/text: {e}")

        # Last resort — plain summary
        try:
            resp = ollama.generate(
                model=self.model,
                prompt=f"请用中文总结以下视频转录内容，提取3-5个要点:\n\n{text[:1500]}",
                options={"temperature": 0.3, "num_predict": 500},
            )
            return SummaryResult(summary=resp.response)
        except Exception as e:
            errors.append(f"fallback: {e}")

        raise RuntimeError("Summarization failed: " + " | ".join(errors))

    def unload(self) -> None:
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()

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
