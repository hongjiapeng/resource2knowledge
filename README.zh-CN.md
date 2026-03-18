# 🌐 ClipVault - 互联网内容知识归档工具

> 本地运行、无需付费 API，支持抓取互联网内容（视频 / 图文）、转录、总结并归档到 Notion。适合 8GB+ 显存环境。

[English](README.md) | [简体中文](README.zh-CN.md)

## ✨ 功能特性

将互联网内容沉淀为可检索的个人知识库：

- 📥 **多平台支持**：YouTube、Bilibili、小红书（视频 + 图文）
- 🎙️ **本地语音转录**：基于 Whisper，本地完成音频转文字
- 🤖 **本地 AI 总结**：通过 Ollama 运行本地 LLM 生成摘要
- 🧹 **可选 transcript 清洗**：在总结前对噪音较多的 ASR 文本做低风险预处理
- 💾 **灵活归档**：支持写入 Notion，也支持本地测试模式
- 🔌 **自动化友好**：可集成到自动化工作流
- ⚡ **断点续跑**：中断后可从 checkpoint 恢复

---

## 📋 流程概览

| 步骤 | 模块 | 技术 | 显存占用 |
|------|------|------|----------|
| 1. 下载内容 | downloader.py | yt-dlp | - |
| 2. 语音转文本 | transcriber.py | faster-whisper（可配置，默认 `small`） | ~2GB |
| 3. 生成摘要 | summarizer.py | Ollama `qwen3.5`，失败时回退 `qwen2.5` | ~4-7GB |
| 4. 归档 | notion_writer.py | Notion API / Mock writer | - |

**总显存占用**：约 `6-9GB`（在 NVIDIA GPU 加速下，串行执行，不并发）

如果是纯 CPU 环境，流程仍然可以运行，只是转录和总结速度会更慢。

---

## 🖥️ 环境要求

- **OS**：Windows 11 / Linux / macOS
- **Python**：3.9+
- **RAM**：建议 16GB+，32GB 更佳
- **可选 GPU 加速**：NVIDIA GPU，建议 8GB+ 显存（如 RTX 4060/5060、RTX 3070）
- **CUDA**：如果希望启用 GPU 加速，建议使用 12.x

转录阶段会自动检测运行设备：

- **检测到 NVIDIA + CUDA 可用**：使用 `cuda`
- **Windows/Linux 无 CUDA**：自动回退到 `cpu`
- **macOS（Intel / Apple Silicon）**：当前默认使用 `cpu`，优先保证兼容性

也就是说，macOS 可以运行，但当前实现默认不启用苹果 GPU 加速。

---

## 📦 安装步骤

### 1. 基础环境

```powershell
# 创建项目目录
mkdir clipvault
cd clipvault

# 创建虚拟环境 (推荐)
python -m venv venv
.\venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

### 2. 安装 yt-dlp

```powershell
# 方法 1: pip
pip install yt-dlp

# 方法 2: winget (Windows)
winget install yt-dlp
```

### 3. 安装 FFmpeg (B站等需要)

```powershell
# winget
winget install FFmpeg.FFmpeg

# 或手动下载: https://ffmpeg.org/download.html
# 将 ffmpeg.exe 添加到 PATH
```

### 4. 安装 Ollama

```powershell
# 下载: https://ollama.com/download/windows
# 或使用 winget
winget install Ollama.Ollama

# 启动服务（后台运行）
ollama serve

# 拉取推荐模型
ollama pull qwen3.5:latest
ollama pull qwen2.5:7b-instruct-q4_K_M

# 验证
ollama list
```

### 5. 下载 Whisper 模型

首次运行时会自动下载 `small` 模型（约 500MB）

---

## ⚙️ 配置

### 方案 1：接入 Notion

### 步骤 1: 创建 Integration

1. 访问 https://www.notion.so/my-integrations
2. 点击 **New integration**
3. 名称: `Resource2Knowledge`
4. 获取 **Internal Integration Token**

### 步骤 2: 创建数据库

创建 Notion 数据库，包含以下字段:

| 字段名 | 类型 | 说明 |
|--------|------|------|
| Title | 标题 | 视频标题 |
| URL | URL | 视频链接 |
| Platform | 选择 | YouTube/Bilibili/... |
| Transcript | 文本 | 完整转录 |
| Summary | 文本 | AI 摘要 |
| Tags | 多选 | 自动标签 |
| KeyPoints | 文本 | 要点列表 |
| Category | 选择 | 视频分类 |
| Sentiment | 选择 | positive/negative/neutral |
| CreatedTime | 日期 | 创建时间 |

### 步骤 3: 分享数据库给 Integration

1. 打开 Notion 数据库页面
2. 点击右上角 `...` → `Connections` → 添加 `Resource2Knowledge`

### 步骤 4: 获取 Database ID

```
https://notion.so/{workspace}/{Database_ID}?v=...
                      ↑ 这里就是 Database ID
```

### 步骤 5：配置环境变量

```powershell
# 复制配置模板
copy .env.example .env

