# -*- coding: utf-8 -*-
"""
yt-dlp based downloader — migrated from the original downloader.py.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import requests

from ...models.resource import ContentType, Platform, ResourceInput
from ..base import Downloader


def _yt_dlp_path() -> str:
    venv_bin = Path(sys.executable).parent
    candidate = venv_bin / ("yt-dlp.exe" if sys.platform == "win32" else "yt-dlp")
    return str(candidate) if candidate.exists() else "yt-dlp"


def _run(cmd: list[str], timeout: int = 600) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        env=env,
    )


class YtdlpDownloader(Downloader):
    """Download audio / scrape image-text via yt-dlp."""

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # ── Downloader interface ──────────────────────────────

    def download(self, resource: ResourceInput, *, force: bool = False) -> Dict[str, Any]:
        platform = resource.platform

        # Xiaohongshu: check for video vs. image-text first
        if platform == Platform.XIAOHONGSHU:
            return self._download_or_scrape_xhs(resource, force=force)

        # X/Twitter: try video, fall back to text scrape
        if platform == Platform.X:
            return self._download_or_scrape_x(resource, force=force)

        return self._download_audio(resource, force=force)

    def cleanup(self, path: str) -> None:
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass

    # ── audio download ────────────────────────────────────

    def _output_path(self, resource: ResourceInput) -> Path:
        url_hash = hashlib.md5(resource.url.encode()).hexdigest()[:8]
        ext = "mp4" if resource.platform == Platform.XIAOHONGSHU else "m4a"
        return self.output_dir / f"{resource.platform.value}_{url_hash}.{ext}"

    def _download_audio(self, resource: ResourceInput, *, force: bool = False) -> Dict[str, Any]:
        output_path = self._output_path(resource)

        if output_path.exists() and not force:
            return self._result(resource, output_path, title=output_path.stem)

        yt = _yt_dlp_path()
        platform = resource.platform

        if platform == Platform.XIAOHONGSHU:
            cmd = [yt, "-f", "best", "--merge-output-format", "mp4", "-o", str(output_path), resource.url]
        elif platform == Platform.BILIBILI:
            cmd = [yt, "-f", "bestaudio", "--audio-format", "m4a", "--audio-quality", "0", "-o", str(output_path), resource.url]
        else:
            cmd = [yt, "-f", "bestaudio", "--audio-format", "m4a", "-o", str(output_path), "--no-playlist", resource.url]

        try:
            proc = _run(cmd, timeout=600)
        except subprocess.TimeoutExpired:
            raise RuntimeError("Download timed out (>10 min)")
        except FileNotFoundError:
            raise RuntimeError("yt-dlp not installed — pip install yt-dlp")

        if proc.returncode != 0:
            raise RuntimeError(f"yt-dlp failed: {proc.stderr}")

        title = self._fetch_title(resource.url) or output_path.stem
        return self._result(resource, output_path, title=title)

    # ── platform-specific helpers ─────────────────────────

    def _download_or_scrape_xhs(self, resource: ResourceInput, *, force: bool = False) -> Dict[str, Any]:
        try:
            info = self._xhs_info(resource.url)
            if info.get("has_video", True):
                return self._download_audio(resource, force=force)
            return info
        except Exception:
            try:
                return self._download_audio(resource, force=force)
            except Exception:
                return self._scrape_xhs(resource.url)

    def _download_or_scrape_x(self, resource: ResourceInput, *, force: bool = False) -> Dict[str, Any]:
        try:
            return self._download_audio(resource, force=force)
        except Exception as e:
            err = str(e)
            if "No video" in err or "No media" in err:
                return self._scrape_x(resource.url)
            try:
                return self._scrape_x(resource.url)
            except Exception:
                raise

    def _xhs_info(self, url: str) -> Dict[str, Any]:
        proc = _run([_yt_dlp_path(), "--dump-json", "--no-download", "--skip-download", url], timeout=60)
        if proc.returncode != 0 or not proc.stdout.strip():
            raise RuntimeError("Cannot retrieve XHS info")
        data = json.loads(proc.stdout.strip())
        has_video = bool(data.get("formats")) or data.get("duration", 0) > 0
        images = [t["url"] for t in data.get("thumbnails", []) if "url" in t]
        return {
            "type": "image_text",
            "content_type": ContentType.IMAGE_TEXT.value,
            "has_video": has_video,
            "title": data.get("title") or "小红书笔记",
            "description": data.get("description", ""),
            "author": data.get("uploader", ""),
            "images": images,
            "comments": [],
            "url": url,
            "platform": Platform.XIAOHONGSHU.value,
        }

    def _scrape_xhs(self, url: str) -> Dict[str, Any]:
        proc = _run([_yt_dlp_path(), "--dump-json", "--no-download", url], timeout=60)
        if proc.returncode == 0 and proc.stdout.strip():
            data = json.loads(proc.stdout.strip())
            images = [t["url"] for t in data.get("thumbnails", []) if "url" in t]
            return {
                "type": "image_text",
                "content_type": ContentType.IMAGE_TEXT.value,
                "title": data.get("title", "小红书笔记"),
                "description": data.get("description", ""),
                "author": data.get("uploader", ""),
                "images": images,
                "comments": [],
                "url": url,
                "platform": Platform.XIAOHONGSHU.value,
            }
        raise RuntimeError("Xiaohongshu scrape failed")

    def _scrape_x(self, url: str) -> Dict[str, Any]:
        tweet_id_m = re.search(r"/(?:status|i)/(\d+)", url)
        user_m = re.search(r"x\.com/([^/]+)/status", url)
        if tweet_id_m and user_m:
            vx = f"https://api.vxtwitter.com/{user_m.group(1)}/status/{tweet_id_m.group(1)}"
            resp = requests.get(vx, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                desc = data.get("text", "")
                if desc:
                    return {
                        "type": "image_text",
                        "content_type": ContentType.IMAGE_TEXT.value,
                        "title": desc[:50] or "X Post",
                        "description": desc,
                        "author": data.get("user_name", user_m.group(1)),
                        "images": data.get("media_urls", []),
                        "comments": [],
                        "url": url,
                        "platform": Platform.X.value,
                    }
        raise RuntimeError("X/Twitter scrape failed")

    # ── utils ─────────────────────────────────────────────

    def _fetch_title(self, url: str) -> Optional[str]:
        try:
            proc = _run([_yt_dlp_path(), "--get-title", "--no-download", url], timeout=30)
            if proc.returncode == 0:
                title = proc.stdout.strip()
                title = re.sub(r'[<>:"/\\|?*]', "_", title)
                return title[:100]
        except Exception:
            pass
        return None

    @staticmethod
    def _result(resource: ResourceInput, path: Path, *, title: str) -> Dict[str, Any]:
        return {
            "audio_path": str(path),
            "platform": resource.platform.value,
            "title": title,
            "url": resource.url,
            "content_type": ContentType.VIDEO.value,
        }
