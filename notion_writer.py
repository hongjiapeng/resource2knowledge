# -*- coding: utf-8 -*-
"""
📝 Notion Writer Module (Full Script)
- Write video metadata into Notion database properties
- Write long Transcript / optional Summary content into page blocks to avoid the 2000-character limit
- Optionally keep a TranscriptPreview field (first N characters) for quick table browsing
"""

import os
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Any

from dotenv import load_dotenv

# Load .env
load_dotenv()

# Notion client
try:
    from notion_client import Client
    USE_NOTION_CLIENT = True
except ImportError:
    USE_NOTION_CLIENT = False
    print("⚠️ notion_client is not installed. MockNotionWriter will be used for local JSON output only.")


class NotionWriter:
    """Notion database writer (properties + page blocks)."""

    # =============== Tunable switches ===============
    WRITE_TRANSCRIPT_TO_PAGE = True          # ✅ Write transcript content into the page body
    WRITE_SUMMARY_TO_PAGE = False            # Optional: also write the summary into the page body
    KEEP_TRANSCRIPT_PROPERTY = False         # ❌ Stop writing the Transcript property to avoid truncation
    KEEP_TRANSCRIPT_PREVIEW = False          # Optional: keep TranscriptPreview (first N characters)
    TRANSCRIPT_PREVIEW_CHARS = 500           # TranscriptPreview length
    USE_TOGGLE_FOR_TRANSCRIPT = True         # ✅ Put transcript content inside a collapsed toggle
    # ================================================

    def __init__(
        self,
        token: Optional[str] = None,
        database_id: Optional[str] = None,
        env_file: str = ".env"
    ):
        self.token = token or os.getenv("NOTION_TOKEN") or self._load_env(env_file, "NOTION_TOKEN")
        self.database_id = database_id or os.getenv("NOTION_DATABASE_ID") or self._load_env(env_file, "NOTION_DATABASE_ID")

        if not self.token:
            raise ValueError("NOTION_TOKEN is not set")
        if not self.database_id:
            raise ValueError("NOTION_DATABASE_ID is not set")
        if not USE_NOTION_CLIENT:
            raise ValueError("notion_client is not installed (pip install notion-client)")

        self.client = Client(auth=self.token)

    def _load_env(self, env_file: str, key: str) -> Optional[str]:
        env_path = Path(env_file)
        if not env_path.exists():
            return None
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    if k.strip() == key:
                        return v.strip()
        return None

    def test_connection(self) -> bool:
        try:
            self.client.databases.retrieve(database_id=self.database_id)
            print("✅ Notion connection successful")
            return True
        except Exception as e:
            print(f"❌ Notion connection failed: {e}")
            return False

    # -------------------- Core: create a page --------------------
    def create_page(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a Notion page with properties and body blocks."""
        properties = self._build_properties(data)
        children = self._build_children(data)

        try:
            # Create the page first with an initial block batch to avoid oversized requests
            initial_children = children[:100] if children else None
            if initial_children:
                page = self.client.pages.create(
                    parent={"database_id": self.database_id},
                    properties=properties,
                    children=initial_children,
                )
            else:
                page = self.client.pages.create(
                    parent={"database_id": self.database_id},
                    properties=properties,
                )

            page_id = page.get("id")
            print(f"✅ Created Notion page: {page_id or 'unknown'}")

            # Append remaining blocks if there are more than 100
            if children and len(children) > 100 and page_id:
                self._append_blocks(page_id, children[100:])

            return page

        except Exception as e:
            raise Exception(f"Failed to create Notion page: {str(e)}")

    # -------------------- Properties: database columns --------------------
    def _build_properties(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build Notion page properties.
        - Name: title (the main page title)
        - Title: rich_text (auxiliary title / source title / ID)
        - URL: rich_text (matches the current database schema)
        - Others: Platform/Tags/Category/Sentiment/Summary/KeyPoints/CreatedTime
        - Transcript is skipped by default to avoid truncation, but can be enabled
        """
        properties: Dict[str, Any] = {}

        # 1) Name (title, the primary Notion page title)
        title = str(data.get("title") or "").strip()
        if not title:
            fallback = data.get("video_id") or data.get("id") or "Untitled"
            title = str(fallback)
        properties["Name"] = {"title": [{"text": {"content": title[:100]}}]}

        # 2) Title (rich_text: raw title / source ID / fallback title)
        platform = str(data.get("platform") or "").strip()
        aux_title = str(data.get("raw_title") or data.get("source_title") or "").strip()
        if not aux_title and platform:
            aux_title = f"【{platform}】{title}"
        elif not aux_title:
            aux_title = title

        properties["Title"] = {"rich_text": [{"text": {"content": aux_title[:2000]}}]}

        # 3) URL (the current database schema uses rich_text)
        url = str(data.get("url") or "").strip()
        if url:
            properties["URL"] = {"rich_text": [{"text": {"content": url}}]}

        # 4) Platform (select)
        if platform:
            properties["Platform"] = {"select": {"name": platform[:50]}}

        # 5) Summary (rich_text, <= 2000 characters)
        summary = str(data.get("summary") or "").strip()
        if summary:
            properties["Summary"] = {"rich_text": [{"text": {"content": summary[:2000]}}]}

        # 6) Tags (multi_select)
        tags = data.get("tags")
        if tags:
            if isinstance(tags, str):
                tag_list = [t.strip() for t in tags.split(",") if t.strip()][:10]
            elif isinstance(tags, list):
                tag_list = [str(t).strip() for t in tags if str(t).strip()][:10]
            else:
                tag_list = []
            if tag_list:
                properties["Tags"] = {"multi_select": [{"name": t[:50]} for t in tag_list]}

        # 7) KeyPoints (rich_text)
        key_points = data.get("key_points")
        if key_points:
            if isinstance(key_points, list):
                key_points_text = "\n".join(f"- {str(p)}" for p in key_points[:10])
            else:
                key_points_text = str(key_points)
            properties["KeyPoints"] = {"rich_text": [{"text": {"content": key_points_text[:2000]}}]}

        # 8) Category / Sentiment (select)
        category = str(data.get("category") or "").strip()
        if category:
            properties["Category"] = {"select": {"name": category[:50]}}

        sentiment = str(data.get("sentiment") or "").strip()
        if sentiment:
            properties["Sentiment"] = {"select": {"name": sentiment[:20]}}

        # 9) CreatedTime (date)
        properties["CreatedTime"] = {"date": {"start": datetime.now().isoformat()}}

        # 10) Transcript property (not recommended, disabled by default)
        transcript = str(data.get("transcript") or "").strip()
        if transcript and self.KEEP_TRANSCRIPT_PROPERTY:
            # Note: this content can still be truncated
            properties["Transcript"] = {"rich_text": [{"text": {"content": transcript[:2000]}}]}

        # 11) TranscriptPreview (optional; requires a matching Text column in Notion)
        if transcript and self.KEEP_TRANSCRIPT_PREVIEW:
            properties["TranscriptPreview"] = {
                "rich_text": [{"text": {"content": transcript[: self.TRANSCRIPT_PREVIEW_CHARS]}}]
            }

        return properties

    # -------------------- Children: page body blocks --------------------
    def _build_children(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        children: List[Dict[str, Any]] = []

        # Optional: place the summary in the page body for easier reading
        summary = str(data.get("summary") or "").strip()
        if summary and self.WRITE_SUMMARY_TO_PAGE:
            children.append(self._heading_2("Summary"))
            children.extend(self._paragraph_blocks(summary))

        transcript = str(data.get("transcript") or "").strip()
        if transcript and self.WRITE_TRANSCRIPT_TO_PAGE:
            if self.USE_TOGGLE_FOR_TRANSCRIPT:
                # Nest transcript blocks inside a toggle (collapsed by default)
                toggle_children = self._paragraph_blocks(transcript)
                children.append(self._toggle("Transcript", toggle_children))
            else:
                children.append(self._heading_2("Transcript"))
                children.extend(self._paragraph_blocks(transcript))

        return children

    def _append_blocks(self, page_id: str, blocks: List[Dict[str, Any]]) -> None:
        """Append blocks in batches to avoid oversized requests."""
        if not blocks:
            return
        batch_size = 100
        for i in range(0, len(blocks), batch_size):
            self.client.blocks.children.append(
                block_id=page_id,
                children=blocks[i:i + batch_size]
            )

    # -------------------- block helpers --------------------
    @staticmethod
    def _rt(text: str) -> List[Dict[str, Any]]:
        return [{"type": "text", "text": {"content": text}}]

    def _heading_2(self, text: str) -> Dict[str, Any]:
        return {
            "object": "block",
            "type": "heading_2",
            "heading_2": {"rich_text": self._rt(text[:2000])},
        }

    def _toggle(self, title: str, children: List[Dict[str, Any]]) -> Dict[str, Any]:
        # Note: toggle children may also be large; create_page appends in batches
        # Put the first batch inside the toggle because Notion supports nested children
        return {
            "object": "block",
            "type": "toggle",
            "toggle": {
                "rich_text": self._rt(title[:2000]),
                "children": children[:100],  # Seed the first batch; append the rest later at the page level
            },
        }

    def _paragraph_blocks(self, text: str) -> List[Dict[str, Any]]:
        """
        Split long text into multiple paragraph blocks.
        - Keep each paragraph content <= 1800 characters for safety
        - Blank lines force a paragraph break
        """
        max_len = 1800
        lines = text.splitlines()

        blocks: List[Dict[str, Any]] = []
        buf = ""

        def flush():
            nonlocal buf
            if not buf.strip():
                buf = ""
                return
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": self._rt(buf[:2000])},
            })
            buf = ""

        for line in lines:
            if not line.strip():
                flush()
                continue

            if len(buf) + len(line) + (1 if buf else 0) <= max_len:
                buf = (buf + "\n" + line) if buf else line
            else:
                flush()
                # Hard-split lines that are too long
                while len(line) > max_len:
                    chunk, line = line[:max_len], line[max_len:]
                    blocks.append({
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {"rich_text": self._rt(chunk)},
                    })
                buf = line

        flush()
        return blocks

    # -------------------- Query / deduplication --------------------
    def query_database(self, filter_dict: Optional[Dict] = None, page_size: int = 100) -> List[Dict]:
        try:
            resp = self.client.databases.query(
                database_id=self.database_id,
                filter=filter_dict,
                page_size=page_size
            )
            return resp.get("results", [])
        except Exception as e:
            raise Exception(f"Query failed: {str(e)}")

    def check_duplicate(self, url: str) -> bool:
        """
        Check whether the URL already exists to avoid duplicates.
        The current URL column uses rich_text, so we query with rich_text.equals.
        """
        try:
            results = self.query_database({
                "property": "URL",
                "rich_text": {"equals": url}
            })
            return len(results) > 0
        except Exception:
            return False


