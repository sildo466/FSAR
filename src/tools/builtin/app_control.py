"""FSAR app_control tool — launch apps via URL scheme / start command / ShellExecute."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from typing import Optional

from src.tools.registry import Tool
from src.utils.logger import logger


WINDOWS_ALIASES: dict[str, str] = {
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
    "wechat": "WeChat",
    "微信": "WeChat",
    "qq": "QQ",
    "钉钉": "DingTalk",
    "飞书": "Feishu",
    "企业微信": "WXWork",
}

POSIX_ALIASES: dict[str, str | tuple[str, ...]] = {
    "terminal": ("open", "-a", "Terminal"),
    "gnome-terminal": "gnome-terminal",
    "konsole": "konsole",
    "files": ("open", "."),
    "nautilus": "nautilus",
    "dolphin": "dolphin",
    "firefox": "firefox",
    "chrome": ("open", "-a", "Google Chrome"),
    "chromium": "chromium",
    "vscode": "code",
    "code": "code",
}

_LINUX_GENERIC_ALIASES: dict[str, str | tuple[str, ...]] = {
    "terminal": "x-terminal-emulator",
    "files": ("xdg-open", "."),
    "chrome": "google-chrome",
}

_BARE_EXE_WIN = re.compile(r"^[A-Za-z0-9_\-\.]{1,64}\.(exe|EXE)$")
_BARE_NAME_POSIX = re.compile(r"^[A-Za-z0-9_\-\.]{1,64}$")


def _is_windows() -> bool:
    return sys.platform == "win32"


def _resolve_target(target: str) -> str | tuple[str, ...] | None:
    """Resolve a target to an allowed alias entry, bare executable name, or None.

    Rejects anything containing path separators or '..' so we never feed an
    attacker-controlled path to a shell.
    """
    if not target or not target.strip():
        return None
    if any(ch in target for ch in ("/", "\\")):
        return None
    if ".." in target:
        return None
    if _is_windows():
        alias_map = WINDOWS_ALIASES
        pattern = _BARE_EXE_WIN
    else:
        alias_map = POSIX_ALIASES
        pattern = _BARE_NAME_POSIX
        if sys.platform.startswith("linux"):
            alias_map = {**alias_map, **_LINUX_GENERIC_ALIASES}

    resolved = alias_map.get(target.lower())
    if resolved is not None:
        return resolved
    if not pattern.fullmatch(target):
        return None
    return target


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
            elif sys.platform == "darwin":
                subprocess.Popen(["open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            elif sys.platform.startswith("linux"):
                subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                return f"Error: URL open not supported on platform {sys.platform!r}"

            logger.info(f"Opened URL: {url}")
            return f"Opened: {url}"
        except Exception as e:
            logger.error(f"Failed to open URL: {e}")
            return f"Error opening URL: {e}"

    async def _start_app(self, app: str | tuple[str, ...], args: str = "") -> str:
        """Start an application. Caller has validated the target."""
        try:
            cmd = list(app) if isinstance(app, tuple) else [app]
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