# 编辑 .env 文件
notepad .env
```

建议在 `.env` 中至少配置：

```env
NOTION_TOKEN=your_integration_token_here
NOTION_DATABASE_ID=your_database_id_here
WHISPER_MODEL=small
LLM_MODEL=qwen3.5:latest
LLM_MODEL_FALLBACK=qwen2.5:7b-instruct-q4_K_M
DISABLE_NOTION=0
ENABLE_TRANSCRIPT_CLEANING=1
```

### 方案 2：本地测试模式

如果你只想测试下载、转录或摘要，不希望写入 Notion，可以：

- 在命令行使用 `--skip-notion`
- 或在 `.env` 里设置 `DISABLE_NOTION=1`

---

## 🚀 使用方法

### CLI 基本用法

```powershell
# 激活环境
.\venv\Scripts\activate

# 运行单个视频
python main.py "https://www.youtube.com/watch?v=xxx"

# 调试模式
python main.py "url" --log-level DEBUG

# 跳过部分步骤
python main.py "url" --skip-summary
python main.py "url" --skip-notion
python main.py "url" --disable-cleaning
python main.py "url" --no-cleanup
```

### 批量处理

```powershell
# 创建 URLs 文件
@"
https://youtube.com/watch?v=xxx1
https://bilibili.com/video/xxx2
https://youtube.com/watch?v=xxx3
"@ | Out-File -Encoding utf8 urls.txt

# 批量处理
Get-Content urls.txt | ForEach-Object { python main.py $_ }
```

### 自动化集成

可通过 `clip_to_vault` 技能接入自动化流程：

```python
skill.clip_to_vault(url="https://youtube.com/watch?v=xxx")
```

---

## 🔍 CUDA 检查

```powershell
# 检查 CUDA 是否可用
python -c "import torch; print(f'CUDA: {torch.cuda.is_available()}'); print(f'Device: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"N/A\"}')"

# 显存信息
python -c "import torch; print(f'VRAM: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f}GB')"
```

---

## 📊 显存占用预估

| 模型 | 参数量 | 量化 | 显存占用 | 速度 |
|------|--------|------|----------|------|
| Whisper small | - | float16 | ~2GB | 快 |
| Whisper medium | - | float16 | ~5GB | 较慢 |
| qwen3.5 | latest | 默认 | ~6-7GB | 中等 |
| qwen2.5:7b | 7B | Q4_K_M | ~4-5GB | 中等 |

---

## 🐛 常见问题

### OOM 解决方案

1. **降低模型精度**
   ```python
   # transcriber.py
   COMPUTE_TYPE = "int8"  # 从 float16 改为 int8
   ```

2. **使用更小的 LLM**
   ```python
   # summarizer.py
   DEFAULT_MODEL = "llama3.2:3b-instruct-q4_K_M"  # ~2-3GB
   ```

3. **分批处理长文本**
   ```python
   # 截断过长文本
   transcript = transcript[:3000]
   ```

4. **显式释放显存**
   ```python
   import torch
   torch.cuda.empty_cache()
   del model
   gc.collect()
   ```

### 其他问题

| 问题 | 解决方案 |
|------|----------|
| yt-dlp 下载失败 | 检查网络，或使用代理 |
| yt-dlp 在 Windows 输出乱码或崩溃 | 更新到最新代码，当前已强制使用 UTF-8 安全解码 |
| Whisper 报错 | 确认 FFmpeg 已安装 |
| Ollama 连接失败 | 运行 `ollama serve` |
| Notion 401 错误 | 检查 Token 和 Database ID |
| 测试时仍写入了 Notion | 使用 `--skip-notion` 或设置 `DISABLE_NOTION=1` |
| 口语视频总结过于泛化 | 保持清洗开启，或将 `WHISPER_MODEL` 提升到 `medium` |

---

## 📁 项目结构

```
clipvault/
├── main.py              # 主入口
├── downloader.py        # 视频 / 内容下载
├── transcriber.py       # Whisper 转录
├── transcript_cleaner.py # 可选 transcript 预处理
├── summarizer.py        # LLM 摘要
├── notion_writer.py     # Notion 写入 / Mock writer
├── requirements.txt     # 依赖
├── .env.example         # 配置模板
├── .env                 # 本地配置 (gitignore)
├── downloads/           # 临时音频
├── logs/                # 运行日志
├── checkpoints/         # 断点续跑文件
├── outputs/             # 本地产物（已 gitignore）
├── README.md            # 英文文档
└── README.zh-CN.md      # 中文文档
```

---

## 🔧 优化建议

### 速度优化

1. **使用更快模型**
   - Whisper: `base` (比 small 快)
   - LLM: `phi3.5:3.8b-mini` (更快但质量略低)

2. **缓存模型**
   - 首次加载后保持运行

### 质量优化

1. **使用更大模型**
   - Whisper: `medium`（设置 `WHISPER_MODEL=medium`）
   - LLM: `qwen2.5:14b` (需要 10GB+ 显存)

---

## 🤝 贡献

欢迎贡献，当前值得继续改进的方向包括：

- [ ] 支持更多平台（Instagram、TikTok 等）
- [ ] Web UI 界面
- [ ] 批量处理仪表盘
- [ ] Excel / Airtable 集成
- [ ] 多语言总结支持

---

## 📝 License

MIT License - 可自由使用和修改

---

## 🙏 致谢

- [faster-whisper](https://github.com/guillaumekln/faster-whisper) - 本地转录
- [Ollama](https://ollama.com) - 本地 LLM 推理
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) - 通用下载器
- [Notion API](https://developers.notion.com) - 知识库集成
