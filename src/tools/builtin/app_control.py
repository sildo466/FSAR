"""FSAR app_control tool — launch apps via URL scheme / start command / ShellExecute."""

from __future__ import annotations

import subprocess
import sys
from typing import Optional

from src.tools.registry import Tool
from src.utils.logger import logger


class AppControlTool(Tool):
    """Launch applications via URL scheme, start command, or ShellExecute."""

    @property
    def name(self) -> str:
        return "app_control"

    @property
    def description(self) -> str:
        return ("Launch or open applications. Supports: app names (e.g. 'notepad', 'chrome'), "
                "URL schemes (e.g. 'mailto:', 'weixin://'), file paths, and URLs. "
                "Use for opening apps, deep linking, and file association.")

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "App name, URL scheme, file path, or URL to open",
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

    async def execute(self, target: str, args: str = "", **kwargs) -> str:
        """Launch an application or open a target."""
        logger.info(f"App control: target={target}, args={args}")

        # Determine the type of target
        target_lower = target.lower()

        # 1. URL scheme (e.g., mailto:, weixin://, https://)
        if "://" in target:
            return await self._open_url(target)

        # 2. Known app aliases
        app_map = {
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

        app_name = app_map.get(target_lower, app_map.get(target, target))
        return await self._start_app(app_name, args)

    async def _open_url(self, url: str) -> str:
        """Open a URL using the default handler."""
        try:
            if sys.platform == "win32":
                # Use os.startfile on Windows
                import os
                os.startfile(url)
            else:
                subprocess.Popen(["open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            logger.info(f"Opened URL: {url}")
            return f"Opened: {url}"
        except Exception as e:
            logger.error(f"Failed to open URL: {e}")
            return f"Error opening URL: {e}"

    async def _start_app(self, app: str, args: str = "") -> str:
        """Start an application."""
        try:
            # Try subprocess.Popen first
            cmd = [app]
            if args:
                cmd.extend(args.split())

            subprocess.Popen(cmd, shell=True)
            logger.info(f"Started app: {app}")
            return f"Started: {app}"
        except FileNotFoundError:
            # Try with start command on Windows
            try:
                cmd = f"start {app}"
                if args:
                    cmd += f" {args}"
                subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                logger.info(f"Started app via 'start': {app}")
                return f"Started: {app}"
            except Exception as e2:
                logger.error(f"Failed to start app: {e2}")
                return f"Error: Could not start '{app}'. {e2}"
        except Exception as e:
            logger.error(f"Failed to start app: {e}")
            return f"Error starting '{app}': {e}"
