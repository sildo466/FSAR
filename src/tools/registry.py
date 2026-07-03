"""FSAR Tool Registry — register/discover tools, OpenAI function calling format."""

from __future__ import annotations

import types
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from src.utils.decorators import track_decision
from src.utils.logger import logger


class Tool(ABC):
    """Base class for all FSAR tools."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Tool name for function calling."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Tool description for LLM."""

    @property
    @abstractmethod
    def parameters(self) -> dict:
        """JSON Schema for parameters."""

    @property
    @abstractmethod
    def risk_level(self) -> str:
        """Risk level: SAFE, LOW, MEDIUM, HIGH, CRITICAL."""

    @abstractmethod
    async def execute(self, **kwargs) -> str:
        """Execute the tool with given arguments. Returns result string."""

    def to_openai_schema(self) -> dict:
        """Convert to OpenAI function calling format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    """Registry for managing and discovering tools."""

    def __init__(self, auto_track: bool = True):
        self._tools: Dict[str, Tool] = {}
        self._tracked: set[str] = set()
        self._auto_track = auto_track

    def register(self, tool: Tool) -> None:
        """Register a tool. If auto_track=True, wraps execute() with @track_decision."""
        if self._auto_track and tool.name not in self._tracked:
            bound = tool.execute
            underlying = getattr(bound, "__func__", bound)
            if not getattr(underlying, "_fsar_tracked", False):
                wrapped = track_decision(underlying)
                tool.execute = types.MethodType(wrapped, tool)  # type: ignore[method-assign]
            self._tracked.add(tool.name)
            logger.debug(f"Tool '{tool.name}' registered with @track_decision")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[Tool]:
        """Get a tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> List[Tool]:
        """List all registered tools."""
        return list(self._tools.values())

    def get_tools_for_llm(self) -> List[dict]:
        """Get all tools in OpenAI function calling format."""
        return [tool.to_openai_schema() for tool in self._tools.values()]

    def get_tool_names(self) -> List[str]:
        """Get all tool names."""
        return list(self._tools.keys())

    async def execute(self, name: str, **kwargs) -> str:
        """Execute a tool by name."""
        tool = self.get(name)
        if tool is None:
            return f"Error: Unknown tool '{name}'"
        return await tool.execute(**kwargs)
