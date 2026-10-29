from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence


class HistoryStore:
    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser()

    def load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            with self.path.open(encoding="utf-8") as file:
                data = json.load(file)
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(data, list):
            return []
        return [dict(message) for message in data if isinstance(message, dict)]

    def save(self, messages: Sequence[Mapping[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_name(self.path.name + ".tmp")
        with temp_path.open("w", encoding="utf-8") as file:
            json.dump(list(messages), file, ensure_ascii=False, indent=2)
        temp_path.replace(self.path)
