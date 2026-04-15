# -*- coding: utf-8 -*-
"""
Notion storage provider.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from ..base import StorageWriter


class NotionStorageWriter(StorageWriter):
    """Write pipeline results to a Notion database."""

    WRITE_TRANSCRIPT_TO_PAGE = True
    USE_TOGGLE_FOR_TRANSCRIPT = True

    def __init__(self, token: str, database_id: str) -> None:
        from notion_client import Client

        self.token = token
        self.database_id = database_id
        self.client = Client(auth=token)

    def test_connection(self) -> bool:
        try:
            self.client.databases.retrieve(database_id=self.database_id)
            return True
        except Exception:
            return False

    def write(self, data: Dict[str, Any]) -> Dict[str, Any]:
        properties = self._build_properties(data)
        children = self._build_children(data)

        initial = children[:100] if children else None
        if initial:
            page = self.client.pages.create(
                parent={"database_id": self.database_id},
                properties=properties,
                children=initial,
            )
        else:
            page = self.client.pages.create(
                parent={"database_id": self.database_id},
                properties=properties,
            )

        page_id = page.get("id")
        if children and len(children) > 100 and page_id:
            self._append_blocks(page_id, children[100:])

        return {"id": page_id, "url": page.get("url")}

    def check_duplicate(self, url: str) -> bool:
        try:
            resp = self.client.databases.query(
                database_id=self.database_id,
                filter={"property": "URL", "rich_text": {"equals": url}},
                page_size=1,
            )
            return len(resp.get("results", [])) > 0
        except Exception as exc:
            import logging
            logging.getLogger("clipvault.pipeline").warning(
                "Notion duplicate check failed (treating as duplicate for safety): %s", exc
            )
            return True  # fail-safe: assume duplicate to prevent wasted work

    # ── property / block builders ─────────────────────────

    def _build_properties(self, data: Dict[str, Any]) -> Dict[str, Any]:
        props: Dict[str, Any] = {}
        title = str(data.get("title") or "Untitled")[:100]
        props["Name"] = {"title": [{"text": {"content": title}}]}

        platform = str(data.get("platform", ""))
        aux = f"【{platform}】{title}" if platform else title
        props["Title"] = {"rich_text": [{"text": {"content": aux[:2000]}}]}

        url = str(data.get("url", ""))
        if url:
            props["URL"] = {"rich_text": [{"text": {"content": url}}]}

        if platform:
            props["Platform"] = {"select": {"name": platform[:50]}}

        summary = str(data.get("summary", ""))
        if summary:
            props["Summary"] = {"rich_text": [{"text": {"content": summary[:2000]}}]}

        tags = data.get("tags")
        if tags:
            tag_list = tags if isinstance(tags, list) else [t.strip() for t in tags.split(",")]
            tag_list = [str(t)[:50] for t in tag_list if str(t).strip()][:10]
            if tag_list:
                props["Tags"] = {"multi_select": [{"name": t} for t in tag_list]}

        kps = data.get("key_points")
        if kps:
            kp_text = "\n".join(f"- {p}" for p in kps[:10]) if isinstance(kps, list) else str(kps)
            props["KeyPoints"] = {"rich_text": [{"text": {"content": kp_text[:2000]}}]}

        cat = str(data.get("category", ""))
        if cat:
            props["Category"] = {"select": {"name": cat[:50]}}
        sent = str(data.get("sentiment", ""))
        if sent:
            props["Sentiment"] = {"select": {"name": sent[:20]}}

        props["CreatedTime"] = {"date": {"start": datetime.now().isoformat()}}
        return props

    def _build_children(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        children: List[Dict[str, Any]] = []
        transcript = str(data.get("transcript", "")).strip()
        if transcript and self.WRITE_TRANSCRIPT_TO_PAGE:
            blocks = self._paragraph_blocks(transcript)
            if self.USE_TOGGLE_FOR_TRANSCRIPT:
                children.append({
                    "object": "block",
                    "type": "toggle",
                    "toggle": {
                        "rich_text": [{"type": "text", "text": {"content": "Transcript"}}],
                        "children": blocks[:100],
                    },
                })
            else:
                children.extend(blocks)
        return children

    def _append_blocks(self, page_id: str, blocks: List[Dict[str, Any]]) -> None:
        for i in range(0, len(blocks), 100):
            self.client.blocks.children.append(block_id=page_id, children=blocks[i : i + 100])

    @staticmethod
    def _paragraph_blocks(text: str) -> List[Dict[str, Any]]:
        max_len = 1800
        blocks: List[Dict[str, Any]] = []
        buf = ""

        def flush() -> None:
            nonlocal buf
            if not buf.strip():
                buf = ""
                return
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": [{"type": "text", "text": {"content": buf[:2000]}}]},
            })
            buf = ""

        for line in text.splitlines():
            if not line.strip():
                flush()
                continue
            if len(buf) + len(line) + 1 <= max_len:
                buf = (buf + "\n" + line) if buf else line
            else:
                flush()
                while len(line) > max_len:
                    chunk, line = line[:max_len], line[max_len:]
                    blocks.append({
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {"rich_text": [{"type": "text", "text": {"content": chunk}}]},
                    })
                buf = line
        flush()
        return blocks
