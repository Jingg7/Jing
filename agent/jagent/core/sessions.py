from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

from .history import HistoryStore

SESSION_FILE_SUFFIX = ".json"
META_FILE_SUFFIX = ".meta.json"
DEFAULT_SESSION_TITLE = "新会话"
_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


@dataclass(frozen=True)
class SessionInfo:
    session_id: str
    title: str
    path: Path
    created_at: datetime
    updated_at: datetime
    saved: bool = False


class SessionStore:
    def __init__(self, directory: str | Path):
        self.directory = Path(directory).expanduser()

    def create(self, title: str | None = None) -> SessionInfo:
        self.directory.mkdir(parents=True, exist_ok=True)
        now = datetime.now()
        session_id = now.strftime("%Y%m%d-%H%M%S")
        candidate = session_id
        counter = 1
        while self._message_path(candidate).exists():
            candidate = f"{session_id}-{counter:02d}"
            counter += 1
        clean_title = self._clean_title(title) or DEFAULT_SESSION_TITLE
        path = self._message_path(candidate)
        HistoryStore(path).save([])
        info = SessionInfo(
            session_id=candidate,
            title=clean_title,
            path=path,
            created_at=now,
            updated_at=now,
            saved=False,
        )
        self._write_meta(info)
        return info

    def history(self, session_id: str) -> HistoryStore:
        return HistoryStore(self._require_message_path(session_id))

    def save(
        self,
        session_id: str,
        title: str | None,
        messages: Sequence[dict[str, Any]],
    ) -> SessionInfo:
        path = self._require_message_path(session_id)
        existing = self.get(session_id)
        clean_title = self._clean_title(title) or (
            existing.title if existing else DEFAULT_SESSION_TITLE
        )
        HistoryStore(path).save(messages)
        now = datetime.now()
        info = SessionInfo(
            session_id=self._require_id(session_id),
            title=clean_title,
            path=path,
            created_at=existing.created_at if existing else now,
            updated_at=now,
            saved=True,
        )
        self._write_meta(info)
        return info

    def get(self, session_id: str) -> SessionInfo | None:
        resolved_id = self._require_id(session_id)
        path = self._message_path(resolved_id)
        if not path.is_file():
            return None
        meta = self._read_meta(resolved_id)
        now = datetime.now().timestamp()
        if meta is not None:
            title = self._clean_title(meta.get("title")) or resolved_id
            created_at = self._parse_datetime(meta.get("created_at")) or datetime.fromtimestamp(
                path.stat().st_ctime
            )
            updated_at = self._parse_datetime(meta.get("updated_at")) or datetime.fromtimestamp(
                path.stat().st_mtime
            )
            saved = bool(meta.get("saved", True))
        else:
            title = resolved_id
            created_at = datetime.fromtimestamp(path.stat().st_ctime)
            updated_at = datetime.fromtimestamp(path.stat().st_mtime)
            saved = True
        return SessionInfo(
            session_id=resolved_id,
            title=title,
            path=path,
            created_at=created_at,
            updated_at=updated_at,
            saved=saved,
        )

    def list_sessions(self) -> list[SessionInfo]:
        if not self.directory.is_dir():
            return []
        infos: list[SessionInfo] = []
        for path in self.directory.glob(f"*{SESSION_FILE_SUFFIX}"):
            if path.name.endswith(META_FILE_SUFFIX) or not path.is_file():
                continue
            session_id = path.stem
            if not _ID_PATTERN.fullmatch(session_id):
                continue
            info = self.get(session_id)
            if info is not None and info.saved:
                infos.append(info)
        return sorted(infos, key=lambda info: info.updated_at, reverse=True)

    def find(self, query: str) -> SessionInfo | None:
        needle = query.strip()
        if not needle:
            return None
        candidates = self.list_sessions()
        for info in candidates:
            if info.session_id == needle:
                return info
        lowered = needle.casefold()
        prefix_matches = [
            info for info in candidates if info.session_id.casefold().startswith(lowered)
        ]
        if len(prefix_matches) == 1:
            return prefix_matches[0]
        title_matches = [info for info in candidates if info.title.casefold() == lowered]
        if len(title_matches) == 1:
            return title_matches[0]
        contains_matches = [
            info for info in candidates if lowered in info.title.casefold()
        ]
        return contains_matches[0] if len(contains_matches) == 1 else None

    def _message_path(self, session_id: str) -> Path:
        return self.directory / f"{session_id}{SESSION_FILE_SUFFIX}"

    def _meta_path(self, session_id: str) -> Path:
        return self.directory / f"{session_id}{META_FILE_SUFFIX}"

    def _require_message_path(self, session_id: str) -> Path:
        resolved_id = self._require_id(session_id)
        path = self._message_path(resolved_id)
        if not path.is_file():
            raise FileNotFoundError(f"会话不存在: {resolved_id}")
        return path

    def _require_id(self, value: str) -> str:
        session_id = value.strip()
        if not _ID_PATTERN.fullmatch(session_id):
            raise ValueError(f"无效的会话编号: {value}")
        return session_id

    @staticmethod
    def _clean_title(value: Any) -> str:
        if not isinstance(value, str):
            return ""
        return " ".join(value.strip().split())[:80]

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if not isinstance(value, str):
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    def _read_meta(self, session_id: str) -> dict[str, Any] | None:
        path = self._meta_path(session_id)
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return data if isinstance(data, dict) else None

    def _write_meta(self, info: SessionInfo) -> None:
        payload = {
            "id": info.session_id,
            "title": info.title,
            "created_at": info.created_at.isoformat(timespec="seconds"),
            "updated_at": info.updated_at.isoformat(timespec="seconds"),
            "saved": info.saved,
        }
        path = self._meta_path(info.session_id)
        temp_path = path.with_name(path.name + ".tmp")
        with temp_path.open("w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
        temp_path.replace(path)
