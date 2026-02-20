# -*- coding: utf-8 -*-
"""
🎬 Video Pipeline Main Entry
视频转文本 + 总结 + 入库 完整工作流
"""

import os
import sys
from pathlib import Path

# 加载 .env 文件
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

import sys
import json
import argparse
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

# 添加当前目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from downloader import VideoDownloader
from transcriber import WhisperTranscriber
from summarizer import Summarizer
from notion_writer import NotionWriter, MockNotionWriter


# ==================== 配置 ====================

class Config:
    """全局配置"""
    
    # 项目路径
    PROJECT_DIR = Path(__file__).parent
    DOWNLOAD_DIR = PROJECT_DIR / "downloads"
    LOG_DIR = PROJECT_DIR / "logs"
    
    # 模型配置
    WHISPER_MODEL = "small"
    LLM_MODEL = "qwen2.5:7b-instruct-q4_K_M"
    
    # 转录配置
    TRANSCRIBE_LANGUAGE = "zh"  # 中文优先
    MAX_TRANSCRIPT_LENGTH = 5000  # LLM 最大    # Notion输入
    
    # Notion 配置
    NOTION_TOKEN = os.getenv("NOTION_TOKEN")
    NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
    
    # 清理配置
    CLEANUP_AUDIO = True  # 下载后删除音频


# ==================== 日志系统 ====================

def setup_logging(log_level: str = "INFO") -> logging.Logger:
    """设置日志系统"""
    Config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    
    logger = logging.getLogger("VideoPipeline")
    logger.setLevel(getattr(logging, log_level.upper()))
    
    # 文件日志
    log_file = Config.LOG_DIR / f"pipeline_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setFormatter(
        logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    )
    
    # 控制台日志
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(
        logging.Formatter('%(levelname)s: %(message)s')
    )
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger


# ==================== 主流程 ====================

