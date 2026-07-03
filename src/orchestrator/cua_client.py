"""FSAR CUA Client — 通过 MCP 连接 cua-driver"""

import asyncio
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from src.utils.logger import logger

CUA_BINARY = r"C:\Users\TANG\AppData\Local\Programs\Cua\cua-driver\bin\cua-driver.exe"


class CUAClient:
    """CUA MCP 客户端 — 封装所有 Computer Use 操作"""

    def __init__(self):
        self._session: ClientSession | None = None
        self._read = None
        self._write = None
        self._context_manager = None

    async def connect(self):
        """连接到 CUA driver"""
        server_params = StdioServerParameters(
            command=CUA_BINARY,
            args=[],
        )
        self._context_manager = stdio_client(server_params)
        self._read, self._write = await self._context_manager.__aenter__()
        self._session = ClientSession(self._read, self._write)
        await self._session.__aenter__()
        await self._session.initialize()
        logger.info("CUA driver connected")

    async def disconnect(self):
        """断开连接"""
        try:
            if self._session:
                await self._session.__aexit__(None, None, None)
        except Exception:
            pass
        try:
            if self._context_manager:
                await self._context_manager.__aexit__(None, None, None)
        except Exception:
            pass
        self._session = None
        self._context_manager = None

    async def call(self, tool_name: str, arguments: dict | None = None) -> str:
        """调用 CUA 工具，返回文本结果"""
        result = await self._session.call_tool(tool_name, arguments or {})
        if result.content and hasattr(result.content[0], 'text'):
            return result.content[0].text
        return ""

    async def call_rich(self, tool_name: str, arguments: dict | None = None) -> list:
        """调用 CUA 工具，返回所有内容块（文本+图片）"""
        result = await self._session.call_tool(tool_name, arguments or {})
        blocks = []
        for c in result.content:
            if hasattr(c, 'text'):
                blocks.append({"type": "text", "data": c.text})
            elif hasattr(c, 'data'):
                blocks.append({"type": "image", "data": c.data, "mime": getattr(c, 'mimeType', 'image/png')})
        return blocks

    # === 高级封装 ===

    async def list_apps(self) -> list:
        """列出所有应用"""
        result = await self.call("list_apps")
        return result

    async def list_windows(self, pid: int | None = None) -> list:
        """列出窗口"""
        args = {}
        if pid:
            args["pid"] = pid
        result = await self.call("list_windows", args)
        return result

    async def get_window_state(self, pid: int, window_id: int, query: str | None = None) -> dict:
        """获取窗口状态（截图 + 元素树）"""
        args = {"pid": pid, "window_id": window_id}
        if query:
            args["query"] = query
        result = await self.call("get_window_state", args)
        return result

    async def launch_app(self, name: str | None = None, path: str | None = None) -> dict:
        """启动应用"""
        args = {}
        if name:
            args["name"] = name
        if path:
            args["path"] = path
        result = await self.call("launch_app", args)
        return result

    async def click(self, pid: int, window_id: int, element_index: int | None = None,
                    x: int | None = None, y: int | None = None,
                    button: str = "left", count: int = 1) -> Any:
        """点击元素"""
        args = {"pid": pid, "window_id": window_id}
        if element_index is not None:
            args["element_index"] = element_index
        elif x is not None and y is not None:
            args["x"] = x
            args["y"] = y
        args["button"] = button
        args["count"] = count
        return await self.call("click", args)

    async def type_text(self, pid: int, text: str, window_id: int | None = None,
                        element_index: int | None = None) -> Any:
        """输入文字"""
        args = {"pid": pid, "text": text}
        if window_id:
            args["window_id"] = window_id
        if element_index is not None:
            args["element_index"] = element_index
        return await self.call("type_text", args)

    async def press_key(self, pid: int, key: str, window_id: int | None = None) -> Any:
        """按键"""
        args = {"pid": pid, "key": key}
        if window_id:
            args["window_id"] = window_id
        return await self.call("press_key", args)

    async def hotkey(self, pid: int, keys: list[str], window_id: int | None = None) -> Any:
        """快捷键"""
        args = {"pid": pid, "keys": keys}
        if window_id:
            args["window_id"] = window_id
        return await self.call("hotkey", args)

    async def scroll(self, pid: int, direction: str, amount: int = 3,
                     window_id: int | None = None) -> Any:
        """滚动"""
        args = {"pid": pid, "direction": direction, "amount": amount}
        if window_id:
            args["window_id"] = window_id
        return await self.call("scroll", args)

    async def kill_app(self, pid: int) -> Any:
        """杀掉进程"""
        return await self.call("kill_app", {"pid": pid})


# 全局实例
_client: CUAClient | None = None


async def get_cua_client() -> CUAClient:
    """获取全局 CUA 客户端"""
    global _client
    if _client is None:
        _client = CUAClient()
        await _client.connect()
    return _client
