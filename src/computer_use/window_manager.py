"""Window management: list windows, launch apps, kill processes."""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import subprocess
import time
from dataclasses import dataclass
from typing import Optional

# Known app window signatures for reliable post-launch window finding.
# Matches CUA's approach of resolving apps by class name and title.
_KNOWN_APPS: dict[str, dict] = {
    "微信": {"class_prefix": "Chrome_WidgetWin", "title_contains": "微信"},
    "wechat": {"class_prefix": "Chrome_WidgetWin", "title_contains": "微信"},
    "qq": {"class_prefix": "TXGuiFoundation", "title_contains": "QQ"},
    "记事本": {"class_prefix": "Notepad", "title_contains": "记事本"},
    "notepad": {"class_prefix": "Notepad", "title_contains": "Notepad"},
    "计算器": {"class_prefix": "ApplicationFrameWindow", "title_contains": "计算器"},
    "calc": {"class_prefix": "ApplicationFrameWindow", "title_contains": "Calculator"},
    "edge": {"class_prefix": "Chrome_WidgetWin", "title_contains": None},
    "chrome": {"class_prefix": "Chrome_WidgetWin", "title_contains": None},
    "vscode": {"class_prefix": "Chrome_WidgetWin", "title_contains": "Visual Studio Code"},
}


@dataclass
class WindowInfo:
    """Basic window information."""
    hwnd: int
    pid: int
    title: str
    class_name: str
    is_visible: bool
    rect: tuple[int, int, int, int]  # left, top, right, bottom


def _enum_windows() -> list[WindowInfo]:
    """Enumerate all top-level windows."""
    user32 = ctypes.windll.user32
    windows = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    def callback(hwnd, lparam):
        if not user32.IsWindowVisible(hwnd):
            return True

        # Get title
        title_buf = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, title_buf, 512)
        title = title_buf.value

        # Get class name
        class_buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, class_buf, 256)
        class_name = class_buf.value

        # Get PID
        pid = ctypes.wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

        # Get rect
        rect = ctypes.wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))

        # Skip windows with no title and not a known class
        if title or class_name in ("Shell_TrayWnd", "Progman"):
            windows.append(WindowInfo(
                hwnd=hwnd,
                pid=pid.value,
                title=title,
                class_name=class_name,
                is_visible=True,
                rect=(rect.left, rect.top, rect.right, rect.bottom),
            ))
        return True

    user32.EnumWindows(callback, 0)
    return windows


def list_windows(pid: Optional[int] = None) -> list[WindowInfo]:
    """List all visible top-level windows, optionally filtered by PID."""
    windows = _enum_windows()
    if pid is not None:
        windows = [w for w in windows if w.pid == pid]
    return windows


def get_foreground_window() -> Optional[WindowInfo]:
    """Get the currently focused foreground window."""
    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None

    title_buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, title_buf, 512)

    class_buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, class_buf, 256)

    pid = ctypes.wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

    rect = ctypes.wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))

    return WindowInfo(
        hwnd=hwnd,
        pid=pid.value,
        title=title_buf.value,
        class_name=class_buf.value,
        is_visible=bool(user32.IsWindowVisible(hwnd)),
        rect=(rect.left, rect.top, rect.right, rect.bottom),
    )


def find_window_for_app(app_name: str, pid: int = 0,
                        timeout: float = 3.0) -> Optional[WindowInfo]:
    """Find a window for a launched app by name, class, and/or PID.

    Tries multiple strategies (matching CUA's post-launch window resolution):
    1. Look up app in _KNOWN_APPS registry → match by class prefix + title
    2. Search by PID (from the launched process)
    3. Fall back to foreground window if it matches the app

    Args:
        app_name: The app name as passed to launch_app (e.g. "微信")
        pid: PID of the launched process (if known)
        timeout: Max seconds to wait for the window to appear
    """
    from src.utils.logger import logger as log

    app_lower = app_name.lower().strip()
    known = None
    for key, info in _KNOWN_APPS.items():
        if key in app_lower or app_lower in key:
            known = info
            break

    deadline = time.time() + timeout

    while time.time() < deadline:
        all_windows = _enum_windows()

        # Strategy 1: Match by known class prefix + title
        if known:
            for w in all_windows:
                if not w.is_visible:
                    continue
                cls_match = (not known["class_prefix"] or
                             w.class_name.startswith(known["class_prefix"]))
                title_match = (not known.get("title_contains") or
                               known["title_contains"] in w.title)
                if cls_match and title_match:
                    log.info(f"Found window by class+title: {w.title} ({w.class_name})")
                    return w

        # Strategy 2: Match by PID
        if pid:
            for w in all_windows:
                if w.pid == pid and w.is_visible and w.title:
                    log.info(f"Found window by PID {pid}: {w.title}")
                    return w

        # Strategy 3: Check if foreground window matches
        fg = get_foreground_window()
        if fg and fg.is_visible and fg.title:
            if known:
                cls_match = (not known["class_prefix"] or
                             fg.class_name.startswith(known["class_prefix"]))
                title_match = (not known.get("title_contains") or
                               known["title_contains"] in fg.title)
                if cls_match or title_match:
                    log.info(f"Found window via foreground: {fg.title}")
                    return fg
            elif pid and fg.pid == pid:
                log.info(f"Found window via foreground PID match: {fg.title}")
                return fg

        time.sleep(0.3)

    return None