class VideoPipeline:
    """视频处理完整工作流"""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger("VideoPipeline")
        self.downloader = VideoDownloader(str(Config.DOWNLOAD_DIR))
        self.transcriber = WhisperTranscriber()
        self.summarizer = Summarizer(model=Config.LLM_MODEL)
        
        # Notion 写入器 (可选)
        self.notion_writer = None
        if Config.NOTION_TOKEN and Config.NOTION_DATABASE_ID:
            try:
                self.notion_writer = NotionWriter(
                    token=Config.NOTION_TOKEN,
                    database_id=Config.NOTION_DATABASE_ID
                )
                self.notion_writer.test_connection()
            except Exception as e:
                self.logger.warning(f"Notion 初始化失败: {e}，将使用 Mock 模式")
                self.notion_writer = MockNotionWriter()
        else:
            self.logger.info("未配置 Notion，使用 Mock 模式")
            self.notion_writer = MockNotionWriter()
        
        # Checkpoint 文件路径
        self.checkpoint_dir = Config.PROJECT_DIR / "checkpoints"
        self.checkpoint_dir.mkdir(exist_ok=True)
    
    def _get_checkpoint_path(self, url: str) -> Path:
        """获取 checkpoint 文件路径"""
        import hashlib
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        return self.checkpoint_dir / f"{url_hash}.json"
    
    def _save_checkpoint(self, result: dict):
        """保存断点"""
        try:
            checkpoint_path = self._get_checkpoint_path(result['url'])
            with open(checkpoint_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            self.logger.info(f"💾 断点已保存: {checkpoint_path.name}")
        except Exception as e:
            self.logger.warning(f"保存断点失败: {e}")
    
    def _load_checkpoint(self, url: str) -> Optional[dict]:
        """加载断点"""
        try:
            checkpoint_path = self._get_checkpoint_path(url)
            if checkpoint_path.exists():
                with open(checkpoint_path, 'r', encoding='utf-8') as f:
                    result = json.load(f)
                # 检查是否完成
                if result.get('status') == 'success':
                    self.logger.info("✓ 任务已完成，跳过")
                    return None
                return result
        except Exception as e:
            self.logger.warning(f"加载断点失败: {e}")
        return None
    
    def run(self, url: str, skip_transcribe: bool = False, skip_summary: bool = False, resume: bool = True) -> dict:
        """
        执行完整工作流
        
        Args:
            url: 视频链接
            skip_transcribe: 跳过转录 (用于测试)
            skip_summary: 跳过摘要
            resume: 是否从断点续传 (默认 True)
            
        Returns:
            包含所有处理结果的字典
        """
        self.logger.info("=" * 50)
        self.logger.info(f"🚀 开始处理: {url}")
        self.logger.info("=" * 50)
        
        # 尝试恢复断点
        result = self._load_checkpoint(url)
        
        if result and resume:
            self.logger.info("📂 从断点恢复...")
            # 恢复已有数据
            if 'title' in result:
                self.logger.info(f"   已有标题: {result['title']}")
            if 'transcript' in result and result.get('steps', {}).get('transcribe', {}).get('status') == 'success':
                self.logger.info("   ✓ 转录已完成")
            if 'summary' in result and result.get('steps', {}).get('summarize', {}).get('status') == 'success':
                self.logger.info("   ✓ 摘要已完成")
        else:
            result = {
                'url': url,
                'status': 'pending',
                'start_time': datetime.now().isoformat(),
                'steps': {}
            }
        
        try:
            # ========== Step 1: 下载音频 ==========
            self.logger.info("\n📍 Step 1: 下载音频")
            self.logger.info("-" * 30)
            
            download_result = self.downloader.download(url)
            audio_path = download_result['audio_path']
            
            result['steps']['download'] = {
                'status': 'success',
                'audio_path': audio_path,
                'platform': download_result['platform'],
                'title': download_result['title']
            }
            result['title'] = download_result['title']
            result['platform'] = download_result['platform']
            self._save_checkpoint(result)
            
            # ========== Step 2: 转录 ==========
            if not skip_transcribe:
                self.logger.info("\n📍 Step 2: 语音转文本 (Whisper)")
                self.logger.info("-" * 30)
                
                # 加载 Whisper 模型
                self.transcriber.load_model(device="cuda")
                
                # 执行转录
                transcript_result = self.transcriber.transcribe(
                    audio_path,
                    language=Config.TRANSCRIBE_LANGUAGE
                )
                
                # 卸载模型释放显存
                self.transcriber.unload_model()
                
                result['steps']['transcribe'] = {
                    'status': 'success',
                    'text_length': len(transcript_result['text']),
                    'duration': transcript_result['duration'],
                    'language': transcript_result['language']
                }
                result['transcript'] = transcript_result['text']
                self._save_checkpoint(result)
            else:
                self.logger.info("⏭️ 跳过转录步骤")
            
            # ========== Step 3: 清理音频文件 ==========
            if Config.CLEANUP_AUDIO and audio_path:
                self.downloader.cleanup(audio_path)
            
            # ========== Step 4: 生成摘要 ==========
            if not skip_summary and 'transcript' in result:
                self.logger.info("\n📍 Step 3: 生成摘要 (LLM)")
                self.logger.info("-" * 30)
                
                # 检查 Ollama
                if not self.summarizer.check_ollama():
                    raise Exception("Ollama 未运行")
                
                # 检查模型 - 如果没找到也尝试运行 (可能已安装)
                if not self.summarizer.check_model_loaded():
                    self.logger.warning("模型检测未通过，尝试直接调用...")
                
                # 生成摘要
                summary_result = self.summarizer.summarize(
                    result['transcript'],
                    max_length=Config.MAX_TRANSCRIPT_LENGTH
                )
                
                # 释放显存
                self.summarizer.unload_model()
                
                result['steps']['summarize'] = {
                    'status': 'success',
                    'model': Config.LLM_MODEL
                }
                result['summary'] = summary_result['summary']
                result['key_points'] = summary_result['key_points']
                result['tags'] = summary_result['tags']
                result['category'] = summary_result.get('category', '未分类')
                result['sentiment'] = summary_result.get('sentiment', 'neutral')
                self._save_checkpoint(result)
            else:
                self.logger.info("⏭️ 跳过摘要步骤")
            
            # ========== Step 5: 写入 Notion ==========
            if self.notion_writer:
                self.logger.info("\n📍 Step 4: 写入 Notion")
                self.logger.info("-" * 30)
                
                # 检查重复
                if self.notion_writer.check_duplicate(url):
                    self.logger.warning("⚠️ URL 已存在，跳过写入")
                    result['steps']['notion'] = {'status': 'skipped', 'reason': 'duplicate'}
                else:
                    # 准备数据
                    notion_data = {
                        'title': result.get('title', url[:50]),
                        'url': url,
                        'platform': result.get('platform', 'Unknown'),
                        'transcript': result.get('transcript', ''),
                        'summary': result.get('summary', ''),
                        'tags': result.get('tags', []),
                        'key_points': result.get('key_points', []),
                        'category': result.get('category', '未分类'),
                        'sentiment': result.get('sentiment', 'neutral'),
                    }
                    
                    page = self.notion_writer.create_page(notion_data)
                    result['steps']['notion'] = {
                        'status': 'success',
                        'page_id': page.get('id', 'unknown')
                    }
                    self._save_checkpoint(result)
            else:
                self.logger.info("⏭️ 跳过 Notion 写入")
            
            # ========== 完成 ==========
            result['status'] = 'success'
            result['end_time'] = datetime.now().isoformat()
            
            elapsed = datetime.fromisoformat(result['end_time']) - datetime.fromisoformat(result['start_time'])
            result['elapsed_seconds'] = elapsed.total_seconds()
            
            self.logger.info("\n" + "=" * 50)
            self.logger.info("✅ 处理完成!")
            self.logger.info(f"⏱️ 总耗时: {elapsed.total_seconds():.1f} 秒")
            self.logger.info("=" * 50)
            
            # 成功后删除 checkpoint
            try:
                checkpoint_path = self._get_checkpoint_path(url)
                if checkpoint_path.exists():
                    checkpoint_path.unlink()
                    self.logger.info("🗑️ 断点文件已清理")
            except:
                pass
            
            return result
            
        except Exception as e:
            result['status'] = 'error'
            result['error'] = str(e)
            result['end_time'] = datetime.now().isoformat()
            # 保存失败断点
            self._save_checkpoint(result)
            self.logger.error(f"❌ 处理失败: {e}")
            self.logger.info("💡 重新运行将从断点继续")
            raise


def main():
    """CLI 入口"""
    parser = argparse.ArgumentParser(
        description="视频转文本 + 总结 + 入库 工作流",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py "https://www.youtube.com/watch?v=xxx"
  python main.py "https://bilibili.com/video/xxx" --log-level DEBUG
  python main.py "url" --skip-summary
        """
    )
    
    parser.add_argument('url', nargs='?', help='视频链接')
    parser.add_argument('--log-level', default='INFO', 
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       help='日志级别')
    parser.add_argument('--skip-transcribe', action='store_true',
                       help='跳过转录步骤')
    parser.add_argument('--skip-summary', action='store_true',
                       help='跳过摘要步骤')
    parser.add_argument('--no-cleanup', action='store_true',
                       help='不清理临时音频文件')
    parser.add_argument('--no-resume', action='store_true',
                       help='不从断点恢复，重新开始')
    
    args = parser.parse_args()
    
    if not args.url:
        parser.print_help()
        print("\n请提供视频链接")
        sys.exit(1)
    
    # 设置日志
    logger = setup_logging(args.log_level)
    
    # 更新配置
    Config.CLEANUP_AUDIO = not args.no_cleanup
    
    # 创建管道
    pipeline = VideoPipeline(logger)
    
    # 运行
    try:
        result = pipeline.run(
            url=args.url,
            skip_transcribe=args.skip_transcribe,
            skip_summary=args.skip_summary,
            resume=not args.no_resume
        )
        
        # 输出 JSON 结果
        print("\n📊 处理结果:")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
    except Exception as e:
        logger.error(f"工作流执行失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
