# -*- coding: utf-8 -*-
"""
🌐 Resource2Knowledge Main Entry
Internet resource to knowledge + summary + storage workflow
"""

import os
import sys
from pathlib import Path

# Fix Windows UTF-8 output
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Load the .env file
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

import sys
import json
import argparse
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

# Add the current directory to sys.path
sys.path.insert(0, str(Path(__file__).parent))

from downloader import VideoDownloader
from transcriber import WhisperTranscriber
from summarizer import Summarizer
from transcript_cleaner import TranscriptCleaner
from notion_writer import NotionWriter, MockNotionWriter


# ==================== Configuration ====================

class Config:
    """Global configuration."""
    
    # Project paths
    PROJECT_DIR = Path(__file__).parent
    DOWNLOAD_DIR = PROJECT_DIR / "downloads"
    LOG_DIR = PROJECT_DIR / "logs"
    
    # Model settings
    WHISPER_MODEL = os.getenv("WHISPER_MODEL", "medium")
    LLM_MODEL = os.getenv("LLM_MODEL") or None  # None = auto-detect an installed model
    
    # Transcription settings
    TRANSCRIBE_LANGUAGE = "zh"  # Prefer Chinese by default
    ENABLE_TRANSCRIPT_CLEANING = os.getenv("ENABLE_TRANSCRIPT_CLEANING", "1").lower() in {"1", "true", "yes", "on"}
    MAX_TRANSCRIPT_LENGTH = 5000  # Maximum LLM input length before Notion write
    
    # Notion settings
    NOTION_TOKEN = os.getenv("NOTION_TOKEN")
    NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
    DISABLE_NOTION = os.getenv("DISABLE_NOTION", "0").lower() in {"1", "true", "yes", "on"}
    
    # Cleanup settings
    CLEANUP_AUDIO = True  # Delete the downloaded audio after processing


# ==================== Logging ====================

def setup_logging(log_level: str = "INFO") -> logging.Logger:
    """Set up the logging system."""
    Config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    
    logger = logging.getLogger("VideoPipeline")
    logger.setLevel(getattr(logging, log_level.upper()))
    
    # File logger
    log_file = Config.LOG_DIR / f"pipeline_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setFormatter(
        logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    )
    
    # Console logger
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(
        logging.Formatter('%(levelname)s: %(message)s')
    )
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger


# ==================== Main Pipeline ====================

