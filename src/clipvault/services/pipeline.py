# -*- coding: utf-8 -*-
"""
Core pipeline service — orchestrates download → transcribe → clean → summarize → store.

Depends only on provider ABCs and models; no concrete imports.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Optional

from ..config.runtime import RuntimeConfig
from ..config.settings import AppSettings
from ..domain.transcript_cleaner import TranscriptCleaner
from ..models.pipeline import PipelineResult, StepStatus
from ..models.resource import ContentType, ResourceInput
from ..models.transcript import TranscriptResult
from ..providers.base import Downloader, StorageWriter, Summarizer, Transcriber
from .checkpoint import CheckpointManager

logger = logging.getLogger("clipvault.pipeline")


class PipelineService:
    """
    Stateless pipeline orchestrator.

    All heavy dependencies are injected via the constructor so the
    same service instance can be called from CLI, skill adapter,
    API handler, or tests.
    """

    def __init__(
        self,
        settings: AppSettings,
        downloader: Downloader,
        transcriber: Transcriber,
        summarizer: Summarizer,
        storage: Optional[StorageWriter] = None,
        checkpoint_mgr: Optional[CheckpointManager] = None,
    ) -> None:
        self.settings = settings
        self.downloader = downloader
        self.transcriber = transcriber
        self.summarizer = summarizer
        self.storage = storage
        self.ckpt = checkpoint_mgr or CheckpointManager(settings.checkpoint_dir)

    # ── public entry ──────────────────────────────────────

    def run(self, url: str, runtime: Optional[RuntimeConfig] = None) -> PipelineResult:
        """Execute the full pipeline and return a structured result."""
        rc = runtime or RuntimeConfig()

        # Resume from checkpoint
        result = self._maybe_resume(url, rc)
        resource = ResourceInput(url=url, language=rc.language)

        if result is None:
            result = PipelineResult(
                url=url,
                platform=resource.platform,
                started_at=datetime.now().isoformat(),
            )

        logger.info("="*50)
        logger.info("🚀 Starting: %s", url)
        logger.info("="*50)

        if rc.dry_run:
            result.status = StepStatus.SKIPPED
            result.metadata["dry_run"] = True
            return result

        # Build cleaner from settings + runtime override
        cleaning_enabled = self.settings.enable_transcript_cleaning and not rc.disable_cleaning
        cleaner = TranscriptCleaner(enabled=cleaning_enabled)

        try:
            self._step_download(result, resource, rc)
            self._step_transcribe(result, resource, rc)
            self._step_clean(result, rc, cleaner)
            self._step_summarize(result, rc)
            self._step_store(result, rc)

            result.status = StepStatus.SUCCESS
            result.finished_at = datetime.now().isoformat()
            if result.started_at:
                result.elapsed_seconds = (
                    datetime.fromisoformat(result.finished_at)
                    - datetime.fromisoformat(result.started_at)
                ).total_seconds()

            self.ckpt.remove(url)
            logger.info("")
            logger.info("="*50)
            logger.info("✅ Processing complete!")
            logger.info("⏱️ Total elapsed: %.1fs", result.elapsed_seconds or 0)
            logger.info("="*50)
            logger.info("🗑️ Checkpoint removed")

        except Exception as exc:
            result.status = StepStatus.ERROR
            result.error = str(exc)
            result.finished_at = datetime.now().isoformat()
            self.ckpt.save(result)
            logger.error("❌ Pipeline failed: %s", exc)
            raise

        return result

    # ── steps ─────────────────────────────────────────────
    # Each step uses ensure_step() so that checkpoint resume
    # resets the existing record instead of creating a duplicate.

    def _step_download(self, result: PipelineResult, resource: ResourceInput, rc: RuntimeConfig) -> None:
        existing = result.get_step("download")
        if existing and existing.status in (StepStatus.SUCCESS, StepStatus.SKIPPED):
            return
        if rc.should_skip("download"):
            result.ensure_step("download").mark_skipped("user")
            logger.info("⏭️ Skipping download (user)")
            return

        step = result.ensure_step("download")
        step.mark_running()
        logger.info("")
        logger.info("📍 Step 1/5: Download")
        logger.info("-"*30)
        logger.info("📥 Downloading: %s", resource.url)
        try:
            dl = self.downloader.download(resource, force=rc.force_download)
            result.audio_path = dl.get("audio_path")
            result.title = dl.get("title")
            result.platform = resource.platform

            ct = dl.get("content_type", "video")
            try:
                result.content_type = ContentType(ct)
            except ValueError:
                result.content_type = ContentType.VIDEO

            # For image-text: store text directly as transcript
            if result.content_type == ContentType.IMAGE_TEXT:
                text = dl.get("description", "")
                result.transcript = TranscriptResult(text=text)

            step.mark_success(platform=resource.platform.value, title=result.title)
            logger.info("✅ Downloaded: %s (%s)", result.title or "untitled", result.content_type.value)
            logger.info("💾 Checkpoint saved")
            self.ckpt.save(result)
        except Exception as exc:
            step.mark_error(exc)
            raise

    def _step_transcribe(self, result: PipelineResult, resource: ResourceInput, rc: RuntimeConfig) -> None:
        existing = result.get_step("transcribe")
        if existing and existing.status in (StepStatus.SUCCESS, StepStatus.SKIPPED):
            return
        if rc.should_skip("transcribe"):
            result.ensure_step("transcribe").mark_skipped("user")
            logger.info("⏭️ Skipping transcription (user)")
            return
        if result.content_type == ContentType.IMAGE_TEXT:
            result.ensure_step("transcribe").mark_skipped("image_text")
            logger.info("⏭️ Skipping transcription (image-text content)")
            return
        if not result.audio_path:
            result.ensure_step("transcribe").mark_skipped("no_audio")
            logger.info("⏭️ Skipping transcription (no audio)")
            return

        step = result.ensure_step("transcribe")
        step.mark_running()
        logger.info("")
        logger.info("📍 Step 2/5: Transcribe")
        logger.info("-"*30)
        logger.info("🎙️ Transcribing: %s", result.audio_path)
        lang = rc.language or self.settings.transcribe_language

        max_retries = 3
        delay = 5
        last_err: Optional[Exception] = None

        for attempt in range(max_retries):
            try:
                self.transcriber.load()
                tr = self.transcriber.transcribe(result.audio_path, language=lang)
                self.transcriber.unload()
                result.transcript = tr
                step.mark_success(duration=tr.duration, device=tr.device)
                logger.info("✅ Transcribed: %.0fs audio on %s", tr.duration or 0, tr.device)
                logger.info("💾 Checkpoint saved")
                self.ckpt.save(result)
                return
            except Exception as exc:
                last_err = exc
                self.transcriber.unload()
                logger.warning("Transcription attempt %d failed: %s", attempt + 1, exc)

                # CPU fallback
                try:
                    self.transcriber.load(device="cpu")
                    tr = self.transcriber.transcribe(result.audio_path, language=lang)
                    self.transcriber.unload()
                    result.transcript = tr
                    step.mark_success(duration=tr.duration, device="cpu")
                    logger.info("✅ Transcribed (CPU fallback): %.0fs audio", tr.duration or 0)
                    logger.info("💾 Checkpoint saved")
                    return
                except Exception as cpu_exc:
                    last_err = cpu_exc
                    self.transcriber.unload()

                if attempt < max_retries - 1:
                    time.sleep(delay)
                    delay *= 2

        step.mark_error(last_err)  # type: ignore[arg-type]
        raise last_err  # type: ignore[misc]

    def _step_clean(self, result: PipelineResult, rc: RuntimeConfig, cleaner: TranscriptCleaner) -> None:
        existing = result.get_step("clean")
        if existing and existing.status in (StepStatus.SUCCESS, StepStatus.SKIPPED):
            return
        if not cleaner.enabled:
            result.ensure_step("clean").mark_skipped("disabled")
            return
        if result.transcript is None:
            result.ensure_step("clean").mark_skipped("no_transcript")
            return

        step = result.ensure_step("clean")
        step.mark_running()
        logger.info("")
        logger.info("📍 Step 3/5: Clean")
        logger.info("-"*30)
        logger.info("🧹 Cleaning transcript (%d chars)", len(result.transcript.text))
        original = result.transcript.text
        cleaned = cleaner.clean(original)
        result.cleaned_transcript = cleaned
        step.mark_success(original_len=len(original), cleaned_len=len(cleaned))
        logger.info("✅ Cleaned: %d → %d chars", len(original), len(cleaned))

        # Cleanup audio after successful transcription + cleaning
        if self.settings.cleanup_audio and result.audio_path:
            self.downloader.cleanup(result.audio_path)

    def _step_summarize(self, result: PipelineResult, rc: RuntimeConfig) -> None:
        existing = result.get_step("summarize")
        if existing and existing.status in (StepStatus.SUCCESS, StepStatus.SKIPPED):
            return
        if rc.should_skip("summarize"):
            result.ensure_step("summarize").mark_skipped("user")
            logger.info("⏭️ Skipping summarization (user)")
            return
        if result.transcript is None:
            result.ensure_step("summarize").mark_skipped("no_transcript")
            return

        step = result.ensure_step("summarize")
        step.mark_running()
        logger.info("")
        logger.info("📍 Step 4/5: Summarize")
        logger.info("-"*30)
        logger.info("🤖 Summarizing with LLM...")
        try:
            text = result.cleaned_transcript or result.transcript.text
            summary = self.summarizer.summarize(
                text,
                content_type=result.content_type.value,
                max_length=self.settings.max_transcript_length,
            )
            self.summarizer.unload()
            result.summary = summary
            step.mark_success()
            logger.info("✅ Summary ready (%d key points, %d tags)", len(summary.key_points or []), len(summary.tags or []))
            logger.info("💾 Checkpoint saved")
            self.ckpt.save(result)
        except Exception as exc:
            step.mark_error(exc)
            raise

    def _step_store(self, result: PipelineResult, rc: RuntimeConfig) -> None:
        existing = result.get_step("store")
        if existing and existing.status in (StepStatus.SUCCESS, StepStatus.SKIPPED):
            return
        if rc.skip_storage or self.storage is None:
            result.ensure_step("store").mark_skipped("disabled")
            logger.info("⏭️ Skipping storage (disabled)")
            return

        step = result.ensure_step("store")
        step.mark_running()
        logger.info("")
        logger.info("📍 Step 5/5: Store")
        logger.info("-"*30)
        logger.info("📝 Storing to %s", "Notion" if self.storage else "JSON")
        try:
            if self.storage.check_duplicate(result.url):
                step.mark_skipped("duplicate")
                logger.info("⏭️ Skipping store (duplicate URL)")
                return

            payload = self._build_storage_payload(result)
            meta = self.storage.write(payload)
            step.mark_success(**meta)
            logger.info("✅ Stored: %s", meta.get("url") or meta.get("id", "ok"))
            logger.info("💾 Checkpoint saved")
            self.ckpt.save(result)
        except Exception as exc:
            step.mark_error(exc)
            raise

    # ── helpers ────────────────────────────────────────────

    def _maybe_resume(self, url: str, rc: RuntimeConfig) -> Optional[PipelineResult]:
        if not rc.resume:
            return None
        result = self.ckpt.load(url)
        if result:
            logger.info("📂 Resuming from checkpoint...")
            if result.title:
                logger.info("   Existing title: %s", result.title)
        return result

    @staticmethod
    def _build_storage_payload(result: PipelineResult) -> dict:
        payload: dict = {
            "title": result.title or result.url[:50],
            "url": result.url,
            "platform": result.platform.value,
            "transcript": result.transcript.text if result.transcript else "",
        }
        if result.summary:
            payload["summary"] = result.summary.summary
            payload["key_points"] = result.summary.key_points
            payload["tags"] = result.summary.tags
            payload["category"] = result.summary.category
            payload["sentiment"] = result.summary.sentiment
        return payload
