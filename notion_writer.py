# -*- coding: utf-8 -*-
"""
📝 Notion Writer Module (Full Script)
- 将视频元数据写入 Notion 数据库 properties
- 将超长 Transcript /（可选）Summary 写入页面正文 blocks，避免 2000 字符截断
- 可选：保留 TranscriptPreview 字段（前 N 字），方便表格快速浏览
"""

import os
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Any

from dotenv import load_dotenv

# 加载 .env
load_dotenv()

# Notion 客户端
try:
    from notion_client import Client
    USE_NOTION_CLIENT = True
except ImportError:
    USE_NOTION_CLIENT = False
    print("⚠️ notion_client 未安装，将使用 MockNotionWriter（仅本地保存 JSON）")


class NotionWriter:
    """Notion 数据库写入器（properties + page blocks）"""

    # =============== 你可以按需调整的开关 ===============
    WRITE_TRANSCRIPT_TO_PAGE = True          # ✅ transcript 写入页面正文
    WRITE_SUMMARY_TO_PAGE = False            # 可选：summary 也写入页面正文
    KEEP_TRANSCRIPT_PROPERTY = False         # ❌ 不再写 Transcript 字段（避免截断）
    KEEP_TRANSCRIPT_PREVIEW = False          # 可选：保留 TranscriptPreview（前 N 字）
    TRANSCRIPT_PREVIEW_CHARS = 500           # TranscriptPreview 长度
    USE_TOGGLE_FOR_TRANSCRIPT = True         # ✅ transcript 放到 Toggle 里（默认折叠）
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
            raise ValueError("未设置 NOTION_TOKEN")
        if not self.database_id:
            raise ValueError("未设置 NOTION_DATABASE_ID")
        if not USE_NOTION_CLIENT:
            raise ValueError("notion_client 未安装（pip install notion-client）")

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
            print("✅ Notion 连接成功")
            return True
        except Exception as e:
            print(f"❌ Notion 连接失败: {e}")
            return False

    # -------------------- 核心：创建页面 --------------------
    def create_page(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """创建 Notion 页面：properties + children（正文 blocks）"""
        properties = self._build_properties(data)
        children = self._build_children(data)

        try:
            # 先创建页面（children 先塞一部分，避免一次过多导致失败）
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
            print(f"✅ 已创建 Notion 页面: {page_id or 'unknown'}")

            # 如果 children 很多，剩余部分再 append
            if children and len(children) > 100 and page_id:
                self._append_blocks(page_id, children[100:])

            return page

        except Exception as e:
            raise Exception(f"创建 Notion 页面失败: {str(e)}")

    # -------------------- properties：数据库列 --------------------
    def _build_properties(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        构建 Notion 页面属性
        - Name: title（页面主标题）
        - Title: rich_text（辅助标题/原始标题/ID）
        - URL: rich_text（你当前数据库就是 rich_text 类型）
        - 其它：Platform/Tags/Category/Sentiment/Summary/KeyPoints/CreatedTime
        - Transcript 字段默认不写（避免截断），可通过开关保留
        """
        properties: Dict[str, Any] = {}

        # 1) Name（title，Notion 页面主标题）
        title = str(data.get("title") or "").strip()
        if not title:
            fallback = data.get("video_id") or data.get("id") or "Untitled"
            title = str(fallback)
        properties["Name"] = {"title": [{"text": {"content": title[:100]}}]}

        # 2) Title（rich_text：原始标题/来源ID/备用标题）
        platform = str(data.get("platform") or "").strip()
        aux_title = str(data.get("raw_title") or data.get("source_title") or "").strip()
        if not aux_title and platform:
            aux_title = f"【{platform}】{title}"
        elif not aux_title:
            aux_title = title

        properties["Title"] = {"rich_text": [{"text": {"content": aux_title[:2000]}}]}

        # 3) URL（你现在数据库 URL 是 rich_text 类型）
        url = str(data.get("url") or "").strip()
        if url:
            properties["URL"] = {"rich_text": [{"text": {"content": url}}]}

        # 4) Platform（select）
        if platform:
            properties["Platform"] = {"select": {"name": platform[:50]}}

        # 5) Summary（rich_text，<=2000）
        summary = str(data.get("summary") or "").strip()
        if summary:
            properties["Summary"] = {"rich_text": [{"text": {"content": summary[:2000]}}]}

        # 6) Tags（multi_select）
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

        # 7) KeyPoints（rich_text）
        key_points = data.get("key_points")
        if key_points:
            if isinstance(key_points, list):
                key_points_text = "\n".join(f"- {str(p)}" for p in key_points[:10])
            else:
                key_points_text = str(key_points)
            properties["KeyPoints"] = {"rich_text": [{"text": {"content": key_points_text[:2000]}}]}

        # 8) Category / Sentiment（select）
        category = str(data.get("category") or "").strip()
        if category:
            properties["Category"] = {"select": {"name": category[:50]}}

        sentiment = str(data.get("sentiment") or "").strip()
        if sentiment:
            properties["Sentiment"] = {"select": {"name": sentiment[:20]}}

        # 9) CreatedTime（date）
        properties["CreatedTime"] = {"date": {"start": datetime.now().isoformat()}}

        # 10) Transcript 字段（不推荐，默认关闭；如需保留自行开关）
        transcript = str(data.get("transcript") or "").strip()
        if transcript and self.KEEP_TRANSCRIPT_PROPERTY:
            # 注意：这里仍然会被截断
            properties["Transcript"] = {"rich_text": [{"text": {"content": transcript[:2000]}}]}

        # 11) TranscriptPreview（可选，需要你在 Notion 数据库新增一个 Text 列：TranscriptPreview）
        if transcript and self.KEEP_TRANSCRIPT_PREVIEW:
            properties["TranscriptPreview"] = {
                "rich_text": [{"text": {"content": transcript[: self.TRANSCRIPT_PREVIEW_CHARS]}}]
            }

        return properties

    # -------------------- children：页面正文 blocks --------------------
    def _build_children(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        children: List[Dict[str, Any]] = []

        # 可选：把 Summary 放正文里（更舒服阅读）
        summary = str(data.get("summary") or "").strip()
        if summary and self.WRITE_SUMMARY_TO_PAGE:
            children.append(self._heading_2("Summary"))
            children.extend(self._paragraph_blocks(summary))

        transcript = str(data.get("transcript") or "").strip()
        if transcript and self.WRITE_TRANSCRIPT_TO_PAGE:
            if self.USE_TOGGLE_FOR_TRANSCRIPT:
                # Toggle 内嵌 transcript blocks（默认折叠）
                toggle_children = self._paragraph_blocks(transcript)
                children.append(self._toggle("Transcript", toggle_children))
            else:
                children.append(self._heading_2("Transcript"))
                children.extend(self._paragraph_blocks(transcript))

        return children

    def _append_blocks(self, page_id: str, blocks: List[Dict[str, Any]]) -> None:
        """分批追加 blocks，避免单次请求过大"""
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
        # 注意：toggle 的 children 同样可能很多；create_page 时我们会分批 append
        # 这里先放在 toggle 里，Notion 允许 toggle 有 children
        return {
            "object": "block",
            "type": "toggle",
            "toggle": {
                "rich_text": self._rt(title[:2000]),
                "children": children[:100],  # 先塞一部分，剩余会在 page append 阶段追加到页面末尾（简化实现）
            },
        }

    def _paragraph_blocks(self, text: str) -> List[Dict[str, Any]]:
        """
        把长文本拆成多个 paragraph blocks。
        - 每个 paragraph content 建议 <= 1800，留余量更稳
        - 空行会强制换段
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
                # 单行过长则硬切
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

    # -------------------- 查询 / 去重 --------------------
    def query_database(self, filter_dict: Optional[Dict] = None, page_size: int = 100) -> List[Dict]:
        try:
            resp = self.client.databases.query(
                database_id=self.database_id,
                filter=filter_dict,
                page_size=page_size
            )
            return resp.get("results", [])
        except Exception as e:
            raise Exception(f"查询失败: {str(e)}")

    def check_duplicate(self, url: str) -> bool:
        """
        检查 URL 是否已存在（去重）
        你现在 URL 列是 rich_text 类型，所以用 rich_text equals
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
    """Mock 写入器（用于 notion_client 不可用时：本地保存 JSON）"""

    def __init__(self, *args, **kwargs):
        self.data_store: List[Dict[str, Any]] = []
        print("📝 使用 MockNotionWriter（测试模式，不会写入 Notion）")

    def test_connection(self) -> bool:
        print("✅ Mock 连接成功")
        return True

    def create_page(self, data: Dict[str, Any]) -> Dict[str, Any]:
        self.data_store.append(data)
        output_file = "notion_mock_output.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(self.data_store, f, ensure_ascii=False, indent=2)
        print(f"✅ 已保存到本地: {output_file}")
        return {"id": "mock-page-id", "data": data}

    def check_duplicate(self, url: str) -> bool:
        return any(item.get("url") == url for item in self.data_store)


def get_writer(token: Optional[str] = None, database_id: Optional[str] = None) -> Any:
    """
    获取 Writer 实例
    - notion_client 可用且 token/database_id 有效 => NotionWriter
    - 否则 => MockNotionWriter
    """
    if not USE_NOTION_CLIENT:
        return MockNotionWriter()

    try:
        return NotionWriter(token=token, database_id=database_id)
    except Exception as e:
        print(f"⚠️ NotionWriter 初始化失败: {e}，使用 Mock")
        return MockNotionWriter()


if __name__ == "__main__":
    # ======= 示例：真实写入 Notion 时，把下面两行注释取消，并确保 .env 配好 =======
    # writer = NotionWriter()
    # writer.test_connection()

    # ======= 示例：本地测试（Mock） =======
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