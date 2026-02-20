# -*- coding: utf-8 -*-
"""
🎙 Whisper Transcriber Module
使用 faster-whisper 进行本地语音转文本
"""

import gc
import torch
from typing import Optional, Dict
from faster_whisper import WhisperModel


class WhisperTranscriber:
    """本地 Whisper 转录器"""
    
    # 模型配置 - small 模型适合 8GB 显存
    MODEL_SIZE = "small"
    COMPUTE_TYPE = "float16"  # float16 在 RTX 5060 上约占用 2GB
    
    def __init__(self, model_path: Optional[str] = None):
        """
        初始化转录器
        
        Args:
            model_path: 自定义模型路径 (可选)
        """
        self.model = None
        self.model_path = model_path
    
    def load_model(self, device: str = "cuda"):
        """
        加载 Whisper 模型到 GPU
        
        Args:
            device: 运行设备 ("cuda" 或 "cpu")
        """
        if self.model is not None:
            print("✅ 模型已加载")
            return
        
        print(f"📥 加载 Whisper {self.MODEL_SIZE} 模型...")
        print(f"🖥️ 设备: {device}")
        print(f"📊 计算类型: {self.COMPUTE_TYPE}")
        
        try:
            self.model = WhisperModel(
                self.MODEL_SIZE,
                device=device,
                compute_type=self.COMPUTE_TYPE,
                download_root=self.model_path
            )
            print("✅ 模型加载完成")
            
            # 打印显存占用预估
            self._print_vram_usage()
            
        except Exception as e:
            print(f"❌ 模型加载失败: {e}")
            raise
    
    def _print_vram_usage(self):
        """打印显存占用预估"""
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
        转录音频文件
        
        Args:
            audio_path: 音频文件路径
            language: 语言代码 (None = 自动检测)
            task: "transcribe" 或 "translate"
            
        Returns:
            包含文本、段落、语言信息的字典
        """
        if self.model is None:
            self.load_model()
        
        print(f"🎙️ 开始转录: {audio_path}")
        
        # 自动检测语言 (默认优先中文)
        if language is None:
            language = "zh"  # 默认中文
        
        try:
            # 执行转录
            segments, info = self.model.transcribe(
                audio_path,
                language=language,
                task=task,
                beam_size=5,
                vad_filter=True,  # 语音活动检测
                vad_parameters=dict(min_silence_duration_ms=500)
            )
            
            # 收集所有段落
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
        """卸载模型并释放显存"""
        if self.model is not None:
            print("🔄 释放 Whisper 模型...")
            del self.model
            self.model = None
            
            # 强制垃圾回收
            gc.collect()
            
            # 清空 CUDA 缓存
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.synchronize()
            
            print("✅ 显存已释放")
            self._print_vram_usage()
    
    def __enter__(self):
        """上下文管理器入口"""
        self.load_model()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口 - 自动释放显存"""
        self.unload_model()


def get_vram_requirement(model_size: str = "small") -> Dict:
    """
    获取各模型的显存需求预估
    
    Returns:
        显存需求字典
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
    # 测试转录
    import sys
    
    if len(sys.argv) < 2:
        print("用法: python transcriber.py <audio_file>")
        sys.exit(1)
    
    audio_file = sys.argv[1]
    
    with WhisperTranscriber() as transcriber:
        result = transcriber.transcribe(audio_file)
        print("\n=== 转录结果 ===")
        print(result['text'][:500] + "..." if len(result['text']) > 500 else result['text'])
