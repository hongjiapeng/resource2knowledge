# 🌐 ClipVault - Your Personal Internet Knowledge Archive

> **Local AI-powered tool** to collect web content (video/image-text), transcribe, summarize, and archive to Notion/CSV. **No API fees required.**

[English](README.md) | [简体中文](README.zh-CN.md)

[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![CUDA](https://img.shields.io/badge/CUDA-12.x-76B900.svg?logo=nvidia)](https://developer.nvidia.com/cuda-downloads)

---

## ✨ Features

Transform internet content into searchable personal knowledge base:

- 📥 **Multi-platform Support**: YouTube, Bilibili, Xiaohongshu (video + image-text posts)
- 🎙️ **Local Transcription**: Whisper-powered audio-to-text (no API fees)
- 🤖 **AI Summarization**: Ollama LLM generates key insights (runs locally)
- 🧹 **Optional Transcript Cleaning**: Low-risk cleanup improves noisy ASR output before summarization
- 💾 **Flexible Export**: Save to Notion database or CSV/Excel
- 🔌 **Automation Ready**: OpenClaw skill integration for workflow automation
- ⚡ **Checkpoint Resume**: Auto-resume from interruptions

---

## 📋 Pipeline Overview

| Step | Module | Technology | VRAM Usage |
|------|--------|------------|----------|
| 1. Download | providers.download | yt-dlp | - |
| 2. Transcribe | providers.transcription | faster-whisper (configurable, default: small) | ~2GB |
| 3. Clean | domain.transcript_cleaner | Regex + heuristics (optional) | - |
| 4. Summarize | providers.summarization | Ollama qwen3.5 with qwen2.5 fallback | ~4-7GB |
| 5. Archive | providers.storage | Notion API / JSON local | - |

**Total VRAM**: ~6-9GB when using NVIDIA GPU acceleration (sequential execution)

On CPU-only systems, the pipeline still works but transcription and summarization will be slower.

---

## 🖥️ System Requirements

- **OS**: Windows 11 / Linux / macOS
- **Python**: 3.9+
- **RAM**: 16GB+ recommended (32GB optimal)
- **Optional GPU acceleration**: NVIDIA GPU with 8GB+ VRAM (e.g., RTX 4060/5060, RTX 3070)
- **CUDA**: 12.x if you want GPU acceleration

The transcription step auto-detects the runtime device:

- **NVIDIA + CUDA available**: uses `cuda`
- **Windows/Linux without CUDA**: falls back to `cpu`
- **macOS (Intel / Apple Silicon)**: currently uses `cpu` for compatibility

macOS is supported, but the current default path is CPU inference rather than Apple GPU acceleration.

---

## 📦 Installation

### 1. Basic Environment

```powershell
# Create project directory
mkdir clipvault
cd clipvault

# Create virtual environment (recommended)
python -m venv venv
.\venv\Scripts\activate

# Install package (editable mode)
pip install -e .
```

### 2. Install yt-dlp

```powershell
# Method 1: pip
pip install yt-dlp

# Method 2: winget (Windows)
winget install yt-dlp
```

### 3. Install FFmpeg (Required for Bilibili, etc.)

```powershell
# winget
winget install FFmpeg.FFmpeg

# Or download manually: https://ffmpeg.org/download.html
# Add ffmpeg.exe to PATH
```

### 4. Install Ollama

```powershell
# Download: https://ollama.com/download/windows
# Or use winget
winget install Ollama.Ollama

# Start service (runs in background)
ollama serve

# Pull recommended models
ollama pull qwen3.5:latest
ollama pull qwen2.5:7b-instruct-q4_K_M

# Verify
ollama list
```

### 5. Download Whisper Model

The `small` model (~500MB) will be automatically downloaded on first run.

---

## ⚙️ Configuration

### Option 1: Notion (Knowledge Base)

#### Step 1: Create Integration

1. Visit https://www.notion.so/my-integrations
2. Click **New integration**
3. Name: `ClipVault`
4. Get **Internal Integration Token**

#### Step 2: Create Database

Create a Notion database with these properties:

| Property | Type | Description |
|--------|------|------|
| Title | Title | Content title |
| URL | URL | Source link |
| Platform | Select | YouTube/Bilibili/... |
| Transcript | Text | Full transcription |
| Summary | Text | AI-generated summary |
| Tags | Multi-select | Auto-generated tags |
| KeyPoints | Text | Key takeaways |
| Category | Select | Content category |
| Sentiment | Select | positive/negative/neutral |
| CreatedTime | Date | Creation timestamp |

#### Step 3: Share Database with Integration

1. Open Notion database page
2. Click `...` (top-right) → `Connections` → Add `ClipVault`

#### Step 4: Get Database ID

```
https://notion.so/{workspace}/{Database_ID}?v=...
                      ↑ This is your Database ID
```

#### Step 5: Configure Environment

```powershell
# Copy template
copy .env.example .env

# Edit .env file
notepad .env
```

**Add to `.env`:**
```env
NOTION_TOKEN=your_integration_token_here
NOTION_DATABASE_ID=your_database_id_here
WHISPER_MODEL=small
LLM_MODEL=qwen3.5:latest
LLM_MODEL_FALLBACK=qwen2.5:7b-instruct-q4_K_M
DISABLE_NOTION=0
ENABLE_TRANSCRIPT_CLEANING=1
```

### Option 2: Local Test Mode

Use `--skip-notion` or set `DISABLE_NOTION=1` when you want to test download, transcription, or summarization without writing to Notion.

---

## 🚀 Usage

### CLI Basic Usage

```powershell
# Activate environment
.\venv\Scripts\activate

# Process single video
clipvault "https://www.youtube.com/watch?v=xxx"

# Debug mode
clipvault "url" --log-level DEBUG

# Skip specific steps
clipvault "url" --skip summarize
clipvault "url" --skip-notion
clipvault "url" --disable-cleaning
clipvault "url" --no-cleanup
clipvault "url" --dry-run
```

### Batch Processing

```powershell
# Create URLs file
@"
https://youtube.com/watch?v=xxx1
https://bilibili.com/video/xxx2
https://youtube.com/watch?v=xxx3
"@ | Out-File -Encoding utf8 urls.txt

# Batch process
Get-Content urls.txt | ForEach-Object { clipvault $_ }
```

### OpenClaw Skill Integration

Use the `clip_to_vault` skill for automation:

```python
# Example: Auto-save interesting videos to knowledge base
skill.clip_to_vault(url="https://youtube.com/watch?v=xxx")
```

---

## 🔍 CUDA Check

```powershell
# Check CUDA availability
python -c "import torch; print(f'CUDA: {torch.cuda.is_available()}'); print(f'Device: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"N/A\"}')"

# VRAM info
python -c "import torch; print(f'VRAM: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f}GB')"
```

---

## 📊 VRAM Usage Estimates

| Model | Parameters | Quantization | VRAM | Speed |
|------|--------|------|----------|------|
| Whisper small | - | float16 | ~2GB | Fast |
| Whisper medium | - | float16 | ~5GB | Slower |
| qwen3.5 | latest | default | ~6-7GB | Medium |
| qwen2.5:7b | 7B | Q4_K_M | ~4-5GB | Medium |

---

## 🐛 Troubleshooting

### OOM (Out of Memory) Solutions

1. **Reduce model precision**
   ```python
   # src/clipvault/providers/transcription/whisper_local.py
   COMPUTE_TYPE = "int8"  # Change from float16 to int8
   ```

2. **Use smaller LLM**
   ```python
   # src/clipvault/providers/summarization/ollama_local.py
   DEFAULT_MODEL = "llama3.2:3b-instruct-q4_K_M"  # ~2-3GB
   ```

3. **Truncate long texts**
   ```python
   # Limit transcript length
   transcript = transcript[:3000]
   ```

4. **Explicit VRAM cleanup**
   ```python
   import torch
   torch.cuda.empty_cache()
   del model
   gc.collect()
   ```

### Common Issues

| Issue | Solution |
|------|----------|
| yt-dlp download fails | Check network or use proxy |
| yt-dlp output crashes on Windows | Update to the latest code, which forces UTF-8-safe subprocess decoding |
| Whisper errors | Verify FFmpeg is installed |
| Ollama connection fails | Run `ollama serve` |
| Notion 401 error | Check Token and Database ID |
| Test run still writes to Notion | Use `--skip-notion` or set `DISABLE_NOTION=1` |
| Summaries are too generic on noisy speech | Keep cleaning enabled or raise `WHISPER_MODEL` to `medium` |

---

## 📁 Project Structure

```
clipvault/
├── src/clipvault/           # Main package
│   ├── cli/                 # CLI entry point (argparse)
│   ├── config/              # Settings & runtime config
│   ├── models/              # Data models (dataclasses)
│   ├── providers/           # Provider implementations
│   │   ├── download/        #   yt-dlp downloader
│   │   ├── transcription/   #   Whisper local / OpenAI cloud
│   │   ├── summarization/   #   Ollama local / OpenAI cloud
│   │   └── storage/         #   Notion / JSON writers
│   ├── domain/              # Pure domain logic (transcript cleaning)
│   ├── services/            # Pipeline orchestrator, factory, checkpoints
│   ├── skill/               # Headless SkillService facade
│   └── platform/            # OS-specific workarounds
├── tests/                   # Unit tests (pytest)
├── pyproject.toml           # Build config & dependencies
├── .env                     # Local config (gitignored)
├── downloads/               # Temporary audio files
├── logs/                    # Execution logs
├── checkpoints/             # Resume points
├── outputs/                 # Generated outputs (gitignored)
├── README.md                # English docs
└── README.zh-CN.md          # Chinese docs
```

---

## 🔧 Optimization Tips

### Speed Optimization

1. **Use faster models**
   - Whisper: `base` (faster than small)
   - LLM: `phi3.5:3.8b-mini` (faster but slightly lower quality)

2. **Cache models**
   - Keep Ollama running after first load

### Quality Optimization

1. **Use larger models**
   - Whisper: `medium` (set `WHISPER_MODEL=medium`)
   - LLM: `qwen2.5:14b` (needs 10GB+ VRAM)

---

## 🤝 Contributing

Contributions welcome! Areas for improvement:
- [ ] Support for more platforms (Instagram, TikTok, etc.)
- [ ] Web UI interface
- [ ] Batch processing dashboard
- [ ] Excel/Airtable direct integration
- [ ] Multi-language summary support

---

## 📝 License

MIT License - Free to use and modify

---

## 🙏 Acknowledgments

- [faster-whisper](https://github.com/guillaumekln/faster-whisper) - Local transcription
- [Ollama](https://ollama.com) - Local LLM inference
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) - Universal video downloader
- [Notion API](https://developers.notion.com) - Knowledge base integration
