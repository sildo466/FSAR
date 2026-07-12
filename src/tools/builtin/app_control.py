"""FSAR app_control tool — launch apps via URL scheme / start command / ShellExecute."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from typing import Optional

from src.tools.registry import Tool
from src.utils.logger import logger


_ALIAS_MAP = {
    "记事本": "notepad",
    "计算器": "calc",
    "画图": "mspaint",
    "资源管理器": "explorer",
    "任务管理器": "taskmgr",
    "控制面板": "control",
    "命令行": "cmd",
    "终端": "wt",
    "终端2": "wt",
    "浏览器": "chrome",
    "edge": "msedge",
    "vscode": "code",
    "微信": "WeChat",
    "qq": "QQ",
    "钉钉": "DingTalk",
    "飞书": "Feishu",
    "企业微信": "WXWork",
}

_BARE_EXE = re.compile(r"^[A-Za-z0-9_\-\.]{1,64}\.(exe|EXE)$")


def _resolve_target(target: str) -> str | None:
    """Resolve a target to either an allowed alias, a bare .exe name, or None.

    Rejects anything containing path separators or '..' so we never feed an
    attacker-controlled path to a shell.
    """
    if not target or not target.strip():
        return None
    if any(ch in target for ch in ("/", "\\")):
        return None
    if ".." in target:
        return None
    resolved = _ALIAS_MAP.get(target.lower(), _ALIAS_MAP.get(target, target))
    if not _BARE_EXE.match(resolved):
        return None
    return resolved


class AppControlTool(Tool):
    """Launch applications via URL scheme or start command."""

    @property
    def name(self) -> str:
        return "app_control"

    @property
    def description(self) -> str:
        return ("Launch or open applications. Supports URL schemes (e.g. 'https://', 'mailto:') "
                "and bare executable names or aliases (e.g. 'notepad', 'chrome', '微信'). "
                "Paths and shell metacharacters are not accepted.")

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "URL scheme or bare app name/alias (no paths)",
                },
                "args": {
                    "type": "string",
                    "default": "",
                    "description": "Optional arguments to pass to the application",
                },
            },
            "required": ["target"],
        }

    @property
    def risk_level(self) -> str:
        return "LOW"

    async def execute(self, target: str = "", args: str = "", **kwargs) -> str:
        """Launch an application or open a URL."""
        if not target or not target.strip():
            return "Error: target is required"

        if "://" in target:
            return await self._open_url(target)

        app_name = _resolve_target(target)
        if app_name is None:
            return (f"Error: target must be a URL or an allowed app alias. "
                    f"Got: {target!r}")
        return await self._start_app(app_name, args)

    async def _open_url(self, url: str) -> str:
        """Open a URL using the default handler."""
        try:
            if sys.platform == "win32":
                os.startfile(url)
            else:
                subprocess.Popen(["open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            logger.info(f"Opened URL: {url}")
            return f"Opened: {url}"
        except Exception as e:
            logger.error(f"Failed to open URL: {e}")
            return f"Error opening URL: {e}"

    async def _start_app(self, app: str, args: str = "") -> str:
        """Start an application. Caller has validated app is a bare .exe name."""
        try:
            cmd = [app]
            if args:
                cmd.extend(args.split())
            subprocess.Popen(cmd)
            logger.info(f"Started app: {app}")
            return f"Started: {app}"
        except FileNotFoundError:
            return f"Error: App not found: {app}"
        except Exception as e:
            logger.error(f"Failed to start app: {e}")
            return f"Error starting '{app}': {e}"
