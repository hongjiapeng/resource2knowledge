# -*- coding: utf-8 -*-
"""Resource input model and content type definitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class ContentType(str, Enum):
    VIDEO = "video"
    IMAGE_TEXT = "image_text"
    AUDIO = "audio"
    TEXT = "text"


class Platform(str, Enum):
    YOUTUBE = "YouTube"
    BILIBILI = "Bilibili"
    DOUYIN = "Douyin"
    XIAOHONGSHU = "Xiaohongshu"
    TIKTOK = "TikTok"
    INSTAGRAM = "Instagram"
    X = "X"
    UNKNOWN = "Unknown"

    @classmethod
    def from_url(cls, url: str) -> Platform:
        _MAP = {
            "youtube.com": cls.YOUTUBE,
            "youtu.be": cls.YOUTUBE,
            "bilibili.com": cls.BILIBILI,
            "b23.tv": cls.BILIBILI,
            "douyin.com": cls.DOUYIN,
            "xiaohongshu.com": cls.XIAOHONGSHU,
            "tiktok.com": cls.TIKTOK,
            "instagram.com": cls.INSTAGRAM,
            "x.com": cls.X,
            "twitter.com": cls.X,
        }
        lower = url.lower()
        for domain, platform in _MAP.items():
            if domain in lower:
                return platform
        return cls.UNKNOWN


@dataclass
class ResourceInput:
    """Structured input for the processing pipeline."""

    url: str
    platform: Platform = field(init=False)
    content_type: ContentType = ContentType.VIDEO
    title: Optional[str] = None
    language: Optional[str] = None
    raw_text: Optional[str] = None       # pre-existing transcript / text
    image_urls: List[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.platform = Platform.from_url(self.url)
