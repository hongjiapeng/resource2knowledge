# -*- coding: utf-8 -*-
"""
📝 Notion Writer Module
将转录和摘要写入 Notion 数据库
"""

import os
import json
from datetime import datetime
from typing import Optional, Dict, List
from pathlib import Path

# 加载 .env 文件
from dotenv import load_dotenv
load_dotenv()

# Notion 客户端 (二选一)
try:
    from notion_client import Client
    USE_NOTION_CLIENT = True
except ImportError:
    USE_NOTION_CLIENT = False
    print("⚠️ notion_client 未安装，将使用备用方法")


class NotionWriter:
    """Notion 数据库写入器"""
    
    # 数据库字段映射
    PROPERTY_MAP = {
        'title': 'Title',
        'url': 'URL',
        'platform': 'Platform',
        'transcript': 'Transcript',
        'summary': 'Summary',
        'tags': 'Tags',
        'created_time': 'CreatedTime',
        'key_points': 'KeyPoints',
        'category': 'Category',
        'sentiment': 'Sentiment',
    }
    
    def __init__(
        self,
        token: Optional[str] = None,
        database_id: Optional[str] = None,
        env_file: str = ".env"
    ):
        """
        初始化 Notion 写入器
        
        Args:
            token: Notion API Token (默认从环境变量读取)
            database_id: Notion 数据库 ID (默认从环境变量读取)
            env_file: .env 文件路径
        """
        # 加载环境变量
        self.token = token or os.getenv("NOTION_TOKEN") or self._load_env(env_file, "NOTION_TOKEN")
        self.database_id = database_id or os.getenv("NOTION_DATABASE_ID") or self._load_env(env_file, "NOTION_DATABASE_ID")
        
        if not self.token:
            raise ValueError("未设置 NOTION_TOKEN")
        if not self.database_id:
            raise ValueError("未设置 NOTION_DATABASE_ID")
        
        self.client = None
        if USE_NOTION_CLIENT:
            self.client = Client(auth=self.token)
    
    def _load_env(self, env_file: str, key: str) -> Optional[str]:
        """从 .env 文件加载环境变量"""
        env_path = Path(env_file)
        if not env_path.exists():
            return None
        
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line.startswith('#') or not line:
                    continue
                if '=' in line:
                    k, v = line.split('=', 1)
                    if k.strip() == key:
                        return v.strip()
        return None
    
    def test_connection(self) -> bool:
        """测试 Notion 连接"""
        try:
            if self.client:
                self.client.databases.retrieve(database_id=self.database_id)
                print("✅ Notion 连接成功")
                return True
            else:
                print("⚠️ notion_client 未安装，跳过连接测试")
                return False
        except Exception as e:
            print(f"❌ Notion 连接失败: {e}")
            return False
    
    def create_page(self, data: Dict) -> Dict:
        """
        创建 Notion 页面
        
        Args:
            data: 包含 title, url, platform, transcript, summary, tags 等的字典
            
        Returns:
            创建的页面信息
        """
        if not self.client:
            raise Exception("Notion 客户端未初始化")
        
        # 构建页面属性
        properties = self._build_properties(data)
        
        try:
            # 创建页面
            page = self.client.pages.create(
                parent={"database_id": self.database_id},
                properties=properties
            )
            
            print(f"✅ 已创建 Notion 页面: {page.get('id', 'unknown')}")
            return page
            
        except Exception as e:
            raise Exception(f"创建 Notion 页面失败: {str(e)}")
    
    def _build_properties(self, data: Dict) -> Dict:
        """构建 Notion 页面属性"""
        properties = {}
        
        # Title - Notion 数据库默认属性名是 "Name"
        if 'title' in data:
            properties['Name'] = {
                'title': [{'text': {'content': str(data['title'])[:100]}}]
            }
        
        # URL - 用 rich_text 存储
        if 'url' in data:
            properties['URL'] = {
                'rich_text': [{'text': {'content': str(data['url'])}}]
            }
        
        # Platform
        if 'platform' in data:
            properties['Platform'] = {
                'select': {'name': str(data['platform'])}
            }
        
        # Transcript (长文本)
        if 'transcript' in data:
            transcript_text = str(data['transcript'])
            # Notion 限制: rich_text 最大 2000 字符
            properties['Transcript'] = {
                'rich_text': [{'text': {'content': transcript_text[:2000]}}]
            }
        
        # Summary (长文本)
        if 'summary' in data:
            summary_text = str(data['summary'])
            properties['Summary'] = {
                'rich_text': [{'text': {'content': summary_text[:2000]}}]
            }
        
        # Tags (多选)
        if 'tags' in data:
            tags = data['tags']
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(',')][:10]
            elif isinstance(tags, list):
                tags = tags[:10]
            else:
                tags = []
            
            properties['Tags'] = {
                'multi_select': [{'name': str(t)[:50]} for t in tags if t]
            }
        
        # Key Points (可选，用文本存储)
        if 'key_points' in data:
            key_points = data['key_points']
            if isinstance(key_points, list):
                key_points_text = '\n'.join(f"- {p}" for p in key_points[:5])
            else:
                key_points_text = str(key_points)
            
            properties['KeyPoints'] = {
                'rich_text': [{'text': {'content': key_points_text[:1000]}}]
            }
        
        # Category (可选)
        if 'category' in data:
            properties['Category'] = {
                'select': {'name': str(data['category'])[:50]}
            }
        
        # Sentiment (可选)
        if 'sentiment' in data:
            properties['Sentiment'] = {
                'select': {'name': str(data['sentiment'])[:20]}
            }
        
        # CreatedTime (自动设置)
        properties['CreatedTime'] = {
            'date': {'start': datetime.now().isoformat()}
        }
        
        return properties
    
    def query_database(
        self,
        filter_dict: Optional[Dict] = None,
        page_size: int = 100
    ) -> List[Dict]:
        """
        查询 Notion 数据库
        
        Args:
            filter_dict: 过滤条件
            page_size: 返回数量
            
        Returns:
            页面列表
        """
        if not self.client:
            raise Exception("Notion 客户端未初始化")
        
        try:
            response = self.client.databases.query(
                database_id=self.database_id,
                filter=filter_dict,
                page_size=page_size
            )
            return response.get('results', [])
        except Exception as e:
            raise Exception(f"查询失败: {str(e)}")
    
    def check_duplicate(self, url: str) -> bool:
        """检查 URL 是否已存在 (去重)"""
        try:
            results = self.query_database({
                'property': 'URL',
                'url': {'equals': url}
            })
            return len(results) > 0
        except:
            return False


