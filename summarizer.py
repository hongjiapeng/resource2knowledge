# -*- coding: utf-8 -*-
"""
🧠 Summarizer Module
使用 Ollama 本地 LLM 生成摘要
"""

import gc
import json
import torch
import ollama
from typing import Optional, Dict, List


class Summarizer:
    """本地 LLM 摘要生成器"""

    RESPONSE_SCHEMA = {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "key_points": {
                "type": "array",
                "items": {"type": "string"}
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"}
            },
            "category": {"type": "string"},
            "sentiment": {"type": "string"},
            "language": {"type": "string"}
        },
        "required": ["summary", "key_points", "tags", "category", "sentiment", "language"]
    }
    
    # 按优先级排列的模型关键词（越靠前越优先）
    # 格式：(匹配关键词列表, 显示名, vram)
    MODEL_PRIORITY = [
        (["qwen2.5", "7b"],        "qwen2.5 7B",   "~4-5GB"),
        (["qwen2.5", "14b"],       "qwen2.5 14B",  "~9GB"),
        (["qwen2.5", "3b"],        "qwen2.5 3B",   "~2GB"),
        (["qwen3",   "8b"],        "qwen3 8B",     "~5GB"),
        (["qwen3",   "4b"],        "qwen3 4B",     "~3GB"),
        (["llama3",  "8b"],        "llama3 8B",    "~5GB"),
        (["llama3",  "3b"],        "llama3 3B",    "~2GB"),
        (["mistral", "7b"],        "mistral 7B",   "~4GB"),
        (["phi3"],                 "phi3",         "~2GB"),
        (["phi"],                  "phi",          "~2GB"),
    ]

    # 兜底默认（无法自动检测时使用）
    FALLBACK_MODEL = "qwen2.5:7b-instruct-q4_K_M"
    
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
- 直接输出 JSON，不要其他内容
- 不要输出 markdown 代码块"""

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
- 直接输出 JSON，不要其他内容
- 不要输出 markdown 代码块"""

    @classmethod
    def detect_model(cls) -> str:
        """从已安装的 Ollama 模型中自动选择最优模型"""
        # 先尝试环境变量中的模型
        import os
        primary_model = os.getenv("LLM_MODEL")
        fallback_model = os.getenv("LLM_MODEL_FALLBACK")
        
        try:
            raw = getattr(ollama.list(), 'models', None) or ollama.list().get('models', [])
            installed = []
            for m in raw:
                name = (getattr(m, 'model', None) or getattr(m, 'name', None)
                        or m.get('model', '') or m.get('name', ''))
                if name:
                    installed.append(name)

            if not installed:
                return fallback_model or cls.FALLBACK_MODEL

            print(f"📋 已安装模型: {installed}")
            
            # 优先使用环境变量中指定的主模型
            if primary_model and primary_model != "auto":
                for name in installed:
                    if primary_model.lower() in name.lower():
                        print(f"✅ 使用配置的主模型: {name}")
                        return name
                # 主模型未安装，尝试备用模型
                if fallback_model:
                    for name in installed:
                        if fallback_model.lower() in name.lower():
                            print(f"⚠️ 主模型未安装，使用备用模型: {name}")
                            return name
                    # 备用模型也未安装
                    print(f"⚠️ 主模型和备用模型都未安装，自动选择")
            
            # 自动选择 - 按优先级逐一匹配
            for keywords, label, _ in cls.MODEL_PRIORITY:
                for name in installed:
                    name_lower = name.lower()
                    if all(kw in name_lower for kw in keywords):
                        print(f"✅ 自动选择模型: {name} ({label})")
                        return name

            # 没有匹配到优先级列表，直接用第一个已安装的
            print(f"⚠️ 未匹配优先级列表，使用已安装的第一个模型: {installed[0]}")
            return installed[0]

        except Exception as e:
            print(f"⚠️ 自动检测模型失败: {e}，使用默认: {fallback_model or cls.FALLBACK_MODEL}")
            return fallback_model or cls.FALLBACK_MODEL

    def __init__(self, model: Optional[str] = None):
        """
        初始化摘要生成器
        
        Args:
            model: Ollama 模型名称，不传则自动检测
        """
        self.model = model or self.detect_model()

    def _build_prompt(self, system_prompt: str, content_label: str, transcript: str) -> str:
        """构建统一 prompt，明确要求仅返回 JSON。"""
        return (
            f"{system_prompt}\n\n"
            f"以下是{content_label}:\n\n{transcript}\n\n"
            "请严格返回一个 JSON 对象，不要附加解释、前后缀文本或 markdown 代码块。"
        )

    def _normalize_result(self, result: Dict) -> Dict:
        """标准化模型返回结构，避免缺字段导致上层报错。"""
        return {
            'summary': result.get('summary', ''),
            'key_points': result.get('key_points', []),
            'tags': result.get('tags', []),
            'category': result.get('category', '未分类'),
            'sentiment': result.get('sentiment', 'neutral'),
            'language': result.get('language', 'zh'),
        }

    def _parse_json_response(self, response_text: str) -> Dict:
        """从模型响应中提取第一个合法 JSON 对象。"""
        text = response_text.strip()
        if not text:
            raise ValueError("模型返回为空")

        decoder = json.JSONDecoder()
        for index, char in enumerate(text):
            if char != '{':
                continue
            try:
                parsed, _ = decoder.raw_decode(text[index:])
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                continue

        raise ValueError("无法从响应中提取合法 JSON 对象")

    def _generate_structured(self, model: str, prompt_text: str) -> Dict:
        """优先使用 Ollama 的结构化输出能力。"""
        response = ollama.generate(
            model=model,
            prompt=prompt_text,
            format=self.RESPONSE_SCHEMA,
            options={
                "temperature": 0,
                "num_predict": 1000,
            }
        )
        return self._parse_json_response(response.response)

    def _generate_unstructured(self, model: str, prompt_text: str) -> Dict:
        """结构化输出失败时，退回纯文本并自行提取 JSON。"""
        response = ollama.generate(
            model=model,
            prompt=prompt_text,
            options={
                "temperature": 0,
                "num_predict": 1000,
            }
        )
        return self._parse_json_response(response.response)
    
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
            # 兼容新旧版 ollama 库：对象属性 or 字典键
            raw = getattr(models, 'models', None) or models.get('models', [])
            model_names = []
            for m in raw:
                name = getattr(m, 'model', None) or getattr(m, 'name', None) or m.get('model', '') or m.get('name', '')
                if name:
                    model_names.append(name)
            
            print(f"📋 已安装模型: {model_names}")
            
            # 精确匹配优先，再宽松匹配
            if self.model in model_names:
                return True
            base_model = self.model.split(':')[0].split('/')[-1].lower()
            for name in model_names:
                if base_model in name.lower():
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

        import os
        fallback_model = os.getenv("LLM_MODEL_FALLBACK")
        prompt_text = self._build_prompt(system_prompt, content_label, transcript)

        model_candidates = [self.model]
        if fallback_model and fallback_model not in model_candidates:
            model_candidates.append(fallback_model)

        errors = []

        for model_name in model_candidates:
            self.model = model_name

            try:
                result = self._generate_structured(model_name, prompt_text)
                print(f"✅ 摘要生成完成 (结构化输出: {model_name})")
                return self._normalize_result(result)
            except Exception as structured_error:
                errors.append(f"{model_name} structured: {structured_error}")
                print(f"⚠️ 模型 {model_name} 结构化输出失败: {structured_error}")

            try:
                result = self._generate_unstructured(model_name, prompt_text)
                print(f"✅ 摘要生成完成 (文本提取 JSON: {model_name})")
                return self._normalize_result(result)
            except Exception as unstructured_error:
                errors.append(f"{model_name} text: {unstructured_error}")
                print(f"⚠️ 模型 {model_name} 文本提取 JSON 失败: {unstructured_error}")

        try:
            print("⚠️ 结构化输出和 JSON 提取均失败，使用备用摘要方法")
            return self._fallback_summarize(transcript)
        except Exception as fallback_error:
            errors.append(f"fallback summary: {fallback_error}")
            raise Exception("摘要生成失败: " + " | ".join(errors))
    
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
