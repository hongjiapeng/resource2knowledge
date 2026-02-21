# -*- coding: utf-8 -*-
"""
🧠 Summarizer Module
使用 Ollama 本地 LLM 生成摘要
"""

import gc
import torch
import ollama
from typing import Optional, Dict, List


class Summarizer:
    """本地 LLM 摘要生成器"""
    
    # 推荐模型配置 (适合 8GB 显存)
    DEFAULT_MODEL = "qwen2.5:7b-instruct-q4_K_M"
    
    # 备选模型
    ALT_MODELS = {
        "qwen2.5:7b-instruct-q4_K_M": {"vram": "~4-5GB", "speed": "中等", "quality": "优秀"},
        "llama3.2:3b-instruct-q4_K_M": {"vram": "~2-3GB", "speed": "快", "quality": "良好"},
        "phi3.5:3.8b-mini-instruct-q4_K_M": {"vram": "~2GB", "speed": "很快", "quality": "一般"},
        "mistral:7b-instruct-q4_K_M": {"vram": "~4GB", "speed": "中等", "quality": "良好"},
    }
    
    SYSTEM_PROMPT = """你是一个专业的视频内容分析师。你的任务是对视频 transcript（转录文本）进行总结。

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
- 直接输出 JSON，不要其他内容"""

    # 图文内容分析 prompt
    IMAGE_TEXT_PROMPT = """你是一个专业的小红书内容分析师。你的任务是对图文笔记内容进行分析总结。

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
- 直接输出 JSON，不要其他内容"""

    def __init__(self, model: Optional[str] = None):
        """
        初始化摘要生成器
        
        Args:
            model: Ollama 模型名称
        """
        self.model = model or self.DEFAULT_MODEL
    
    def check_ollama(self) -> bool:
        """检查 Ollama 服务是否可用"""
        try:
            ollama.list()
            return True
        except Exception as e:
            print(f"❌ Ollama 连接失败: {e}")
            print("💡 请确保 Ollama 已启动: ollama serve")
            return False
    
    def check_model_loaded(self) -> bool:
        """检查模型是否已下载"""
        try:
            models = ollama.list()
            model_names = [m.get('name', '') for m in models.get('models', [])]
            
            print(f"📋 已安装模型: {model_names}")
            
            # 处理模型名称格式 - 更宽松的匹配
            base_model = self.model.split(':')[0]
            for name in model_names:
                if base_model.lower() in name.lower():
                    return True
            
            print(f"⚠️ 模型 {self.model} 未在列表中")
            print(f"📥 请运行: ollama pull {self.model}")
            return False
        except Exception as e:
            print(f"❌ 检查模型失败: {e}")
            return False
    
    def load_model(self):
        """预热模型 (可选)"""
        print(f"🔥 预热模型: {self.model}")
        try:
            # 简单的预热请求
            ollama.generate(
                model=self.model,
                prompt="你好",
                options={"num_predict": 1}
            )
            print("✅ 模型预热完成")
        except Exception as e:
            print(f"⚠️ 预热失败: {e}")
        
        # 打印显存占用
        if torch.cuda.is_available():
            allocated = torch.cuda.memory_allocated() / 1024**3
            print(f"📊 显存占用: {allocated:.2f}GB")
    
    def summarize(self, transcript: str, max_length: int = 2000, content_type: str = 'video') -> Dict:
        """
        生成摘要
        
        Args:
            transcript: 转录文本
            max_length: 最大输入长度 (字符)
            content_type: 内容类型 ('video' 或 'image_text')
            
        Returns:
            包含 summary, key_points, tags 等的字典
        """
        # 截断过长的文本
        if len(transcript) > max_length:
            print(f"📄 文本过长 ({len(transcript)} 字符)，截断至 {max_length} 字符")
            transcript = transcript[:max_length] + "..."
        
        # 选择合适的 prompt
        if content_type == 'image_text':
            system_prompt = self.IMAGE_TEXT_PROMPT
            content_label = "图文笔记内容"
        else:
            system_prompt = self.SYSTEM_PROMPT
            content_label = "视频转录文本"
        
        print(f"🧠 开始生成摘要 (模型: {self.model}, 类型: {content_type})")
        
        try:
            response = ollama.generate(
                model=self.model,
                prompt=f"{system_prompt}\n\n以下是{content_label}:\n\n{transcript}",
                format="json",
                options={
                    "temperature": 0.3,  # 低温度，更确定性的输出
                    "num_predict": 1000,
                }
            )
            
            import json
            result = json.loads(response.response)
            
            print("✅ 摘要生成完成")
            return {
                'summary': result.get('summary', ''),
                'key_points': result.get('key_points', []),
                'tags': result.get('tags', []),
                'category': result.get('category', '未分类'),
                'sentiment': result.get('sentiment', 'neutral'),
                'language': result.get('language', 'zh'),
            }
            
        except json.JSONDecodeError as e:
            print(f"⚠️ JSON 解析失败，使用备用方法")
            return self._fallback_summarize(transcript)
        except Exception as e:
            raise Exception(f"摘要生成失败: {str(e)}")
    
    def _fallback_summarize(self, transcript: str) -> Dict:
        """备用摘要方法 (当 JSON 解析失败时)"""
        print("🔄 使用备用摘要方法...")
        
        try:
            response = ollama.generate(
                model=self.model,
                prompt=f"请用中文总结以下视频转录内容，提取3-5个要点:\n\n{transcript[:1500]}",
                options={"temperature": 0.3, "num_predict": 500}
            )
            
            return {
                'summary': response.response,
                'key_points': [],
                'tags': [],
                'category': '未分类',
                'sentiment': 'neutral',
                'language': 'zh',
            }
        except Exception as e:
            raise Exception(f"备用摘要也失败: {str(e)}")
    
    def unload_model(self):
        """释放显存 (通过清空缓存)"""
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
        print("✅ LLM 显存已释放")
    
    @staticmethod
    def get_available_models() -> List[Dict]:
        """获取可用的 Ollama 模型列表"""
        try:
            result = ollama.list()
            return result.get('models', [])
        except:
            return []


def estimate_vram(model: str) -> str:
    """预估模型显存占用"""
    configs = Summarizer.ALT_MODELS
    return configs.get(model, {}).get('vram', '未知')


if __name__ == "__main__":
    # 测试
    summarizer = Summarizer()
    
    if not summarizer.check_ollama():
        print("❌ Ollama 未运行")
        exit(1)
    
    if not summarizer.check_model_loaded():
        exit(1)
    
    # 测试摘要
    test_transcript = """
    今天我们来聊聊如何入门机器学习。机器学习是人工智能的一个重要分支，
    它让计算机能够从数据中学习，而不需要明确的编程指令。
    首先，我们需要了解基本概念：监督学习、无监督学习和强化学习。
    监督学习是最常见的方式，比如分类和回归问题。
    无监督学习用于聚类和降维，强化学习则用于游戏和机器人控制。
    推荐初学者从 Python 基础开始，学习 NumPy、Pandas 等库，
    然后逐步学习 scikit-learn，最后深入深度学习框架。
    """
    
    result = summarizer.summarize(test_transcript)
    import json
    print(json.dumps(result, indent=2, ensure_ascii=False))