class MockNotionWriter:
    """Mock writer used when notion_client is unavailable; saves JSON locally."""

    def __init__(self, *args, **kwargs):
        self.data_store: List[Dict[str, Any]] = []
        print("📝 Using MockNotionWriter (test mode, nothing will be written to Notion)")

    def test_connection(self) -> bool:
        print("✅ Mock connection successful")
        return True

    def create_page(self, data: Dict[str, Any]) -> Dict[str, Any]:
        self.data_store.append(data)
        output_file = "notion_mock_output.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(self.data_store, f, ensure_ascii=False, indent=2)
        print(f"✅ Saved locally: {output_file}")
        return {"id": "mock-page-id", "data": data}

    def check_duplicate(self, url: str) -> bool:
        return any(item.get("url") == url for item in self.data_store)


def get_writer(token: Optional[str] = None, database_id: Optional[str] = None) -> Any:
    """
    Get a writer instance.
    - If notion_client is available and token/database_id are valid => NotionWriter
    - Otherwise => MockNotionWriter
    """
    if not USE_NOTION_CLIENT:
        return MockNotionWriter()

    try:
        return NotionWriter(token=token, database_id=database_id)
    except Exception as e:
        print(f"⚠️ NotionWriter initialization failed: {e}. Using Mock.")
        return MockNotionWriter()


if __name__ == "__main__":
    # ======= Example: uncomment the next two lines for a real Notion write, and make sure .env is configured =======
    # writer = NotionWriter()
    # writer.test_connection()

    # ======= Example: local test with the mock writer =======
    writer = MockNotionWriter()

    test_data = {
        'title': '测试视频 - 机器学习入门',
        'url': 'https://youtube.com/watch?v=test',
        'platform': 'YouTube',
        'transcript': '这是视频的转录文本...',
        'summary': '这是一个关于机器学习入门的视频...\n' * 500,  # 模拟超长文本
        'tags': ['机器学习', 'AI', '教程'],
        'key_points': ['要点1', '要点2', '要点3'],
        'category': '教育',
        'sentiment': 'positive'
    }

    result = writer.create_page(test_data)
    print(json.dumps(result, ensure_ascii=False, indent=2))
