# -*- coding: utf-8 -*-
"""
🎙 Whisper Transcriber Module
Run local speech-to-text with faster-whisper
"""

import gc
import torch
from typing import Optional, Dict
from faster_whisper import WhisperModel


class WhisperTranscriber:
    """Local Whisper transcriber."""
    
    # Model defaults: the small model is a good fit for 8GB VRAM
    MODEL_SIZE = "small"
    COMPUTE_TYPE = "float16"  # float16 uses about 2GB on an RTX 5060
    
    def __init__(self, model_path: Optional[str] = None, model_size: Optional[str] = None):
        """
        Initialize the transcriber.
        
        Args:
            model_path: Custom model download path (optional)
            model_size: Whisper model size override
        """
        self.model = None
        self.model_path = model_path
        self.model_size = model_size or self.MODEL_SIZE
    
    def load_model(self, device: str = "cuda", compute_type: Optional[str] = None):
        """
        Load the Whisper model.
        
        Args:
            device: Execution device ("cuda" or "cpu")
            compute_type: Compute type (optional; auto-selected by device when omitted)
        """
        if self.model is not None:
            print("✅ 模型已加载")
            return
        
        # Select the compute type automatically based on the device
        if compute_type is None:
            compute_type = "float16" if device == "cuda" else "int8"
        
        print(f"📥 加载 Whisper {self.model_size} 模型...")
        print(f"🖥️ 设备: {device}")
        print(f"📊 计算类型: {compute_type}")
        
        try:
            self.model = WhisperModel(
                self.model_size,
                device=device,
                compute_type=compute_type,
                download_root=self.model_path
            )
            print("✅ 模型加载完成")
            
            # Print estimated VRAM usage
            self._print_vram_usage()
            
        except Exception as e:
            print(f"❌ 模型加载失败: {e}")
            raise
    
    def _print_vram_usage(self):
        """Print estimated VRAM usage."""
        if torch.cuda.is_available():
            allocated = torch.cuda.memory_allocated() / 1024**3
            reserved = torch.cuda.memory_reserved() / 1024**3
            print(f"📊 显存占用: {allocated:.2f}GB (已分配) / {reserved:.2f}GB (已预留)")
    
    def transcribe(
        self,
        audio_path: str,
        language: Optional[str] = None,
        task: str = "transcribe"
    ) -> Dict:
        """
        Transcribe an audio file.
        
        Args:
            audio_path: Audio file path
            language: Language code (None = auto-detect)
            task: "transcribe" or "translate"
            
        Returns:
            A dictionary containing text, segments, and language metadata
        """
        if self.model is None:
            self.load_model()
        
        print(f"🎙️ 开始转录: {audio_path}")
        
        # Auto-detect the language, with Chinese preferred by default
        if language is None:
            language = "zh"  # Default to Chinese
        
        try:
            # Run transcription
            segments, info = self.model.transcribe(
                audio_path,
                language=language,
                task=task,
                beam_size=5,
                vad_filter=True,  # Voice activity detection
                vad_parameters=dict(min_silence_duration_ms=500)
            )
            
            # Collect all transcription segments
            transcript_segments = []
            full_text = []
            
            print("📝 转录进度:")
            for segment in segments:
                text = segment.text.strip()
                transcript_segments.append({
                    'start': segment.start,
                    'end': segment.end,
                    'text': text
                })
                full_text.append(text)
                print(f"  [{segment.start:.1f}s - {segment.end:.1f}s] {text}")
            
            result = {
                'text': ' '.join(full_text),
                'segments': transcript_segments,
                'language': info.language if hasattr(info, 'language') else language,
                'duration': info.duration if hasattr(info, 'duration') else 0,
            }
            
            print(f"✅ 转录完成! 时长: {result['duration']:.1f}秒")
            print(f"📊 文本长度: {len(result['text'])} 字符")
            
            return result
            
        except Exception as e:
            raise Exception(f"转录失败: {str(e)}")
    
    def unload_model(self):
        """Unload the model and release VRAM."""
        if self.model is not None:
            print("🔄 释放 Whisper 模型...")
            del self.model
            self.model = None
            
            # Force garbage collection
            gc.collect()
            
            # Clear the CUDA cache
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.synchronize()
            
            print("✅ 显存已释放")
            self._print_vram_usage()
    
    def __enter__(self):
        """Context manager entry point."""
        self.load_model()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit point that automatically releases VRAM."""
        self.unload_model()


def get_vram_requirement(model_size: str = "small") -> Dict:
    """
    Get the estimated VRAM requirement for each model size.
    
    Returns:
        A dictionary describing VRAM requirements
    """
    requirements = {
        "tiny": {"vram": "~1GB", "speed": "最快", "accuracy": "最低"},
        "base": {"vram": "~1GB", "speed": "快", "accuracy": "基础"},
        "small": {"vram": "~2GB", "speed": "中等", "accuracy": "良好"},
        "medium": {"vram": "~5GB", "speed": "较慢", "accuracy": "很好"},
        "large": {"vram": "~10GB", "speed": "慢", "accuracy": "最佳"},
    }
    return requirements.get(model_size, requirements["small"])


if __name__ == "__main__":
    # Smoke test transcription
    import sys
    
    if len(sys.argv) < 2:
        print("用法: python transcriber.py <audio_file>")
        sys.exit(1)
    
    audio_file = sys.argv[1]
    
    with WhisperTranscriber() as transcriber:
        result = transcriber.transcribe(audio_file)
        print("\n=== 转录结果 ===")
        print(result['text'][:500] + "..." if len(result['text']) > 500 else result['text'])
