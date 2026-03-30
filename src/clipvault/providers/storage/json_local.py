# -*- coding: utf-8 -*-
"""
Local JSON file storage — used as mock / offline fallback.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


from ..base import StorageWriter


class JsonStorageWriter(StorageWriter):
    """Persist results as a local JSON file."""

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._store_path = self.output_dir / "results.json"
        self._store: List[Dict[str, Any]] = self._load()

    def write(self, data: Dict[str, Any]) -> Dict[str, Any]:
        self._store.append(data)
        self._flush()
        return {"path": str(self._store_path), "index": len(self._store) - 1}

    def check_duplicate(self, url: str) -> bool:
        return any(item.get("url") == url for item in self._store)

    def _load(self) -> List[Dict[str, Any]]:
        if self._store_path.exists():
            try:
                with open(self._store_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                return []
        return []

    def _flush(self) -> None:
        with open(self._store_path, "w", encoding="utf-8") as f:
            json.dump(self._store, f, ensure_ascii=False, indent=2)
