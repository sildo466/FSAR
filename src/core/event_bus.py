"""FSAR 事件总线 — 模块间通信"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Coroutine
from uuid import uuid4

from src.utils.logger import logger


class EventType(Enum):
    """事件类型"""
    # 用户交互
    USER_MESSAGE = "user_message"        # 用户输入
    AGENT_RESPONSE = "agent_response"    # Agent 回复

    # 工具/操作
    TOOL_CALL = "tool_call"              # 工具调用
    TOOL_RESULT = "tool_result"          # 工具结果
    SCREEN_CAPTURE = "screen_capture"    # 截图事件

    # 系统
    SYSTEM_EVENT = "system_event"        # 系统事件
    ERROR = "error"                      # 错误

    # 记忆
    MEMORY_EVENT = "memory_event"        # 记忆相关事件

    # 进化
    REFLECTION = "reflection"            # 自我反思


@dataclass
class Event:
    """事件对象"""
    type: EventType
    data: Any = None
    source: str = ""
    id: str = field(default_factory=lambda: uuid4().hex[:8])
    timestamp: datetime = field(default_factory=datetime.now)

    def __str__(self):
        return f"[{self.type.value}] {self.source}: {str(self.data)[:80]}"


# 事件处理函数类型
EventHandler = Callable[[Event], Coroutine[Any, Any, None]]


class EventBus:
    """事件总线 — 发布/订阅模式"""

    def __init__(self):
        self._handlers: dict[EventType, list[EventHandler]] = {}
        self._global_handlers: list[EventHandler] = []
        self._event_log: list[Event] = []

    def on(self, event_type: EventType, handler: EventHandler):
        """订阅特定类型的事件"""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    def on_all(self, handler: EventHandler):
        """订阅所有事件"""
        self._global_handlers.append(handler)

    async def emit(self, event: Event):
        """发布事件"""
        self._event_log.append(event)
        logger.debug(f"Event emitted: {event}")

        # 调用特定类型的处理器
        handlers = self._handlers.get(event.type, [])
        for handler in handlers:
            try:
                await handler(event)
            except Exception as e:
                logger.error(f"Event handler error for {event.type.value}: {e}")

        # 调用全局处理器
        for handler in self._global_handlers:
            try:
                await handler(event)
            except Exception as e:
                logger.error(f"Global event handler error: {e}")

    def get_log(self, event_type: EventType | None = None, limit: int = 100) -> list[Event]:
        """获取事件日志"""
        if event_type:
            filtered = [e for e in self._event_log if e.type == event_type]
        else:
            filtered = self._event_log
        return filtered[-limit:]

    def clear_log(self):
        """清空事件日志"""
        self._event_log.clear()


# 全局事件总线实例
_event_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    """获取全局事件总线实例"""
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus
