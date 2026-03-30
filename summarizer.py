# -*- coding: utf-8 -*-
"""
🧠 Summarizer Module
Generate summaries with a local Ollama LLM
"""

import gc
import json
import torch
import ollama
from typing import Optional, Dict, List


class Summarizer:
    """Local LLM-based summarizer."""

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
    
    # Model keywords ordered by priority (higher priority appears first)
    # Format: (keyword list, display name, vram)
    MODEL_PRIORITY = [
        (["qwen3",   "4b"],        "qwen3 4B",     "~2.5GB"),
        (["qwen2.5", "3b"],        "qwen2.5 3B",   "~2GB"),
        (["phi3"],                 "phi3",         "~2GB"),
        (["phi"],                  "phi",          "~2GB"),
        (["qwen2.5", "7b"],        "qwen2.5 7B",   "~4-5GB"),
        (["qwen2.5", "14b"],       "qwen2.5 14B",  "~9GB"),
        (["qwen3",   "8b"],        "qwen3 8B",     "~5GB"),
        (["qwen2.5vl", "7b"],      "qwen2.5vl 7B", "~6GB"),
        (["llama3",  "3b"],        "llama3 3B",    "~2GB"),
        (["llama3",  "8b"],        "llama3 8B",    "~5GB"),
        (["mistral", "7b"],        "mistral 7B",   "~4GB"),
    ]

    # Fallback model used when auto-detection fails
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

    # Prompt for image-text content analysis
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
        """Automatically select the best available Ollama model."""
        # Check environment-configured models first
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

            print(f"📋 Installed models: {installed}")
            
            # Prefer the primary model defined in the environment
            if primary_model and primary_model != "auto":
                for name in installed:
                    if primary_model.lower() in name.lower():
                        print(f"✅ Using configured primary model: {name}")
                        return name
                # If the primary model is unavailable, try the fallback model
                if fallback_model:
                    for name in installed:
                        if fallback_model.lower() in name.lower():
                            print(f"⚠️ Primary model not installed, using fallback model: {name}")
                            return name
                    # Neither configured model is installed
                    print("⚠️ Neither the primary nor fallback model is installed. Selecting automatically.")
            
            # Automatic selection based on the priority list
            for keywords, label, _ in cls.MODEL_PRIORITY:
                for name in installed:
                    name_lower = name.lower()
                    if all(kw in name_lower for kw in keywords):
                        print(f"✅ Automatically selected model: {name} ({label})")
                        return name

            # If nothing matches the priority list, use the first installed model
            print(f"⚠️ No priority-list match found. Using the first installed model: {installed[0]}")
            return installed[0]

        except Exception as e:
            print(f"⚠️ Auto-detecting the model failed: {e}. Using default: {fallback_model or cls.FALLBACK_MODEL}")
            return fallback_model or cls.FALLBACK_MODEL

    def __init__(self, model: Optional[str] = None):
        """
        Initialize the summarizer.
        
        Args:
            model: Ollama model name; auto-detected when omitted
        """
        self.model = model or self.detect_model()

    def _build_prompt(self, system_prompt: str, content_label: str, transcript: str) -> str:
        """Build a shared prompt that requires JSON-only output."""
        return (
            f"{system_prompt}\n\n"
            f"以下是{content_label}:\n\n{transcript}\n\n"
            "请严格返回一个 JSON 对象，不要附加解释、前后缀文本或 markdown 代码块。"
        )

    def _normalize_result(self, result: Dict) -> Dict:
        """Normalize model output to avoid missing-field errors upstream."""
        return {
            'summary': result.get('summary', ''),
            'key_points': result.get('key_points', []),
            'tags': result.get('tags', []),
            'category': result.get('category', '未分类'),
            'sentiment': result.get('sentiment', 'neutral'),
            'language': result.get('language', 'zh'),
        }

    def _parse_json_response(self, response_text: str) -> Dict:
        """Extract the first valid JSON object from the model response."""
        text = response_text.strip()
        if not text:
            raise ValueError("The model returned an empty response")

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

        raise ValueError("Unable to extract a valid JSON object from the response")

    def _generate_structured(self, model: str, prompt_text: str) -> Dict:
        """Prefer Ollama's structured-output support when available."""
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
        """Fall back to plain text and extract JSON manually when needed."""
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
        """Check whether the Ollama service is available."""
        try:
            ollama.list()
            return True
        except Exception as e:
            print(f"❌ Ollama connection failed: {e}")
            print("💡 Make sure Ollama is running: ollama serve")
            return False
    
    def check_model_loaded(self) -> bool:
        """Check whether the target model has already been downloaded."""
        try:
            models = ollama.list()
            # Support both old and new ollama client response shapes
            raw = getattr(models, 'models', None) or models.get('models', [])
            model_names = []
            for m in raw:
                name = getattr(m, 'model', None) or getattr(m, 'name', None) or m.get('model', '') or m.get('name', '')
                if name:
                    model_names.append(name)
            
            print(f"📋 Installed models: {model_names}")
            
            # Prefer exact matches, then fall back to loose matching
            if self.model in model_names:
                return True
            base_model = self.model.split(':')[0].split('/')[-1].lower()
            for name in model_names:
                if base_model in name.lower():
                    return True
            
            print(f"⚠️ Model {self.model} is not in the installed model list")
            print(f"📥 Run: ollama pull {self.model}")
            return False
        except Exception as e:
            print(f"❌ Failed to check model availability: {e}")
            return False
    
    def load_model(self):
        """Warm up the model (optional)."""
        print(f"🔥 Warming up model: {self.model}")
        try:
            # Simple warm-up request
            ollama.generate(
                model=self.model,
                prompt="你好",
                options={"num_predict": 1}
            )
            print("✅ Model warm-up complete")
        except Exception as e:
            print(f"⚠️ Model warm-up failed: {e}")
        
        # Print current VRAM usage
        if torch.cuda.is_available():
            allocated = torch.cuda.memory_allocated() / 1024**3
            print(f"📊 VRAM usage: {allocated:.2f}GB")
    
    def summarize(self, transcript: str, max_length: int = 2000, content_type: str = 'video') -> Dict:
        """
        Generate a summary.
        
        Args:
            transcript: Transcript text
            max_length: Maximum input length in characters
            content_type: Content type ('video' or 'image_text')
            
        Returns:
            A dictionary containing summary, key points, tags, and related fields
        """
        # Truncate overly long text
        if len(transcript) > max_length:
            print(f"📄 Text is too long ({len(transcript)} chars). Truncating to {max_length} chars")
            transcript = transcript[:max_length] + "..."
        
        # Select the appropriate prompt template
        if content_type == 'image_text':
            system_prompt = self.IMAGE_TEXT_PROMPT
            content_label = "图文笔记内容"
        else:
            system_prompt = self.SYSTEM_PROMPT
            content_label = "视频转录文本"
        
        print(f"🧠 Starting summary generation (model: {self.model}, type: {content_type})")

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
                print(f"✅ Summary generation complete (structured output: {model_name})")
                return self._normalize_result(result)
            except Exception as structured_error:
                errors.append(f"{model_name} structured: {structured_error}")
                print(f"⚠️ Structured output failed for model {model_name}: {structured_error}")

            try:
                result = self._generate_unstructured(model_name, prompt_text)
                print(f"✅ Summary generation complete (JSON extracted from text: {model_name})")
                return self._normalize_result(result)
            except Exception as unstructured_error:
                errors.append(f"{model_name} text: {unstructured_error}")
                print(f"⚠️ JSON extraction from text failed for model {model_name}: {unstructured_error}")

        try:
            print("⚠️ Structured output and JSON extraction both failed. Using fallback summarization.")
            return self._fallback_summarize(transcript)
        except Exception as fallback_error:
            errors.append(f"fallback summary: {fallback_error}")
            raise Exception("Summary generation failed: " + " | ".join(errors))
    
    def _fallback_summarize(self, transcript: str) -> Dict:
        """Fallback summarization method used when JSON parsing fails."""
        print("🔄 Using fallback summarization...")
        
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
            raise Exception(f"Fallback summarization also failed: {str(e)}")
    
    def unload_model(self):
        """Release VRAM by clearing caches."""
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
        print("✅ LLM VRAM released")
    
    @staticmethod
    def get_available_models() -> List[Dict]:
        """Get the list of available Ollama models."""
        try:
            result = ollama.list()
            return result.get('models', [])
        except:
            return []


def estimate_vram(model: str) -> str:
    """Estimate VRAM usage for a model."""
    configs = Summarizer.ALT_MODELS
    return configs.get(model, {}).get('vram', '未知')


if __name__ == "__main__":
    # Smoke test
    summarizer = Summarizer()
    
    if not summarizer.check_ollama():
        print("❌ Ollama is not running")
        exit(1)
    
    if not summarizer.check_model_loaded():
        exit(1)
    
    # Test summary generation
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
