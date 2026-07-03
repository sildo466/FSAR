"""FSAR Computer Use - Windows UI Automation based screen control."""

from .snapshot import WindowSnapshot, ElementInfo, get_window_state
from .input_actions import click_element, type_text, press_key, hotkey, scroll_window
from .screen_capture import capture_window
from .window_manager import (
    list_windows, launch_app, kill_app, get_foreground_window,
    find_window_for_app,
)

__all__ = [
    "WindowSnapshot", "ElementInfo", "get_window_state",
    "click_element", "type_text", "press_key", "hotkey", "scroll_window",
    "capture_window",
    "list_windows", "launch_app", "kill_app", "get_foreground_window",
    "find_window_for_app",
]
