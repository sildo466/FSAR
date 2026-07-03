"""Input actions: click, type, press_key, hotkey, scroll.

Replicates CUA's dispatch strategy:
- Click: UIA InvokePattern first → PostMessage → SendInput foreground fallback
- Type: ValuePattern.SetValue first → WM_CHAR fallback
- Key: PostMessage WM_KEYDOWN/UP
- Scroll: PostMessage WM_VSCROLL/WM_HSCROLL

For Chromium/Electron/WPF/GTK targets where PostMessage is silently dropped,
falls back to SendInput with a brief SetForegroundWindow swap.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import time
from typing import Optional

import uiautomation as uia

from src.utils.logger import logger as log

# Win32 message constants
WM_CHAR = 0x0102
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WM_MOUSEMOVE = 0x0200
WM_VSCROLL = 0x0115
WM_HSCROLL = 0x0114

MK_LBUTTON = 0x0001
MK_RBUTTON = 0x0002

SB_LINEUP = 0
SB_LINEDOWN = 1
SB_PAGEUP = 2
SB_PAGEDOWN = 3
SB_LINELEFT = 0
SB_LINERIGHT = 1
SB_PAGELEFT = 2
SB_PAGERIGHT = 3

# SendInput constants
INPUT_MOUSE = 0
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_VIRTUALDESK = 0x4000

# ctypes structures for SendInput
class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.wintypes.DWORD),
        ("dwFlags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]

class INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT)]

class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.wintypes.DWORD),
        ("union", INPUT_UNION),
    ]

# Set SendInput argtypes/restype
_user32 = ctypes.windll.user32
_user32.SendInput.argtypes = [ctypes.wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
_user32.SendInput.restype = ctypes.wintypes.UINT
_user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
_user32.SetCursorPos.restype = ctypes.wintypes.BOOL
_user32.GetCursorPos.argtypes = [ctypes.POINTER(ctypes.wintypes.POINT)]
_user32.GetCursorPos.restype = ctypes.wintypes.BOOL
_user32.GetClassNameW.argtypes = [ctypes.wintypes.HWND, ctypes.c_wchar_p, ctypes.c_int]
_user32.GetClassNameW.restype = ctypes.c_int


def _get_window_class(hwnd: int) -> str:
    """Get the window class name for a given HWND."""
    buf = ctypes.create_unicode_buffer(256)
    ctypes.windll.user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def _is_postmessage_dropped(hwnd: int) -> bool:
    """Check if PostMessage mouse clicks would be silently dropped or unreliable.

    Matches CUA's would_be_silently_dropped logic, plus Qt detection:
    - Chrome_WidgetWin_* (Chromium/Electron: WeChat, Edge, Chrome, VS Code)
    - HwndWrapper[*] (WPF)
    - gdkWindow* / gdkSurface* (GTK)
    - Qt* (Qt applications: WeChat old UI, VLC, etc.)
    """
    cls = _get_window_class(hwnd)
    if cls.startswith("Chrome_WidgetWin"):
        return True
    if cls.startswith("HwndWrapper"):
        return True
    if cls.startswith("gdkWindow") or cls.startswith("gdkSurface"):
        return True
    # Qt applications: PostMessage may not reliably deliver clicks
    if cls.startswith("Qt") or "QWindow" in cls:
        return True
    return False


def _send_input_click(hwnd: int, x: int, y: int, button: str, count: int) -> bool:
    """Foreground click via SendInput — for Chromium/WPF/GTK targets.

    Briefly brings the target window to foreground, moves the real cursor,
    injects mouse events via SendInput, then restores the previous foreground.
    Matches CUA's send_click_synthesized approach.
    """
    user32 = ctypes.windll.user32

    # Save previous foreground window and cursor position
    prev_fg = user32.GetForegroundWindow()
    prev_pos = ctypes.wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(prev_pos))

    try:
        # Bring target to foreground
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.05)

        # Move cursor to target position (screen coordinates)
        user32.SetCursorPos(x, y)
        time.sleep(0.02)

        # Determine button flags
        if button == "left":
            down_flag = MOUSEEVENTF_LEFTDOWN
            up_flag = MOUSEEVENTF_LEFTUP
        elif button == "right":
            down_flag = MOUSEEVENTF_RIGHTDOWN
            up_flag = MOUSEEVENTF_RIGHTUP
        else:
            raise ValueError(f"Unsupported button: {button}")

        # Build and send input events
        for _ in range(count):
            # Mouse down
            inputs = (INPUT * 1)()
            inputs[0].type = INPUT_MOUSE
            inputs[0].union.mi.dwFlags = down_flag
            _user32.SendInput(1, inputs, ctypes.sizeof(INPUT))
            time.sleep(0.02)

            # Mouse up
            inputs = (INPUT * 1)()
            inputs[0].type = INPUT_MOUSE
            inputs[0].union.mi.dwFlags = up_flag
            _user32.SendInput(1, inputs, ctypes.sizeof(INPUT))
            time.sleep(0.05)

        return True

    finally:
        # Restore previous foreground and cursor
        if prev_fg:
            user32.SetForegroundWindow(prev_fg)
        user32.SetCursorPos(prev_pos.x, prev_pos.y)


# Key name → VK code mapping
_VK_MAP = {
    "return": 0x0D, "enter": 0x0D, "tab": 0x09, "escape": 0x1B, "esc": 0x1B,
    "space": 0x20, "backspace": 0x08, "delete": 0x2E, "del": 0x2E,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73,
    "f5": 0x74, "f6": 0x75, "f7": 0x76, "f8": 0x77,
    "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
    "ctrl": 0x11, "control": 0x11, "shift": 0x10, "alt": 0x12,
    "win": 0x5B, "windows": 0x5B,
    "insert": 0x2D, "printscreen": 0x2C,
}

_MODIFIER_VKS = {0x11, 0x10, 0x12, 0x5B}  # ctrl, shift, alt, win


def _resolve_vk(key: str) -> int:
    """Resolve key name to VK code."""
    k = key.lower().strip()
    if k in _VK_MAP:
        return _VK_MAP[k]
    if len(k) == 1:
        return ord(k.upper())
    raise ValueError(f"Unknown key: {key}")


def _make_lparam(x: int, y: int) -> int:
    """Pack screen coordinates into LPARAM for PostMessage."""
    return (y << 16) | (x & 0xFFFF)


def click_element(hwnd: int, element_index: int = -1,
                  x: int = -1, y: int = -1,
                  button: str = "left", count: int = 1) -> bool:
    """Click an element or screen position.

    Two modes (matching CUA):
    - element_index: look up from snapshot cache, use UIA InvokePattern
    - x, y: screen coordinates, try UIA hit-test then PostMessage

    Returns True if click was performed.
    """
    if element_index >= 0:
        return _click_by_element(hwnd, element_index, button, count)
    elif x >= 0 and y >= 0:
        return _click_by_coords(hwnd, x, y, button, count)
    else:
        raise ValueError("Must provide either element_index or (x, y)")


def _click_by_element(hwnd: int, idx: int, button: str, count: int) -> bool:
    """Click using cached UIA element reference.

    Strategy:
    1. Try UIA patterns (Invoke/Toggle/Select/Expand) — works for most native controls
    2. If UIA fails or times out, get element's screen coords
    3. For Chromium/WPF/GTK targets: use SendInput (foreground)
    4. For other targets: use PostMessage (background)
    """
    from .snapshot import _element_cache
    hwnd_cache = _element_cache.get(hwnd)
    if hwnd_cache is None:
        raise ValueError(f"No cache for hwnd={hwnd}. Call get_window_state first.")
    ctrl = hwnd_cache.get(idx)
    if ctrl is None:
        raise ValueError(f"Element index {idx} not found in cache for hwnd={hwnd}. "
                         "Call get_window_state first.")

    # Try UIA patterns (matching CUA's cascade)
    if button == "left":
        import concurrent.futures
        _pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)

        def _try_invoke():
            try:
                p = ctrl.GetInvokePattern()
                if p:
                    for _ in range(count):
                        p.Invoke()
                        time.sleep(0.05)
                    return True
            except Exception:
                pass
            return False

        def _try_toggle():
            try:
                p = ctrl.GetTogglePattern()
                if p:
                    p.Toggle()
                    return True
            except Exception:
                pass
            return False

        def _try_select():
            try:
                p = ctrl.GetSelectionItemPattern()
                if p:
                    p.Select()
                    return True
            except Exception:
                pass
            return False

        def _try_expand():
            try:
                p = ctrl.GetExpandCollapsePattern()
                if p:
                    p.Expand()
                    return True
            except Exception:
                pass
            return False

        # Try each pattern with 5-second timeout
        for fn in (_try_invoke, _try_toggle, _try_select, _try_expand):
            try:
                future = _pool.submit(fn)
                result = future.result(timeout=5)
                if result:
                    _pool.shutdown(wait=False)
                    return True
            except concurrent.futures.TimeoutError:
                log.warning("UIA pattern timed out, falling through to coordinate click")
                break
            except Exception:
                continue

        _pool.shutdown(wait=False)

    # Fallback: click at element center using appropriate method
    try:
        rect = ctrl.BoundingRectangle
        cx = (rect.left + rect.right) // 2
        cy = (rect.top + rect.bottom) // 2
        log.info(f"UIA fallback: element {idx} center at ({cx}, {cy}), rect=({rect.left},{rect.top},{rect.right},{rect.bottom})")

        if _is_postmessage_dropped(hwnd):
            log.info(f"SendInput target detected (class={_get_window_class(hwnd)}), using foreground click")
            return _send_input_click(hwnd, cx, cy, button, count)
        else:
            return _post_click(hwnd, cx, cy, button, count)
    except Exception as e:
        log.warning(f"Element fallback click failed: {e}")

    return False


def _click_by_coords(hwnd: int, x: int, y: int, button: str, count: int) -> bool:
    """Click at window-relative coordinates (from LLM screenshot analysis).

    The LLM outputs coordinates relative to the window screenshot.
    We need to convert them to screen coordinates for both SendInput and PostMessage.

    Conversion: screen_x = window_rect.left + x, screen_y = window_rect.top + y
    (The screenshot is captured from the window's position on screen)
    """
    user32 = ctypes.windll.user32

    # Get window rect to convert window-relative coords to screen coords
    rect = ctypes.wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    screen_x = rect.left + x
    screen_y = rect.top + y
    log.info(f"Window-relative ({x},{y}) + window origin ({rect.left},{rect.top}) -> screen ({screen_x},{screen_y})")

    if _is_postmessage_dropped(hwnd):
        return _send_input_click(hwnd, screen_x, screen_y, button, count)
    return _post_click(hwnd, screen_x, screen_y, button, count)


def _post_click(hwnd: int, x: int, y: int, button: str, count: int) -> bool:
    """Post WM_LBUTTONDOWN/UP or WM_RBUTTONDOWN/UP.

    x, y are screen coordinates. Converts to client coordinates for PostMessage.
    """
    user32 = ctypes.windll.user32

    # Convert screen coords to client coords
    point = ctypes.wintypes.POINT(x, y)
    user32.ScreenToClient(hwnd, ctypes.byref(point))
    lparam = _make_lparam(point.x, point.y)

    if button == "left":
        down, up, mk = WM_LBUTTONDOWN, WM_LBUTTONUP, MK_LBUTTON
    elif button == "right":
        down, up, mk = WM_RBUTTONDOWN, WM_RBUTTONUP, MK_RBUTTON
    else:
        raise ValueError(f"Unsupported button: {button}")

    for _ in range(count):
        user32.PostMessageW(hwnd, down, mk, lparam)
        time.sleep(0.02)
        user32.PostMessageW(hwnd, up, 0, lparam)
        time.sleep(0.05)

    return True


def type_text(hwnd: int, text: str, element_index: int = -1,
              delay_ms: int = 30) -> bool:
    """Type text into a window.

    Strategy (matching CUA):
    1. If element_index provided, try ValuePattern.SetValue on that element
    2. If no element_index, find the first element with set_value action (e.g., text editor)
    3. Fallback: PostMessage WM_CHAR character by character
    """
    from .snapshot import _element_cache

    # Try ValuePattern first (for XAML/WinUI3 targets like Notepad)
    hwnd_cache = _element_cache.get(hwnd)
    if hwnd_cache:
        ctrl = None
        if element_index >= 0:
            ctrl = hwnd_cache.get(element_index)
        else:
            # Auto-find: look for an element with set_value action (text editor)
            for idx, c in sorted(hwnd_cache.items()):
                try:
                    if c.GetValuePattern():
                        ctrl = c
                        break
                except Exception:
                    continue

        if ctrl:
            try:
                pattern = ctrl.GetValuePattern()
                if pattern:
                    pattern.SetValue(text)
                    return True
            except Exception:
                pass

    # Fallback: PostMessage WM_CHAR (handles Unicode including Chinese for Win32 apps)
    return _post_type_text(hwnd, text, delay_ms)


def _post_type_text(hwnd: int, text: str, delay_ms: int) -> bool:
    """Post WM_CHAR for each character."""
    user32 = ctypes.windll.user32
    delay = delay_ms / 1000.0

    for ch in text:
        user32.PostMessageW(hwnd, WM_CHAR, ord(ch), 0)
        time.sleep(delay)

    return True


def press_key(hwnd: int, key: str, modifiers: Optional[list[str]] = None) -> bool:
    """Press a key with optional modifiers.

    Uses PostMessage WM_KEYDOWN/WM_KEYUP for background delivery.
    """
    user32 = ctypes.windll.user32
    vk = _resolve_vk(key)

    # Press modifiers
    mod_vks = []
    if modifiers:
        for mod in modifiers:
            mvk = _resolve_vk(mod)
            mod_vks.append(mvk)
            user32.PostMessageW(hwnd, WM_KEYDOWN, mvk, 0)
            time.sleep(0.02)

    # Press key
    user32.PostMessageW(hwnd, WM_KEYDOWN, vk, 0)
    time.sleep(0.02)
    user32.PostMessageW(hwnd, WM_KEYUP, vk, 0)
    time.sleep(0.02)

    # Release modifiers (reverse order)
    for mvk in reversed(mod_vks):
        user32.PostMessageW(hwnd, WM_KEYUP, mvk, 0)
        time.sleep(0.02)

    return True


def hotkey(hwnd: int, keys: list[str]) -> bool:
    """Press a key combination (e.g., ["ctrl", "s"]).

    Convenience wrapper around press_key with modifiers.
    """
    if not keys:
        raise ValueError("keys cannot be empty")

    # Last key is the main key, rest are modifiers
    *modifiers, main_key = keys
    return press_key(hwnd, main_key, modifiers or None)


def scroll_window(hwnd: int, direction: str, by: str = "line",
                  amount: int = 3) -> bool:
    """Scroll a window.

    Posts WM_VSCROLL/WM_HSCROLL to the window (matching CUA).
    """
    user32 = ctypes.windll.user32

    if direction in ("up", "down"):
        msg = WM_VSCROLL
        if direction == "up":
            code = SB_LINEUP if by == "line" else SB_PAGEUP
        else:
            code = SB_LINEDOWN if by == "line" else SB_PAGEDOWN
    elif direction in ("left", "right"):
        msg = WM_HSCROLL
        if direction == "left":
            code = SB_LINELEFT if by == "line" else SB_PAGELEFT
        else:
            code = SB_LINERIGHT if by == "line" else SB_PAGERIGHT
    else:
        raise ValueError(f"Invalid direction: {direction}")

    for _ in range(amount):
        user32.PostMessageW(hwnd, msg, code, 0)
        time.sleep(0.02)

    return True
