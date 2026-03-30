# ClipVault — Architecture

## Directory Structure

```
src/
  clipvault/
    __init__.py                       # version
    __main__.py                       # python -m clipvault
    
    config/
      __init__.py
      settings.py                     # AppSettings  (immutable, from env)
      runtime.py                      # RuntimeConfig (per-run overrides)
    
    models/
      __init__.py
      resource.py                     # ResourceInput, ContentType, Platform
      transcript.py                   # TranscriptResult, TranscriptSegment
      summary.py                      # SummaryResult
      pipeline.py                     # PipelineResult, StepRecord, StepStatus
    
    providers/
      __init__.py
      base.py                         # ABCs: Downloader, Transcriber, Summarizer, StorageWriter
      download/
        ytdlp.py                      # YtdlpDownloader
      transcription/
        whisper_local.py              # WhisperLocalTranscriber
        # (future) cloud_stt.py
      summarization/
        ollama_local.py               # OllamaLocalSummarizer
        # (future) openai_cloud.py
      storage/
        notion.py                     # NotionStorageWriter
        json_local.py                 # JsonStorageWriter
    
    domain/
      __init__.py
      transcript_cleaner.py           # Pure domain logic, no I/O
    
    services/
      __init__.py
      pipeline.py                     # PipelineService (orchestrator)
      checkpoint.py                   # CheckpointManager
      factory.py                      # Composition root — wires providers
    
    skill/
      __init__.py                     # SkillService — headless facade
    
    cli/
      __init__.py                     # Thin CLI entry (argparse → PipelineService)
    
    platform/
      __init__.py                     # fix_encoding() — Windows UTF-8 workaround

tests/
  conftest.py                         # Stub providers + shared fixtures
  test_models.py
  test_pipeline.py
  test_cleaner.py

pyproject.toml                        # Build, deps, scripts, tool config
```

## Layer Responsibilities

| Layer | Module | Responsibility |
|-------|--------|----------------|
| **CLI** | `clipvault.cli` | Parse args, human-readable output. Thin. |
| **Skill Adapter** | `clipvault.skill` | Headless dict-in/dict-out facade for agents/skills |
| **Service** | `clipvault.services.pipeline` | Orchestrate steps, manage retry/checkpoint |
| **Service** | `clipvault.services.factory` | Single composition root — wire concrete providers |
| **Service** | `clipvault.services.checkpoint` | Save/restore `PipelineResult` by URL hash |
| **Domain** | `clipvault.domain` | Pure logic (transcript cleaning). No I/O. |
| **Models** | `clipvault.models` | Dataclasses for all structured data |
| **Providers** | `clipvault.providers.base` | ABCs that the pipeline depends on |
| **Providers** | `clipvault.providers.*` | Concrete implementations (local/cloud) |
| **Config** | `clipvault.config.settings` | Immutable env-based settings |
| **Config** | `clipvault.config.runtime` | Mutable per-run overrides |
| **Platform** | `clipvault.platform` | OS-specific workarounds (encoding) |

## How CLI and Skill Share the Same Core

```
                    ┌──────────┐  ┌──────────────┐
                    │   CLI    │  │ Skill/Agent   │
                    │ (argparse│  │ (SkillService)│
                    └────┬─────┘  └──────┬────────┘
                         │               │
                         ▼               ▼
                    ┌────────────────────────┐
                    │    PipelineService      │
                    │  (services/pipeline.py) │
                    └────────┬───────────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
         Downloader    Transcriber    Summarizer    StorageWriter
          (ABC)          (ABC)          (ABC)         (ABC)
              │              │              │              │
              ▼              ▼              ▼              ▼
         YtdlpDL    WhisperLocal    OllamaLocal     Notion/JSON
```

Both CLI and SkillService call `create_pipeline_service()` → same factory,
same providers, same pipeline logic. The only difference:

- **CLI**: formats output for humans, manages logging to console
- **SkillService**: returns plain dicts, no stdout side-effects

## Provider Abstraction

All providers implement ABCs in `providers/base.py`. The pipeline never
imports a concrete class directly.

Three provider modes are supported via `PROVIDER_MODE` env var:

| Mode | Transcription | Summarization |
|------|---------------|---------------|
| `local` (default) | faster-whisper | Ollama |
| `cloud` | OpenAI Whisper API | OpenAI Chat Completions |
| `hybrid` | faster-whisper (local) | Ollama → OpenAI fallback |

Cloud providers live alongside local ones:
- `providers/transcription/openai_cloud.py` — OpenAI Whisper API
- `providers/summarization/openai_cloud.py` — OpenAI Chat Completions

The hybrid summarizer (`_HybridSummarizer` in `factory.py`) wraps
local + cloud: tries local first, falls back to cloud transparently.

To add another cloud provider:
1. Create `providers/transcription/my_cloud.py` implementing `Transcriber`
2. Update `services/factory.py` to select it based on an env flag
3. Done — no changes to pipeline, CLI, or skill adapter

## Configuration

Two layers:
- **AppSettings** (frozen dataclass): loaded once from `.env` + env vars
- **RuntimeConfig** (mutable dataclass): per-invocation overrides (skip steps, dry-run, language)

New env var `PROVIDER_MODE=local|cloud|hybrid` controls provider selection.

## Pipeline Features

- **Checkpoint/Resume**: automatic save after each step; re-run resumes from last success
- **Skip Steps**: `RuntimeConfig.skip_steps = {"transcribe", "summarize"}`
- **Dry Run**: `RuntimeConfig.dry_run = True` — validates inputs, returns plan
- **Structured Result**: `PipelineResult.to_dict()` / `.to_json()`

## Platform Handling

- Windows UTF-8 fix is in `clipvault.platform.fix_encoding()` — called once at CLI entry
- All subprocess calls use explicit `encoding="utf-8"` + `errors="replace"`
- No `sys.path` manipulation — uses standard `pyproject.toml` packaging
- Architecture is platform-agnostic; Windows fix is opt-in, isolated

## Migration from Old Structure

| Old file | New location | Notes |
|----------|-------------|-------|
| `main.py` → `Config` | `clipvault.config.settings` | Now a frozen dataclass |
| `main.py` → `VideoPipeline` | `clipvault.services.pipeline` | Depends on ABCs only |
| `main.py` → `main()` | `clipvault.cli` | Pure arg parsing |
| `downloader.py` | `clipvault.providers.download.ytdlp` | Implements `Downloader` ABC |
| `transcriber.py` | `clipvault.providers.transcription.whisper_local` | Implements `Transcriber` ABC |
| `summarizer.py` | `clipvault.providers.summarization.ollama_local` | Implements `Summarizer` ABC |
| `transcript_cleaner.py` | `clipvault.domain.transcript_cleaner` | Pure domain, unchanged |
| `notion_writer.py` | `clipvault.providers.storage.notion` + `json_local` | Implements `StorageWriter` ABC |

The old flat files can remain as legacy wrappers during migration.
