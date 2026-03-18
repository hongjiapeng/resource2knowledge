# -*- coding: utf-8 -*-
"""
🎬 Video Downloader Module
Download video/audio with yt-dlp
Support scraping Xiaohongshu image-text notes
"""

import os
import sys
import subprocess
import json
import re
import requests
from pathlib import Path
from typing import Optional, Dict


def get_yt_dlp_path() -> str:
    """Get the yt-dlp executable path."""
    # Check whether yt-dlp exists inside the virtual environment
    venv_dir = Path(sys.executable).parent
    yt_dlp_venv = venv_dir / "yt-dlp.exe"
    if yt_dlp_venv.exists():
        return str(yt_dlp_venv)
    
    # Fall back to calling it directly from PATH
    return "yt-dlp"


def run_command(cmd: list[str], timeout: int) -> subprocess.CompletedProcess:
    """Run subprocess commands with UTF-8-safe decoding on Windows."""
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


class VideoDownloader:
    """Video downloader with audio-first behavior."""
    
    # Supported platform domain mapping
    PLATFORMS = {
        'youtube.com': 'YouTube',
        'youtu.be': 'YouTube',
        'bilibili.com': 'Bilibili',
        'b23.tv': 'Bilibili',
        'douyin.com': 'Douyin',
        'xiaohongshu.com': 'Xiaohongshu',
        'instagram.com': 'Instagram',
        'tiktok.com': 'TikTok',
        'x.com': 'X',
        'twitter.com': 'X',
    }
    
    def __init__(self, output_dir: str = "downloads"):
        """
        Initialize the downloader.
        
        Args:
            output_dir: Audio output directory
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def detect_platform(self, url: str) -> str:
        """Detect the target video platform."""
        for domain, platform in self.PLATFORMS.items():
            if domain in url.lower():
                return platform
        return 'Unknown'
    
    def get_output_path(self, url: str, platform: str) -> Path:
        """Generate the output file path."""
        # Use the URL hash as the filename to avoid special-character issues
        import hashlib
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        
        # Xiaohongshu uses mp4; other platforms use m4a
        ext = 'mp4' if platform == 'Xiaohongshu' else 'm4a'
        return self.output_dir / f"{platform}_{url_hash}.{ext}"
    
    def download(self, url: str, force: bool = False) -> Dict:
        """
        Download video audio.
        
        Args:
            url: Video URL
            force: Whether to force a fresh download
            
        Returns:
            A dictionary containing the audio path, platform, and video title
        """
        platform = self.detect_platform(url)
        output_path = self.get_output_path(url, platform)
        
        # Return immediately if the file already exists and re-download is not forced
        if output_path.exists() and not force:
            print(f"📁 文件已存在: {output_path}")
            return {
                'audio_path': str(output_path),
                'platform': platform,
                'title': output_path.stem,
                'url': url
            }
        
        print(f"⬇️ 开始下载: {url}")
        print(f"📍 平台: {platform}")
        
        yt_dlp = get_yt_dlp_path()
        
        # ========== Platform-specific settings ==========
        if platform == 'Xiaohongshu':
            # Xiaohongshu: download the full video and keep the video track
            cmd = [
                yt_dlp,
                '-f', 'best',
                '--merge-output-format', 'mp4',
                '-o', str(output_path),
                url
            ]
        elif platform == 'Bilibili':
            # Bilibili: download audio only
            cmd = [
                yt_dlp,
                '-f', 'bestaudio',
                '--audio-format', 'm4a',
                '--audio-quality', '0',
                '-o', str(output_path),
                url
            ]
        else:
            # YouTube and other platforms: download audio only
            cmd = [
                yt_dlp,
                '-f', 'bestaudio',
                '--audio-format', 'm4a',
                '-o', str(output_path),
                '--no-playlist',
                url
            ]
        
        try:
            result = run_command(cmd, timeout=600)
            
            if result.returncode != 0:
                raise Exception(f"下载失败: {result.stderr}")
            
            # Retrieve the video title
            title = self._get_title(url) or output_path.stem
            
            print(f"✅ 下载完成: {output_path.name}")
            
            return {
                'audio_path': str(output_path),
                'platform': platform,
                'title': title,
                'url': url
            }
            
        except subprocess.TimeoutExpired:
            raise Exception("下载超时 (超过10分钟)")
        except FileNotFoundError:
            raise Exception("yt-dlp 未安装，请运行: pip install yt-dlp")
        except Exception as e:
            raise Exception(f"下载失败: {str(e)}")
    
    def _get_title(self, url: str) -> Optional[str]:
        """Get the video title."""
        try:
            cmd = [
                get_yt_dlp_path(),
                '--get-title',
                '--no-download',
                url
            ]
            result = run_command(cmd, timeout=30)
            if result.returncode == 0:
                title = result.stdout.strip()
                # Remove characters that are invalid in filenames
                title = re.sub(r'[<>:"/\\|?*]', '_', title)
                return title[:100]  # Keep the filename length bounded
        except:
            pass
        return None
    
    def cleanup(self, audio_path: str):
        """Delete the temporary audio file."""
        try:
            if os.path.exists(audio_path):
                os.remove(audio_path)
                print(f"🗑️ 已清理: {audio_path}")
        except Exception as e:
            print(f"⚠️ 清理失败: {e}")

    def scrape_xiaohongshu(self, url: str) -> Dict:
        """
        Scrape Xiaohongshu image-text note content.
        
        Args:
            url: Xiaohongshu URL
            
        Returns:
            A dictionary containing the title, description, images, and comments
        """
        print("📝 未检测到视频，尝试抓取图文内容...")
        
        # Attempt 1: use yt-dlp --dump-json to fetch metadata
        try:
            yt_dlp = get_yt_dlp_path()
            cmd = [yt_dlp, '--dump-json', '--no-download', url]
            
            result = run_command(cmd, timeout=60)
            
            if result.returncode == 0 and result.stdout.strip():
                data = json.loads(result.stdout.strip())
                
                title = data.get('title', '')
                description = data.get('description', '') or data.get('title', '')
                uploader = data.get('uploader', '未知作者')
                
                # Try to collect image URLs
                images = []
                if 'thumbnails' in data:
                    for thumb in data.get('thumbnails', []):
                        if 'url' in thumb:
                            images.append(thumb['url'])
                
                result_dict = {
                    'type': 'image_text',
                    'title': title or description[:50] or '小红书笔记',
                    'description': description,
                    'author': uploader,
                    'images': images,
                    'comments': [],
                    'url': url
                }
                
                print(f"✅ 图文抓取成功(yt-dlp): {result_dict['title']}")
                return result_dict
        except Exception as e:
            print(f"⚠️ yt-dlp 方法失败: {e}")
        
        # Attempt 2: request and parse the webpage directly
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'text/html,application/xhtml+xml',
            }
            response = requests.get(url, headers=headers, timeout=30)
            
            # Extract JSON data from the HTML
            json_match = re.search(r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\});', response.text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(1))
                # Parse the note payload...
                print("✅ 图文抓取成功(网页解析)")
        except Exception as e:
            print(f"⚠️ 网页解析失败: {e}")
        
        raise Exception("图文抓取失败，请尝试提供视频链接")
    
    def download_or_scrape(self, url: str, force: bool = False) -> Dict:
        """
        Download the video, or scrape image-text content on failure.
        
        Args:
            url: Target URL
            force: Whether to force a fresh download
            
        Returns:
            A dictionary containing either the audio path or image-text content
        """
        platform = self.detect_platform(url)
        
        # Xiaohongshu: inspect metadata first to determine video vs. image-text
        if platform == 'Xiaohongshu':
            # Use --dump-json first to determine the content type
            try:
                result = self._get_xiaohongshu_info(url)
                if result.get('has_video', True):
                    # Video present: proceed with the normal download flow
                    return self.download(url, force)
                else:
                    # No video: return the image-text payload
                    print("📝 检测为图文笔记")
                    return result
            except Exception as e:
                print(f"⚠️ 元数据获取失败: {e}，尝试直接下载...")
                try:
                    return self.download(url, force)
                except:
                    # Download failed, so fall back to scraping image-text content
                    print("💡 尝试抓取图文内容...")
                    return self.scrape_xiaohongshu(url)
        
        # X (Twitter): try download first, then fall back to scraping
        if platform == 'X':
            try:
                return self.download(url, force)
            except Exception as e:
                error_msg = str(e)
                # Check whether this is specifically a "no video" error
                if 'No video could be found' in error_msg or 'No media found' in error_msg:
                    print("💡 该帖子没有视频，尝试抓取文字和图片...")
                    return self.scrape_x_tweet(url)
                else:
                    # For other errors, still try scraping the post content
                    print(f"⚠️ 下载失败: {e}，尝试抓取帖子内容...")
                    try:
                        return self.scrape_x_tweet(url)
                    except:
                        raise  # If scraping also fails, re-raise the original error
        
        # Other platforms go through the normal download flow
        return self.download(url, force)
    
    def _get_xiaohongshu_info(self, url: str) -> Dict:
        """Get Xiaohongshu note metadata and determine whether it includes video."""
        yt_dlp = get_yt_dlp_path()
        cmd = [yt_dlp, '--dump-json', '--no-download', '--skip-download', url]

        result = run_command(cmd, timeout=60)

        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout.strip())

            title = data.get('title', '')
            description = data.get('description', '') or data.get('title', '')
            uploader = data.get('uploader', '未知作者')

            # Determine whether a video stream is present
            has_video = bool(data.get('formats')) or data.get('duration', 0) > 0

            # Collect image URLs
            images = []
            for thumb in data.get('thumbnails', []):
                if 'url' in thumb:
                    images.append(thumb['url'])

            return {
                'type': 'image_text',
                'has_video': has_video,
                'title': title or description[:50] or '小红书笔记',
                'description': description,
                'author': uploader,
                'images': images,
                'comments': [],
                'url': url
            }

        raise Exception("无法获取笔记信息")

    def scrape_x_tweet(self, url: str) -> Dict:
        """
        Scrape X (Twitter) post content, including text and images.
        
        Args:
            url: X post URL
            
        Returns:
            A dictionary containing the text content and images
        """
        print("📝 检测为 X 帖子，尝试抓取内容...")
        
        # Extract the tweet ID and username
        tweet_id_match = re.search(r'/(?:status|i)/(\d+)', url)
        username_match = re.search(r'x\.com/([^/]+)/status', url)
        
        tweet_id = tweet_id_match.group(1) if tweet_id_match else None
        username = username_match.group(1) if username_match else None
        
        # Method 1: try the vxtwitter.com API (the simplest and most reliable option)
        if tweet_id and username:
            try:
                print(f"🔄 尝试 vxtwitter API...")
                vx_url = f"https://api.vxtwitter.com/{username}/status/{tweet_id}"
                response = requests.get(vx_url, timeout=30)
                if response.status_code == 200:
                    data = response.json()
                    description = data.get('text', '')
                    if description:
                        # Collect image URLs
                        images = data.get('media_urls', [])
                        result_dict = {
                            'type': 'image_text',
                            'title': description[:50] or 'X 帖子',
                            'description': description,
                            'author': data.get('user_name', username),
                            'images': images,
                            'comments': [],
                            'url': url
                        }
                        print(f"✅ X 帖子抓取成功: {result_dict['title']}")
                        return result_dict
            except Exception as e:
                print(f"⚠️ vxtwitter 失败: {e}")
        
        # Method 2: try the fxtwitter.com API
        if tweet_id and username:
            try:
                print(f"🔄 尝试 fxtwitter API...")
                fx_url = f"https://api.fxtwitter.com/{username}/status/{tweet_id}"
                response = requests.get(fx_url, timeout=30)
                if response.status_code == 200:
                    data = response.json()
                    tweet_data = data.get('tweet', {})
                    description = tweet_data.get('text', '')
                    if description:
                        # Collect photo media
                        images = []
                        media = tweet_data.get('media', [])
                        for m in media:
                            if m.get('type') == 'photo':
                                images.append(m.get('url', ''))
                        
                        result_dict = {
                            'type': 'image_text',
                            'title': description[:50] or 'X 帖子',
                            'description': description,
                            'author': tweet_data.get('author', {}).get('name', username),
                            'images': images,
                            'comments': [],
                            'url': url
                        }
                        print(f"✅ X 帖子抓取成功(fxtwitter): {result_dict['title']}")
                        return result_dict
            except Exception as e:
                print(f"⚠️ fxtwitter 失败: {e}")
        
        raise Exception("X 帖子抓取失败，请确认网络能访问 X")


if __name__ == "__main__":
    # Download smoke test
    downloader = VideoDownloader()
    
    # Test URL
    test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    
    try:
        result = downloader.download(test_url)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"❌ 错误: {e}")
