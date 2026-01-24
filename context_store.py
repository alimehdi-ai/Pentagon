"""
Chat context storage for Pentagon.
Stores user/bot turns per session in memory and JSONL on disk.
"""

from __future__ import annotations

import json
import os
import threading
from typing import Dict, List, Optional


class ChatContextStore:
    def __init__(self, file_path: str, max_in_memory: int = 2000) -> None:
        self.file_path = file_path
        self.max_in_memory = max_in_memory
        self._lock = threading.Lock()
        self._data: Dict[str, Dict[str, List[dict]]] = {}
        self._ensure_dir()
        self._load_existing()

    def _ensure_dir(self) -> None:
        directory = os.path.dirname(self.file_path)
        if directory:
            os.makedirs(directory, exist_ok=True)

    def _load_existing(self) -> None:
        if not os.path.exists(self.file_path):
            return
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                        self._append_to_memory(record)
                    except json.JSONDecodeError:
                        continue
        except OSError:
            pass

    def _append_to_memory(self, record: dict) -> None:
        user_id = record.get("user_id")
        session_id = record.get("session_id")
        if not user_id or not session_id:
            return
        self._data.setdefault(user_id, {}).setdefault(session_id, []).append(record)

        # Trim oldest entries if needed
        total = sum(len(s) for u in self._data.values() for s in u.values())
        if total > self.max_in_memory:
            self._trim_oldest(total - self.max_in_memory)

    def _trim_oldest(self, count: int) -> None:
        removed = 0
        for user_id in list(self._data.keys()):
            for session_id in list(self._data[user_id].keys()):
                session_list = self._data[user_id][session_id]
                while session_list and removed < count:
                    session_list.pop(0)
                    removed += 1
                if not session_list:
                    del self._data[user_id][session_id]
            if not self._data[user_id]:
                del self._data[user_id]
            if removed >= count:
                return

    def add_message(
        self,
        user_id: str,
        session_id: str,
        user_text: str,
        bot_text: str,
        timestamp: str,
    ) -> None:
        record = {
            "user_id": user_id,
            "session_id": session_id,
            "user_text": user_text,
            "bot_text": bot_text,
            "timestamp": timestamp,
        }
        with self._lock:
            self._append_to_memory(record)
            try:
                with open(self.file_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
            except OSError:
                pass

    def get_history(self, user_id: str, session_id: str, limit: int = 10) -> List[dict]:
        sessions = self._data.get(user_id, {})
        history = sessions.get(session_id, [])
        return history[-limit:]

    def get_last_user_message(self, user_id: str, session_id: str) -> Optional[str]:
        history = self.get_history(user_id, session_id, limit=1)
        if not history:
            return None
        return history[-1].get("user_text")

    def get_last_bot_message(self, user_id: str, session_id: str) -> Optional[str]:
        history = self.get_history(user_id, session_id, limit=1)
        if not history:
            return None
        return history[-1].get("bot_text")

    def get_context_text(self, user_id: str, session_id: str, limit: int = 5) -> str:
        history = self.get_history(user_id, session_id, limit=limit)
        if not history:
            return ""
        lines = []
        for item in history:
            user_text = item.get("user_text", "")
            bot_text = item.get("bot_text", "")
            if user_text:
                lines.append(f"User: {user_text}")
            if bot_text:
                lines.append(f"Bot: {bot_text}")
        return "\n".join(lines)
