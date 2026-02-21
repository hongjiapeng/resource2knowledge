# -*- coding: utf-8 -*-
"""
🎬 Video Downloader Module
使用 yt-dlp 下载视频音频
支持小红书图文笔记抓取
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
    """获取 yt-dlp 路径"""
    # 检查 venv 中是否有 yt-dlp
    venv_dir = Path(sys.executable).parent
    yt_dlp_venv = venv_dir / "yt-dlp.exe"
    if yt_dlp_venv.exists():
        return str(yt_dlp_venv)
    
    # 尝试直接调用
    return "yt-dlp"


class VideoDownloader:
    """视频下载器 - 仅下载音频流"""
    
    # 支持的平台域名映射
    PLATFORMS = {
        'youtube.com': 'YouTube',
        'youtu.be': 'YouTube',
        'bilibili.com': 'Bilibili',
        'b23.tv': 'Bilibili',
        'douyin.com': 'Douyin',
        'xiaohongshu.com': 'Xiaohongshu',
        'instagram.com': 'Instagram',
        'tiktok.com': 'TikTok',
    }
    
    def __init__(self, output_dir: str = "downloads"):
        """
        初始化下载器
        
        Args:
            output_dir: 音频输出目录
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def detect_platform(self, url: str) -> str:
        """检测视频平台"""
        for domain, platform in self.PLATFORMS.items():
            if domain in url.lower():
                return platform
        return 'Unknown'
    
    def get_output_path(self, url: str, platform: str) -> Path:
        """生成输出文件路径"""
        # 使用 URL hash 作为文件名，避免特殊字符问题
        import hashlib
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        
        # 小红书用 mp4，其他用 m4a
        ext = 'mp4' if platform == 'Xiaohongshu' else 'm4a'
        return self.output_dir / f"{platform}_{url_hash}.{ext}"
    
    def download(self, url: str, force: bool = False) -> Dict:
        """
        下载视频音频
        
        Args:
            url: 视频链接
            force: 是否强制重新下载
            
        Returns:
            包含音频路径、平台、视频标题的字典
        """
        platform = self.detect_platform(url)
        output_path = self.get_output_path(url, platform)
        
        # 如果文件已存在且不强制下载，直接返回
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
        
        # ========== 平台特定配置 ==========
        if platform == 'Xiaohongshu':
            # 小红书：下载完整视频（保留视频轨道）
            cmd = [
                yt_dlp,
                '-f', 'best',
                '--merge-output-format', 'mp4',
                '-o', str(output_path),
                url
            ]
        elif platform == 'Bilibili':
            # B站：下载音频
            cmd = [
                yt_dlp,
                '-f', 'bestaudio',
                '--audio-format', 'm4a',
                '--audio-quality', '0',
                '-o', str(output_path),
                url
            ]
        else:
            # YouTube 等平台：下载音频
            cmd = [
                yt_dlp,
                '-f', 'bestaudio',
                '--audio-format', 'm4a',
                '-o', str(output_path),
                '--no-playlist',
                url
            ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600  # 10分钟超时
            )
            
            if result.returncode != 0:
                raise Exception(f"下载失败: {result.stderr}")
            
            # 获取视频标题
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
        """获取视频标题"""
        try:
            cmd = [
                get_yt_dlp_path(),
                '--get-title',
                '--no-download',
                url
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                title = result.stdout.strip()
                # 清理标题中的非法文件名字符
                title = re.sub(r'[<>:"/\\|?*]', '_', title)
                return title[:100]  # 限制长度
        except:
            pass
        return None
    
    def cleanup(self, audio_path: str):
        """删除临时音频文件"""
        try:
            if os.path.exists(audio_path):
                os.remove(audio_path)
                print(f"🗑️ 已清理: {audio_path}")
        except Exception as e:
            print(f"⚠️ 清理失败: {e}")

    def scrape_xiaohongshu(self, url: str) -> Dict:
        """
        抓取小红书图文笔记内容
        
        Args:
            url: 小红书链接
            
        Returns:
            包含标题、描述、图片、评论的字典
        """
        print("📝 未检测到视频，尝试抓取图文内容...")
        
        # 尝试方法1: 用 yt-dlp --dump-json 获取元数据
        try:
            yt_dlp = get_yt_dlp_path()
            cmd = [yt_dlp, '--dump-json', '--no-download', url]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            if result.returncode == 0 and result.stdout.strip():
                data = json.loads(result.stdout.strip())
                
                title = data.get('title', '')
                description = data.get('description', '') or data.get('title', '')
                uploader = data.get('uploader', '未知作者')
                
                # 尝试获取图片
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
        
        # 尝试方法2: 直接请求网页解析
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'text/html,application/xhtml+xml',
            }
            response = requests.get(url, headers=headers, timeout=30)
            
            # 从 HTML 中提取 JSON 数据
            json_match = re.search(r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\});', response.text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(1))
                # 解析 note 数据...
                print("✅ 图文抓取成功(网页解析)")
        except Exception as e:
            print(f"⚠️ 网页解析失败: {e}")
        
        raise Exception("图文抓取失败，请尝试提供视频链接")
    
    def download_or_scrape(self, url: str, force: bool = False) -> Dict:
        """
        下载视频，失败则抓取图文
        
        Args:
            url: 链接
            force: 是否强制重新下载
            
        Returns:
            包含音频路径或图文内容的字典
        """
        platform = self.detect_platform(url)
        
        # 小红书：先尝试获取元数据，判断是视频还是图文
        if platform == 'Xiaohongshu':
            # 先用 --dump-json 获取信息，判断内容类型
            try:
                result = self._get_xiaohongshu_info(url)
                if result.get('has_video', True):
                    # 有视频，用普通下载
                    return self.download(url, force)
                else:
                    # 无视频，返回图文内容
                    print("📝 检测为图文笔记")
                    return result
            except Exception as e:
                print(f"⚠️ 元数据获取失败: {e}，尝试直接下载...")
                try:
                    return self.download(url, force)
                except:
                    # 下载失败，尝试抓取图文
                    print("💡 尝试抓取图文内容...")
                    return self.scrape_xiaohongshu(url)
        
        # 其他平台直接下载
        return self.download(url, force)
    
    def _get_xiaohongshu_info(self, url: str) -> Dict:
        """获取小红书笔记信息（判断是否有视频）"""
        yt_dlp = get_yt_dlp_path()
        cmd = [yt_dlp, '--dump-json', '--no-download', '--skip-download', url]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout.strip())
            
            title = data.get('title', '')
            description = data.get('description', '') or data.get('title', '')
            uploader = data.get('uploader', '未知作者')
            
            # 判断是否有视频流
            has_video = bool(data.get('formats')) or data.get('duration', 0) > 0
            
            # 获取图片
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


if __name__ == "__main__":
    # 测试下载
    downloader = VideoDownloader()
    
    # 测试 URL
    test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    
    try:
        result = downloader.download(test_url)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"❌ 错误: {e}")
