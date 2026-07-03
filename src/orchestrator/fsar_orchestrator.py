"""FSAR Orchestrator — per-window screenshot + grid coordinates + SendInput.

Modeled after CUA's approach:
1. Capture target window at native resolution (like CUA's capture.rs)
2. Add grid overlay on ORIGINAL resolution
3. Resize for LLM, tell LLM the actual window size
4. LLM reads grid coordinates in window space
5. Convert: coord / ratio + window_origin → screen pixel → SendInput click
"""

from __future__ import annotations

import asyncio
import base64
import ctypes
import ctypes.wintypes
import io
import json
import time
from datetime import datetime
from typing import Any, Optional

from PIL import Image

from src.computer_use import launch_app, kill_app, find_window_for_app
from src.computer_use.snapshot import get_window_state, _element_cache
from src.computer_use.screen_capture import resize_if_needed, capture_window, add_grid_overlay
from src.computer_use.window_manager import list_windows, get_foreground_window
from src.utils.logger import logger as log
from src.utils.config import get_config
from src.utils.llm_factory import cached_chat_completion


AGENT_SYSTEM_PROMPT = """You are FSAR, a computer-use AI agent. You see a screenshot of the target application window.

## Coordinate System

The screenshot has a gray grid overlay. Numbers along the TOP edge are X pixel coordinates. Numbers along the LEFT edge are Y pixel coordinates.

To click on a target:
1. Find the target in the screenshot
2. Look straight UP from the target's center to find the X coordinate
3. Look straight LEFT from the target's center to find the Y coordinate
4. If between grid lines, estimate the value

The origin (0,0) is at the top-left corner of the WINDOW (not the screen).

## Rules

1. The screenshot is your ONLY source of truth.
2. Click coordinates must point to the CENTER of the target.
3. If the target app is already on screen, interact with it directly.
4. Type Chinese characters directly.
5. After each action, observe the next screenshot. If unchanged, your action failed.
6. If the same action fails 2 times, change strategy.
7. When done, call "done" with a summary.
"""


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "click",
            "description": "Click at a position in the window using grid coordinates.",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "X pixel coordinate (read from top edge grid)."},
                    "y": {"type": "integer", "description": "Y pixel coordinate (read from left edge grid)."},
                    "button": {"type": "string", "enum": ["left", "right"], "default": "left"},
                },
                "required": ["x", "y"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "type_text",
            "description": "Type text into the focused input field.",
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "press_key",
            "description": "Press a single key.",
            "parameters": {
                "type": "object",
                "properties": {"key": {"type": "string"}},
                "required": ["key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "hotkey",
            "description": "Press a key combination.",
            "parameters": {
                "type": "object",
                "properties": {"keys": {"type": "array", "items": {"type": "string"}}},
                "required": ["keys"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "launch_app",
            "description": "Launch an application.",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scroll",
            "description": "Scroll the window.",
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {"type": "string", "enum": ["up", "down", "left", "right"]},
                    "amount": {"type": "integer", "default": 3},
                },
                "required": ["direction"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "think",
            "description": "Reason about the situation.",
            "parameters": {
                "type": "object",
                "properties": {"thought": {"type": "string"}},
                "required": ["thought"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "done",
            "description": "Task complete.",
            "parameters": {
                "type": "object",
                "properties": {"summary": {"type": "string"}},
                "required": ["summary"],
            },
        },
    },
]


class FSAROrchestrator:

    def __init__(self, llm_client, model: str,
                 task_reflector=None, session_id: str = ""):
        self._llm = llm_client
        self._model = model
        self._max_steps = 9999
        self._consecutive_errors = 0
        self._resize_max = 1568
        self._coord_ratio = 1.0
        self._window_origin = (0, 0)
        self._task_reflector = task_reflector
        self._session_id = session_id

    async def run(self, task: str, pid: int = 0, hwnd: int = 0,
                  task_id: str = "") -> str:
        log.info(f"Computer Use task: {task}")
        history: list[dict[str, Any]] = []
        target_hwnd = hwnd
        target_pid = pid
        if not task_id:
            task_id = f"cu_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"

        for step in range(self._max_steps):
            user32 = ctypes.windll.user32

            # 0. Ensure valid target window
            if not target_hwnd or not user32.IsWindow(target_hwnd) or not user32.IsWindowVisible(target_hwnd):
                if target_pid:
                    for w in list_windows(target_pid):
                        if w.is_visible and w.title:
                            target_hwnd, target_pid = w.hwnd, w.pid
                            log.info(f"Re-found: {w.title} (hwnd={w.hwnd})")
                            break
                if not target_hwnd or not user32.IsWindow(target_hwnd):
                    return await self._finalize(task, task_id, history, "failure",
                                                 "No target window")

            # Get window position (for coordinate conversion)
            rect = ctypes.wintypes.RECT()
            user32.GetWindowRect(target_hwnd, ctypes.byref(rect))
            self._window_origin = (rect.left, rect.top)
            win_w = rect.right - rect.left
            win_h = rect.bottom - rect.top

            # 1. Capture target window at native resolution
            try:
                png_bytes = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: capture_window(target_hwnd)
                )
            except Exception as e:
                log.warning(f"Capture failed: {e}")
                fg = get_foreground_window()
                if fg:
                    target_hwnd, target_pid = fg.hwnd, fg.pid
                    continue
                return await self._finalize(task, task_id, history, "failure",
                                             "Cannot capture window")

            if not png_bytes:
                fg = get_foreground_window()
                if fg:
                    target_hwnd, target_pid = fg.hwnd, fg.pid
                    continue
                return await self._finalize(task, task_id, history, "failure",
                                             "Empty screenshot")

            # Grid on ORIGINAL resolution, then resize
            png_bytes = add_grid_overlay(png_bytes, step_px=50)
            png_bytes, self._coord_ratio = resize_if_needed(png_bytes, self._resize_max)
            png_b64 = base64.b64encode(png_bytes).decode("ascii")

            # Get actual image size
            img = Image.open(io.BytesIO(png_bytes))
            img_w, img_h = img.size

            # 2. Get UIA element tree
            element_text = ""
            snapshot = None
            try:
                snapshot = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: get_window_state(target_pid, target_hwnd)
                )
                if snapshot.elements:
                    element_text = "\n".join(snapshot.tree_markdown.split("\n")[:50])
                else:
                    element_text = "No actionable UI elements. Use coordinate clicks."
            except Exception:
                element_text = "Cannot read UI elements. Use coordinate clicks."

            # 3. Build message — tell LLM actual window dimensions
            window_title = snapshot.window_title if snapshot else "Unknown"
            user_content = [
                {"type": "text", "text": (
                    f"Task: {task}\n\n"
                    f"Window: {window_title}\n"
                    f"Window size: {win_w}x{win_h} pixels\n"
                    f"Screenshot size: {img_w}x{img_h} pixels\n\n"
                    f"Grid: gray lines every 50px with coordinate labels.\n"
                    f"Read X from top edge, Y from left edge.\n"
                )},
                {"type": "image_url", "image_url": {
                    "url": f"data:image/png;base64,{png_b64}",
                    "detail": "high",
                }},
            ]

            if history:
                user_content.insert(0, {
                    "type": "text",
                    "text": f"History:\n{json.dumps(history, ensure_ascii=False, indent=1)}"
                })

            if self._consecutive_errors >= 2:
                user_content.insert(0, {
                    "type": "text",
                    "text": f"WARNING: Last {self._consecutive_errors} actions failed. Change strategy."
                })

            messages = [
                {"role": "system", "content": AGENT_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ]

            # 4. Ask LLM
            tool_call = await self._ask_llm(messages)
            if tool_call is None:
                self._consecutive_errors += 1
                history.append({"step": step + 1, "action": "invalid", "error": "no tool call"})
                continue

            action_name = tool_call["name"]
            params = tool_call["args"]

            reasoning = tool_call.get("reasoning", "")
            if reasoning:
                print(f"\n  [Step {step + 1}] LLM: {reasoning[:300]}")
                log.info(f"Step {step + 1} LLM: {reasoning[:300]}")
            print(f"  [Step {step + 1}] → {action_name}: {json.dumps(params, ensure_ascii=False)}")
            log.info(f"Step {step + 1}: {action_name} {json.dumps(params, ensure_ascii=False)}")

            if action_name == "done":
                summary = params.get("summary", "Task completed")
                history.append({"step": step + 1, "action": "done", "summary": summary})
                return await self._finalize(task, task_id, history, "success", summary)

            if action_name == "think":
                print(f"  [Think] {params.get('thought', '')}")
                history.append({"step": step + 1, "action": "think", "thought": params.get("thought", "")})
                continue

            # 5. Execute
            try:
                await asyncio.wait_for(
                    self._execute_action(target_hwnd, action_name, params),
                    timeout=30
                )
                self._consecutive_errors = 0
                result = {"step": step + 1, "action": action_name, "params": params, "result": "success"}

                if action_name == "click":
                    await asyncio.sleep(0.5)

                # Handle window recreation (Qt apps)
                if not user32.IsWindow(target_hwnd) or not user32.IsWindowVisible(target_hwnd):
                    for w in list_windows(target_pid):
                        if w.is_visible and w.title:
                            old = target_hwnd
                            target_hwnd = w.hwnd
                            result["window_recreated"] = f"{old} → {w.hwnd}"
                            log.info(f"Window recreated: {w.title}")
                            break

                if action_name == "launch_app":
                    app_name = params.get("name", "")
                    launched_pid = params.get("_launched_pid", 0)
                    await asyncio.sleep(1.0)
                    target = find_window_for_app(app_name, pid=launched_pid, timeout=3.0)
                    if target:
                        target_hwnd, target_pid = target.hwnd, target.pid
                        result["found"] = f"{target.title} (hwnd={target.hwnd})"

                history.append(result)

            except asyncio.TimeoutError:
                self._consecutive_errors += 1
                history.append({"step": step + 1, "action": action_name, "error": "timeout"})
            except Exception as e:
                log.error(f"Action failed: {e}")
                self._consecutive_errors += 1
                history.append({"step": step + 1, "action": action_name, "error": str(e)})

            await asyncio.sleep(0.3)

        return await self._finalize(task, task_id, history, "timeout",
                                     f"Reached max steps ({self._max_steps})")

    async def _finalize(self, task: str, task_id: str, history: list[dict],
                        outcome: str, summary: str) -> str:
        """Hook for per-task reflection before returning."""
        if self._task_reflector is not None:
            try:
                self._task_reflector.reflect(
                    task_id=task_id,
                    session_id=self._session_id,
                    task=task,
                    outcome=outcome,
                    history=history,
                )
            except Exception as e:
                log.warning(f"Task reflection failed (non-blocking): {e}")
        return summary

    async def _ask_llm(self, messages: list) -> Optional[dict]:
        loop = asyncio.get_event_loop()

        def _call():
            return cached_chat_completion(
                self._llm,
                model=self._model,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                max_tokens=4096,
                temperature=0.1,
            )

        resp = await loop.run_in_executor(None, _call)
        choice = resp.choices[0]

        if choice.message.tool_calls:
            tc = choice.message.tool_calls[0]
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {}
            return {"name": tc.function.name, "args": args, "reasoning": choice.message.content or ""}

        text = (choice.message.content or "").strip()
        if text:
            try:
                obj = json.loads(text)
                if "action" in obj:
                    return {"name": obj.pop("action"), "args": obj, "reasoning": text[:200]}
            except json.JSONDecodeError:
                pass
        return None

    async def _execute_action(self, target_hwnd: int, action_name: str, params: dict) -> None:
        loop = asyncio.get_event_loop()

        if action_name == "click":
            x = params.get("x", 0)
            y = params.get("y", 0)
            button = params.get("button", "left")
            try:
                x, y = int(x), int(y)
            except (TypeError, ValueError):
                x, y = 0, 0

            # Convert window-space coords to screen coords (like CUA's bitmap_to_screen)
            # LLM coordinates are in resized image space → multiply by ratio to get window bitmap space
            # Then add window origin to get screen coordinates
            x = int(x * self._coord_ratio)
            y = int(y * self._coord_ratio)
            screen_x = self._window_origin[0] + x
            screen_y = self._window_origin[1] + y

            log.info(f"Window coord ({params.get('x')},{params.get('y')}) "
                     f"× ratio {self._coord_ratio:.3f} = ({x},{y}) "
                     f"+ origin {self._window_origin} = screen ({screen_x},{screen_y})")

            await loop.run_in_executor(None, lambda: self._send_click(screen_x, screen_y, button))

        elif action_name == "type_text":
            text = params.get("text", "")
            await loop.run_in_executor(None, lambda: self._send_type(text))

        elif action_name == "press_key":
            key = params.get("key", "")
            await loop.run_in_executor(None, lambda: self._send_key(key))

        elif action_name == "hotkey":
            keys = params.get("keys", [])
            await loop.run_in_executor(None, lambda: self._send_hotkey(keys))

        elif action_name == "launch_app":
            name = params.get("name", "")
            result = await loop.run_in_executor(None, lambda: launch_app(name=name))
            if result and isinstance(result, tuple):
                params["_launched_pid"] = result[0]

        elif action_name == "scroll":
            direction = params.get("direction", "down")
            amount = params.get("amount", 3)
            await loop.run_in_executor(None, lambda: self._send_scroll(direction, amount))

    # --- SendInput helpers (using ctypes.WinDLL to avoid argtype conflicts) ---

    def _make_sendinput(self):
        """Create SendInput structures and function reference."""
        u32 = ctypes.WinDLL('user32', use_last_error=True)

        class MOUSEINPUT(ctypes.Structure):
            _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long),
                        ("mouseData", ctypes.wintypes.DWORD), ("dwFlags", ctypes.wintypes.DWORD),
                        ("time", ctypes.wintypes.DWORD), ("dwExtraInfo", ctypes.c_void_p)]
        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [("wVk", ctypes.wintypes.WORD), ("wScan", ctypes.wintypes.WORD),
                        ("dwFlags", ctypes.wintypes.DWORD), ("time", ctypes.wintypes.DWORD),
                        ("dwExtraInfo", ctypes.c_void_p)]
        class INPUT_UNION(ctypes.Union):
            _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]
        class INPUT(ctypes.Structure):
            _fields_ = [("type", ctypes.wintypes.DWORD), ("union", INPUT_UNION)]

        return u32, INPUT, MOUSEINPUT, KEYBDINPUT

    def _send_click(self, x: int, y: int, button: str = "left"):
        u32, INPUT, MOUSEINPUT, _ = self._make_sendinput()
        MOUSEEVENTF_LEFTDOWN = 0x0002
        MOUSEEVENTF_LEFTUP = 0x0004
        MOUSEEVENTF_RIGHTDOWN = 0x0008
        MOUSEEVENTF_RIGHTUP = 0x0010

        u32.SetCursorPos(x, y)
        time.sleep(0.05)

        down = MOUSEEVENTF_LEFTDOWN if button == "left" else MOUSEEVENTF_RIGHTDOWN
        up = MOUSEEVENTF_LEFTUP if button == "left" else MOUSEEVENTF_RIGHTUP

        arr = (INPUT * 2)()
        arr[0].type = 0  # INPUT_MOUSE
        arr[0].union.mi.dwFlags = down
        arr[1].type = 0
        arr[1].union.mi.dwFlags = up
        u32.SendInput(2, ctypes.byref(arr), ctypes.sizeof(INPUT))

    def _send_type(self, text: str):
        import subprocess
        escaped = text.replace("'", "''")
        subprocess.run(["powershell", "-command", f"Set-Clipboard -Value '{escaped}'"],
                       capture_output=True, timeout=5)
        time.sleep(0.1)
        self._send_hotkey(["ctrl", "v"])

    def _send_key(self, key: str):
        u32, INPUT, _, KEYBDINPUT = self._make_sendinput()
        KEYEVENTF_KEYUP = 0x0002

        VK_MAP = {
            "return": 0x0D, "enter": 0x0D, "tab": 0x09, "escape": 0x1B,
            "space": 0x20, "backspace": 0x08, "delete": 0x2E,
            "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
        }
        vk = VK_MAP.get(key.lower(), 0)
        if not vk and len(key) == 1:
            vk = ord(key.upper())
        if not vk:
            return

        arr = (INPUT * 2)()
        arr[0].type = 1  # INPUT_KEYBOARD
        arr[0].union.ki.wVk = vk
        arr[1].type = 1
        arr[1].union.ki.wVk = vk
        arr[1].union.ki.dwFlags = KEYEVENTF_KEYUP
        u32.SendInput(2, ctypes.byref(arr), ctypes.sizeof(INPUT))

    def _send_hotkey(self, keys: list):
        u32, INPUT, _, _ = self._make_sendinput()
        KEYEVENTF_KEYUP = 0x0002

        VK_MAP = {"ctrl": 0x11, "shift": 0x10, "alt": 0x12, "win": 0x5B,
                  "a": 0x41, "c": 0x43, "v": 0x56, "x": 0x58, "z": 0x5A, "s": 0x53}

        # Press all keys
        arr = (INPUT * len(keys))()
        for i, k in enumerate(keys):
            vk = VK_MAP.get(k.lower(), 0)
            if vk:
                arr[i].type = 1
                arr[i].union.ki.wVk = vk
        u32.SendInput(len(keys), ctypes.byref(arr), ctypes.sizeof(INPUT))
        time.sleep(0.02)

        # Release all keys in reverse
        arr = (INPUT * len(keys))()
        for i, k in enumerate(reversed(keys)):
            vk = VK_MAP.get(k.lower(), 0)
            if vk:
                arr[i].type = 1
                arr[i].union.ki.wVk = vk
                arr[i].union.ki.dwFlags = KEYEVENTF_KEYUP
        u32.SendInput(len(keys), ctypes.byref(arr), ctypes.sizeof(INPUT))

    def _send_scroll(self, direction: str, amount: int):
        u32, INPUT, MOUSEINPUT, _ = self._make_sendinput()
        MOUSEEVENTF_WHEEL = 0x0800
        WHEEL_DELTA = 120

        delta = WHEEL_DELTA * amount if direction == "up" else -WHEEL_DELTA * amount

        arr = (INPUT * 1)()
        arr[0].type = 0
        arr[0].union.mi.dwFlags = MOUSEEVENTF_WHEEL
        arr[0].union.mi.mouseData = delta
        u32.SendInput(1, ctypes.byref(arr), ctypes.sizeof(INPUT))