class MockNotionWriter:
    """Mock 写入器 (用于测试或 Notion 不可用时)"""
    
    def __init__(self, *args, **kwargs):
        self.data_store = []
        print("📝 使用 Mock Notion Writer (测试模式)")
    
    def test_connection(self) -> bool:
        print("✅ Mock 连接成功")
        return True
    
    def create_page(self, data: Dict) -> Dict:
        # 保存到本地 JSON
        self.data_store.append(data)
        
        output_file = "notion_mock_output.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(self.data_store, f, ensure_ascii=False, indent=2)
        
        print(f"✅ 已保存到本地: {output_file}")
        return {'id': 'mock-page-id', 'data': data}
    
    def check_duplicate(self, url: str) -> bool:
        return any(item.get('url') == url for item in self.data_store)


def get_writer(token: Optional[str] = None, database_id: Optional[str] = None) -> NotionWriter:
    """
    获取 Notion 写入器实例
    
    如果 notion_client 不可用或 token 为空，返回 Mock 写入器
    """
    if not token or not USE_NOTION_CLIENT:
        return MockNotionWriter()
    
    try:
        return NotionWriter(token=token, database_id=database_id)
    except Exception as e:
        print(f"⚠️ Notion 初始化失败: {e}，使用 Mock")
        return MockNotionWriter()


if __name__ == "__main__":
    # 测试
    import sys
    
    # 尝试使用 Mock 模式测试
    writer = MockNotionWriter()
    
    test_data = {
        'title': '测试视频 - 机器学习入门',
        'url': 'https://youtube.com/watch?v=test',
        'platform': 'YouTube',
        'transcript': '这是视频的转录文本...',
        'summary': '这是一个关于机器学习入门的视频...',
        'tags': ['机器学习', 'AI', '教程'],
        'key_points': ['要点1', '要点2', '要点3'],
        'category': '教育',
        'sentiment': 'positive'
    }
    
    result = writer.create_page(test_data)
    print(json.dumps(result, indent=2, ensure_ascii=False))
