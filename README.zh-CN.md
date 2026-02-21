# 🌐 Resource2Knowledge - 互联网资源知识入库工作流

> 本地运行、无需付费 API、适配 8GB 显存（当前支持视频，后续可扩展图文）

## 📋 功能概览

| 步骤 | 模块 | 技术 | 显存占用 |
|------|------|------|----------|
| 1. 下载音频 | downloader.py | yt-dlp | - |
| 2. 语音转文本 | transcriber.py | faster-whisper small | ~2GB |
| 3. 生成摘要 | summarizer.py | Ollama qwen2.5:7b | ~4-5GB |
| 4. 入库 | notion_writer.py | Notion API | - |

**总显存占用**: ~6-7GB (串行执行，不并发)

---



## 🎯 项目定位

将互联网上的内容资源沉淀为可检索的个人知识库。

- **当前输入**: 视频链接（如 YouTube、Bilibili）
- **后续输入规划**: 图文内容（如小红书图文）
- **当前输出**: Notion 数据库
- **后续输出规划**: CSV / Excel 等离线格式

---
## 🖥️ 环境要求

- **OS**: Windows 11
- **GPU**: NVIDIA RTX 5060 (8GB VRAM)
- **RAM**: 32GB
- **CUDA**: 12.x

---

## 📦 安装步骤

### 1. 基础环境

```powershell
# 创建项目目录
mkdir resource2knowledge
cd resource2knowledge

# 创建虚拟环境 (推荐)
python -m venv venv
.\venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

### 2. 安装 yt-dlp

```powershell
# 方法1: pip
pip install yt-dlp

# 方法2: winget (Windows)
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

# 启动服务 (后台运行)
ollama serve

# 拉取模型
ollama pull qwen2.5:7b-instruct-q4_K_M

# 验证
ollama list
```

### 5. 下载 Whisper 模型

首次运行时会自动下载 `small` 模型 (~500MB)

---

## ⚙️ 配置 Notion

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

### 步骤 5: 配置环境变量

```powershell
# 复制配置模板
copy .env.example .env

# 编辑 .env 文件
notepad .env
```

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
| qwen2.5:7b | 7B | Q4_K_M | ~4-5GB | 中等 |
| **总计** | - | - | **~6-7GB** | 10分钟视频<3分钟 |

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
| Whisper 报错 | 确认 FFmpeg 已安装 |
| Ollama 连接失败 | 运行 `ollama serve` |
| Notion 401 错误 | 检查 Token 和 Database ID |

---

## 📁 项目结构

```
resource2knowledge/
├── main.py              # 主入口
├── downloader.py        # 视频下载
├── transcriber.py       # Whisper 转录
├── summarizer.py       # LLM 摘要
├── notion_writer.py     # Notion 写入
├── requirements.txt     # 依赖
├── .env.example         # 配置模板
├── .env                 # 本地配置 (gitignore)
├── downloads/           # 临时音频
├── logs/                # 运行日志
└── README.md
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
   - Whisper: `medium` (需要更多显存)
   - LLM: `qwen2.5:14b` (需要 10GB+ 显存)

---

## 📝 License

MIT License - 可自由使用和修改