class VideoPipeline:
    """End-to-end video processing workflow."""
    
    def __init__(self, logger: Optional[logging.Logger] = None, skip_notion: bool = False, disable_cleaning: bool = False):
        self.logger = logger or logging.getLogger("VideoPipeline")
        self.downloader = VideoDownloader(str(Config.DOWNLOAD_DIR))
        self.transcriber = WhisperTranscriber(model_size=Config.WHISPER_MODEL)
        self.transcript_cleaner = TranscriptCleaner(
            enabled=Config.ENABLE_TRANSCRIPT_CLEANING and not disable_cleaning
        )
        self.summarizer = Summarizer(model=Config.LLM_MODEL)
        
        # Optional Notion writer
        self.notion_writer = None
        notion_disabled = skip_notion or Config.DISABLE_NOTION
        if notion_disabled:
            self.logger.info("Notion writing disabled")
        elif Config.NOTION_TOKEN and Config.NOTION_DATABASE_ID:
            try:
                self.notion_writer = NotionWriter(
                    token=Config.NOTION_TOKEN,
                    database_id=Config.NOTION_DATABASE_ID
                )
                self.notion_writer.test_connection()
            except Exception as e:
                self.logger.warning(f"Notion initialization failed: {e}. Falling back to Mock mode.")
                self.notion_writer = MockNotionWriter()
        else:
            self.logger.info("Notion is not configured. Using Mock mode.")
            self.notion_writer = MockNotionWriter()
        
        # Checkpoint directory
        self.checkpoint_dir = Config.PROJECT_DIR / "checkpoints"
        self.checkpoint_dir.mkdir(exist_ok=True)
    
    def _get_checkpoint_path(self, url: str) -> Path:
        """Get the checkpoint file path."""
        import hashlib
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        return self.checkpoint_dir / f"{url_hash}.json"
    
    def _save_checkpoint(self, result: dict):
        """Save a processing checkpoint."""
        try:
            checkpoint_path = self._get_checkpoint_path(result['url'])
            with open(checkpoint_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            self.logger.info(f"💾 Checkpoint saved: {checkpoint_path.name}")
        except Exception as e:
            self.logger.warning(f"Failed to save checkpoint: {e}")
    
    def _load_checkpoint(self, url: str) -> Optional[dict]:
        """Load a processing checkpoint."""
        try:
            checkpoint_path = self._get_checkpoint_path(url)
            if checkpoint_path.exists():
                with open(checkpoint_path, 'r', encoding='utf-8') as f:
                    result = json.load(f)
                # Skip already completed tasks
                if result.get('status') == 'success':
                    self.logger.info("✓ Task already completed. Skipping.")
                    return None
                return result
        except Exception as e:
            self.logger.warning(f"Failed to load checkpoint: {e}")
        return None
    
    def run(self, url: str, skip_transcribe: bool = False, skip_summary: bool = False, resume: bool = True) -> dict:
        """
        Run the complete workflow.
        
        Args:
            url: Video URL
            skip_transcribe: Skip transcription (useful for testing)
            skip_summary: Skip summarization
            resume: Whether to resume from a checkpoint (default: True)
            
        Returns:
            A dictionary containing all processing results
        """
        self.logger.info("=" * 50)
        self.logger.info(f"🚀 Starting processing: {url}")
        self.logger.info("=" * 50)
        
        # Try to resume from a checkpoint
        result = self._load_checkpoint(url)
        
        if result and resume:
            self.logger.info("📂 Resuming from checkpoint...")
            # Restore existing data from the checkpoint
            if 'title' in result:
                self.logger.info(f"   Existing title: {result['title']}")
            if 'transcript' in result and result.get('steps', {}).get('transcribe', {}).get('status') == 'success':
                self.logger.info("   ✓ Transcription already completed")
            if 'summary' in result and result.get('steps', {}).get('summarize', {}).get('status') == 'success':
                self.logger.info("   ✓ Summary already completed")
        else:
            result = {
                'url': url,
                'status': 'pending',
                'start_time': datetime.now().isoformat(),
                'steps': {}
            }
        
        try:
            # ========== Step 1: Download audio or scrape image-text content ==========
            self.logger.info("\n📍 Step 1: Download or scrape content")
            self.logger.info("-" * 30)
            
            # Try downloading the video first; fall back to scraping if needed
            download_result = self.downloader.download_or_scrape(url)
            
            # Determine the content type
            content_type = download_result.get('type', 'video')
            
            if content_type == 'image_text':
                # Image-text note: use the scraped text content directly
                self.logger.info("📝 Detected image-text note")
                
                result['steps']['download'] = {
                    'status': 'success',
                    'type': 'image_text',
                    'platform': 'Xiaohongshu',
                    'title': download_result['title']
                }
                result['title'] = download_result['title']
                result['platform'] = 'Xiaohongshu'
                result['content_type'] = 'image_text'
                
                # Convert image-text content into transcript-like text
                text_content = download_result.get('description', '')
                if download_result.get('comments'):
                    text_content += '\n\n评论:\n'
                    for c in download_result['comments']:
                        text_content += f"- {c['user']}: {c['text']}\n"
                
                result['transcript'] = text_content
                result['image_text_data'] = download_result
                self._save_checkpoint(result)
                
                audio_path = None
            else:
                # Standard video content
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
            
            # ========== Step 2: Transcription (video content only) ==========
            if content_type == 'image_text':
                self.logger.info("⏭️ Image-text note detected, skipping speech transcription")
                result['steps']['transcribe'] = {'status': 'skipped', 'reason': 'image_text'}
            elif not skip_transcribe:
                self.logger.info("\n📍 Step 2: Speech to text (Whisper)")
                self.logger.info("-" * 30)
                
                # Retry on failure and automatically fall back to CPU
                max_retries = 3
                retry_delay = 5  # seconds
                last_error = None
                transcript_result = None
                
                for attempt in range(max_retries):
                    attempted_device = None
                    try:
                        # Auto-detect device (CUDA/CPU)
                        self.logger.info(f"🔄 Trying to load Whisper (auto-detect) - attempt {attempt + 1}/{max_retries}")
                        self.transcriber.load_model()
                        active_device = self.transcriber.last_device or 'unknown'
                        attempted_device = active_device
                        self.logger.info(f"🖥️ Whisper device selected: {active_device}")
                        
                        # Run transcription
                        transcript_result = self.transcriber.transcribe(
                            audio_path,
                            language=Config.TRANSCRIBE_LANGUAGE
                        )
                        
                        # Unload the model to free VRAM
                        self.transcriber.unload_model()
                        
                        result['steps']['transcribe'] = {
                            'status': 'success',
                            'text_length': len(transcript_result['text']),
                            'duration': transcript_result['duration'],
                            'language': transcript_result['language'],
                            'device': active_device
                        }
                        result['transcript'] = transcript_result['text']
                        self._save_checkpoint(result)
                        break  # Success: exit the retry loop
                        
                    except Exception as transcribe_error:
                        last_error = transcribe_error
                        attempted_device = attempted_device or self.transcriber.last_device or 'auto-detect'
                        self.logger.warning(f"⚠️ Transcription failed on {attempted_device}: {transcribe_error}")
                        self.transcriber.unload_model()

                        if attempted_device != 'cpu':
                            # Fall back to CPU explicitly to avoid retrying the same auto-detected path
                            try:
                                self.logger.info("🔄 Falling back to CPU...")
                                self.transcriber.load_model(device="cpu", compute_type="int8")
                                
                                transcript_result = self.transcriber.transcribe(
                                    audio_path,
                                    language=Config.TRANSCRIBE_LANGUAGE
                                )
                                
                                self.transcriber.unload_model()
                                
                                result['steps']['transcribe'] = {
                                    'status': 'success',
                                    'text_length': len(transcript_result['text']),
                                    'duration': transcript_result['duration'],
                                    'language': transcript_result['language'],
                                    'device': self.transcriber.last_device or 'cpu'
                                }
                                result['transcript'] = transcript_result['text']
                                self._save_checkpoint(result)
                                self.logger.info("✅ CPU fallback transcription succeeded!")
                                break
                                
                            except Exception as cpu_error:
                                last_error = cpu_error
                                self.logger.warning(f"⚠️ CPU fallback also failed: {cpu_error}")
                                self.transcriber.unload_model()
                        else:
                            self.logger.info("ℹ️ Auto-detect already selected CPU; skipping redundant CPU fallback")
                        
                        # Wait before retrying unless this was the last attempt
                        if attempt < max_retries - 1:
                            self.logger.info(f"⏳ Retrying in {retry_delay} seconds...")
                            import time
                            time.sleep(retry_delay)
                            retry_delay *= 2  # Exponential backoff
                
                else:
                    # All retry attempts failed
                    self.logger.error(f"❌ Transcription still failed after {max_retries} retries: {last_error}")
                    result['steps']['transcribe'] = {
                        'status': 'error',
                        'error': str(last_error)
                    }
                    raise last_error
            else:
                self.logger.info("⏭️ Skipping transcription step")
            
            # ========== Step 3: Clean up audio files ==========
            if Config.CLEANUP_AUDIO and audio_path:
                self.downloader.cleanup(audio_path)
            
            # ========== Step 4: Generate summary ==========
            if not skip_summary and 'transcript' in result:
                self.logger.info("\n📍 Step 3: Generate summary (LLM)")
                self.logger.info("-" * 30)

                transcript_for_summary = result['transcript']
                if self.transcript_cleaner.enabled:
                    self.logger.info("🧹 Cleaning transcript before summarization")
                    cleaned_transcript = self.transcript_cleaner.clean(transcript_for_summary)
                    result['steps']['clean_transcript'] = {
                        'status': 'success',
                        'enabled': True,
                        'original_length': len(transcript_for_summary),
                        'cleaned_length': len(cleaned_transcript),
                    }
                    transcript_for_summary = cleaned_transcript
                else:
                    result['steps']['clean_transcript'] = {
                        'status': 'skipped',
                        'reason': 'disabled'
                    }
                
                # Check whether Ollama is available
                if not self.summarizer.check_ollama():
                    raise Exception("Ollama is not running")
                
                # Check the model; still try running even if lookup fails
                if not self.summarizer.check_model_loaded():
                    self.logger.warning("Model check did not pass. Trying a direct call anyway...")
                
                # Generate the summary
                content_type = result.get('content_type', 'video')
                summary_result = self.summarizer.summarize(
                    transcript_for_summary,
                    max_length=Config.MAX_TRANSCRIPT_LENGTH,
                    content_type=content_type
                )
                
                # Release VRAM
                self.summarizer.unload_model()
                
                result['steps']['summarize'] = {
                    'status': 'success',
                    'model': self.summarizer.model
                }
                result['summary'] = summary_result['summary']
                result['key_points'] = summary_result['key_points']
                result['tags'] = summary_result['tags']
                result['category'] = summary_result.get('category', '未分类')
                result['sentiment'] = summary_result.get('sentiment', 'neutral')
                result['language'] = summary_result.get('language', 'zh')
                self._save_checkpoint(result)
            else:
                self.logger.info("⏭️ Skipping summary step")
            
            # ========== Step 5: Write to Notion ==========
            if self.notion_writer:
                self.logger.info("\n📍 Step 4: Write to Notion")
                self.logger.info("-" * 30)
                
                # Check for duplicates
                if self.notion_writer.check_duplicate(url):
                    self.logger.warning("⚠️ URL already exists. Skipping write.")
                    result['steps']['notion'] = {'status': 'skipped', 'reason': 'duplicate'}
                else:
                    # Prepare the payload
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
                self.logger.info("⏭️ Skipping Notion write")
            
            # ========== Complete ==========
            result['status'] = 'success'
            result['end_time'] = datetime.now().isoformat()
            
            elapsed = datetime.fromisoformat(result['end_time']) - datetime.fromisoformat(result['start_time'])
            result['elapsed_seconds'] = elapsed.total_seconds()
            
            self.logger.info("\n" + "=" * 50)
            self.logger.info("✅ Processing complete!")
            self.logger.info(f"⏱️ Total elapsed time: {elapsed.total_seconds():.1f} seconds")
            self.logger.info("=" * 50)
            
            # Remove the checkpoint after a successful run
            try:
                checkpoint_path = self._get_checkpoint_path(url)
                if checkpoint_path.exists():
                    checkpoint_path.unlink()
                    self.logger.info("🗑️ Checkpoint file removed")
            except:
                pass
            
            return result
            
        except Exception as e:
            result['status'] = 'error'
            result['error'] = str(e)
            result['end_time'] = datetime.now().isoformat()
            # Save a checkpoint for failed runs
            self._save_checkpoint(result)
            self.logger.error(f"❌ Processing failed: {e}")
            self.logger.info("💡 Re-running will continue from the saved checkpoint")
            raise


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Internet resource to knowledge + summary + storage workflow",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py "https://www.youtube.com/watch?v=xxx"
  python main.py "https://bilibili.com/video/xxx" --log-level DEBUG
  python main.py "url" --skip-summary
        """
    )
    
    parser.add_argument('url', nargs='?', help='Video URL')
    parser.add_argument('--log-level', default='INFO', 
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       help='Log level')
    parser.add_argument('--skip-transcribe', action='store_true',
                       help='Skip the transcription step')
    parser.add_argument('--skip-summary', action='store_true',
                       help='Skip the summary step')
    parser.add_argument('--skip-notion', action='store_true',
                       help='Skip writing to Notion')
    parser.add_argument('--disable-cleaning', action='store_true',
                       help='Disable transcript cleaning before summarization')
    parser.add_argument('--no-cleanup', action='store_true',
                       help='Do not delete temporary audio files')
    parser.add_argument('--no-resume', action='store_true',
                       help='Start fresh instead of resuming from a checkpoint')
    
    args = parser.parse_args()
    
    if not args.url:
        parser.print_help()
        print("\nPlease provide a video URL")
        sys.exit(1)
    
    # Configure logging
    logger = setup_logging(args.log_level)
    
    # Update runtime configuration
    Config.CLEANUP_AUDIO = not args.no_cleanup
    Config.DISABLE_NOTION = Config.DISABLE_NOTION or args.skip_notion
    
    # Create the pipeline
    pipeline = VideoPipeline(
        logger,
        skip_notion=args.skip_notion,
        disable_cleaning=args.disable_cleaning,
    )
    
    # Run the workflow
    try:
        result = pipeline.run(
            url=args.url,
            skip_transcribe=args.skip_transcribe,
            skip_summary=args.skip_summary,
            resume=not args.no_resume
        )
        
        # Print the JSON result
        print("\n📊 Processing result:")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
    except Exception as e:
        logger.error(f"Workflow execution failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