def launch_app(name: Optional[str] = None, path: Optional[str] = None,
               args: Optional[list[str]] = None,
               start_minimized: bool = False) -> tuple[int, str]:
    """Launch an application. Returns (pid, name).

    Tries multiple methods:
    1. Direct path execution
    2. ShellExecuteEx with name
    3. Start Menu / shell:AppsFolder search
    """
    if path:
        cmd = [path] + (args or [])
        proc = subprocess.Popen(cmd)
        return proc.pid, path.split("\\")[-1]

    if name:
        import win32api

        # Try common app paths FIRST (before ShellExecuteEx which fails on unknown names)
        _COMMON_APPS = {
            "微信": r"C:\Program Files\Tencent\WeChat\WeChat.exe",
            "wechat": r"C:\Program Files\Tencent\WeChat\WeChat.exe",
            "weixin": r"C:\Program Files\Tencent\WeChat\WeChat.exe",
            "qq": r"C:\Program Files\Tencent\QQ\Bin\QQ.exe",
            "记事本": "notepad.exe",
            "notepad": "notepad.exe",
            "计算器": "calc.exe",
            "calc": "calc.exe",
            "浏览器": "msedge.exe",
            "edge": "msedge.exe",
            "chrome": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            "explorer": "explorer.exe",
            "资源管理器": "explorer.exe",
            "任务管理器": "taskmgr.exe",
            "cmd": "cmd.exe",
            "终端": "wt.exe",
            "powershell": "powershell.exe",
        }

        app_lower = name.lower().strip()
        for key, exe_path in _COMMON_APPS.items():
            if key in app_lower or app_lower in key:
                try:
                    proc = subprocess.Popen([exe_path] + (args or []))
                    return proc.pid, name
                except Exception:
                    continue

        # Try ShellExecuteEx for unknown names
        try:
            proc_info = win32api.ShellExecuteEx(
                0, "open", name,
                " ".join(args) if args else None,
                None,
                0x00000007 if start_minimized else 0x00000001,
            )
            pid = proc_info.get("hProcess", 0)
            if pid:
                kernel32 = ctypes.windll.kernel32
                pid_val = kernel32.GetProcessId(pid)
                kernel32.CloseHandle(pid)
                if pid_val:
                    return pid_val, name
        except Exception:
            pass

        # Try shell:AppsFolder (UWP/Store apps)
        try:
            import win32com.client
            shell = win32com.client.Dispatch("Shell.Application")
            folder = shell.NameSpace("shell:AppsFolder")
            for item in folder.Items():
                item_name = item.Name.lower() if item.Name else ""
                if name.lower() in item_name or item_name in name.lower():
                    try:
                        item.InvokeVerb()
                        return 0, name
                    except Exception:
                        continue
        except Exception:
            pass

        # Last resort: subprocess with shell=True
        try:
            proc = subprocess.Popen(name, shell=True)
            return proc.pid, name
        except Exception:
            pass

    raise ValueError(f"Cannot launch app: {name}")


def kill_app(pid: int) -> bool:
    """Force-terminate a process by PID."""
    try:
        import win32api
        import win32con
        handle = win32api.OpenProcess(win32con.PROCESS_TERMINATE, False, pid)
        win32api.TerminateProcess(handle, 0)
        win32api.CloseHandle(handle)
        return True
    except Exception:
        try:
            subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                           capture_output=True, timeout=5)
            return True
        except Exception:
            return False
