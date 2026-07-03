"""FSAR 短期记忆 — 当前对话上下文"""

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from src.utils.config import get_config


@dataclass
class Message:
    """对话消息"""
    role: str           # "user" / "assistant" / "system"
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Message":
        return cls(
            role=data["role"],
            content=data["content"],
            timestamp=datetime.fromisoformat(data["timestamp"]) if "timestamp" in data else datetime.now(),
            metadata=data.get("metadata", {}),
        )


class ShortTermMemory:
    """短期记忆 — 维护当前对话上下文"""

    def __init__(self, max_size: int | None = None):
        config = get_config()
        self._max_size = max_size or config.short_term_window
        self._messages: deque[Message] = deque(maxlen=self._max_size)

    def add(self, role: str, content: str, metadata: dict | None = None):
        """添加一条消息"""
        msg = Message(role=role, content=content, metadata=metadata or {})
        self._messages.append(msg)

    def get_messages(self, last_n: int | None = None) -> list[Message]:
        """获取消息列表"""
        if last_n is None:
            return list(self._messages)
        return list(self._messages)[-last_n:]

    def get_context_for_llm(self, last_n: int | None = None) -> list[dict]:
        """获取 LLM 格式的上下文"""
        messages = self.get_messages(last_n)
        return [{"role": m.role, "content": m.content} for m in messages]

    def clear(self):
        """清空对话上下文"""
        self._messages.clear()

    @property
    def length(self) -> int:
        return len(self._messages)

    @property
    def is_empty(self) -> bool:
        return len(self._messages) == 0
