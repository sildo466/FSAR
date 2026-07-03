"""Window state snapshot: UIA tree walk + screenshot capture.

Replicates CUA's get_window_state: walks the accessibility tree, assigns
element_index to actionable elements, captures a screenshot, and returns
both the tree markdown and structured element list for LLM consumption.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
from dataclasses import dataclass, field
from typing import Optional

import uiautomation as uia

from .screen_capture import capture_window

# UIA ControlType IDs → human-readable names
_CONTROL_TYPE_NAMES = {
    50000: "Button", 50001: "Calendar", 50002: "CheckBox", 50003: "ComboBox",
    50004: "Edit", 50005: "Hyperlink", 50006: "Image", 50007: "ListItem",
    50008: "List", 50009: "Menu", 50010: "MenuBar", 50011: "MenuItem",
    50012: "ProgressBar", 50013: "RadioButton", 50014: "ScrollBar",
    50015: "Slider", 50016: "Spinner", 50017: "StatusBar", 50018: "Tab",
    50019: "TabItem", 50020: "Text", 50021: "ToolBar", 50022: "ToolTip",
    50023: "Tree", 50024: "TreeItem", 50025: "Group", 50026: "Thumb",
    50027: "DataGrid", 50028: "DataItem", 50029: "Document",
    50030: "SplitButton", 50031: "Window", 50032: "Pane", 50033: "Header",
    50034: "HeaderItem", 50035: "Table", 50036: "TitleBar",
    50037: "Separator", 50038: "SemanticZoom", 50039: "AppBar",
}

# Max limits (matching CUA defaults)
MAX_DEPTH = 25
MAX_ELEMENTS = 5000

# Element cache: maps (hwnd, element_index) → UIA control reference
# Populated by get_window_state, consumed by input_actions.click_element
_element_cache: dict[int, dict[int, object]] = {}


@dataclass
class ElementInfo:
    """One actionable element in the UIA tree."""
    element_index: int
    role: str
    label: str
    value: str
    actions: list[str]
    frame: tuple[int, int, int, int]  # (left, top, width, height) in screen coords
    center: tuple[int, int]           # screen-coordinate center
    depth: int
    parent_index: Optional[int]
    enabled: bool
    offscreen: bool
    # The actual UIA control reference (not serialized for LLM)
    _control: object = field(repr=False, default=None)


@dataclass
class WindowSnapshot:
    """Complete window state: element tree + screenshot."""
    pid: int
    hwnd: int
    window_title: str
    elements: list[ElementInfo]           # only actionable elements (with element_index)
    tree_markdown: str                     # formatted tree for LLM
    screenshot_png: bytes                  # PNG screenshot bytes
    screenshot_width: int
    screenshot_height: int

    def to_llm_text(self) -> str:
        """Format for LLM consumption."""
        lines = [f"Window: {self.window_title} (pid={self.pid}, hwnd={self.hwnd})"]
        lines.append(f"Elements: {len(self.elements)}")
        lines.append("")
        lines.append(self.tree_markdown)
        return "\n".join(lines)


def _detect_actions(ctrl) -> list[str]:
    """Detect which actions a UIA control supports (matching CUA's detect_cached_actions)."""
    actions = []
    try:
        if ctrl.GetInvokePattern():
            actions.append("invoke")
    except Exception:
        pass
    try:
        if ctrl.GetTogglePattern():
            actions.append("toggle")
    except Exception:
        pass
    try:
        if ctrl.GetSelectionItemPattern():
            actions.append("select")
    except Exception:
        pass
    try:
        if ctrl.GetExpandCollapsePattern():
            actions.append("expand")
    except Exception:
        pass
    try:
        if ctrl.GetValuePattern():
            actions.append("set_value")
    except Exception:
        pass
    try:
        if ctrl.GetRangeValuePattern():
            actions.append("set_range")
    except Exception:
        pass
    try:
        if ctrl.GetTextPattern():
            actions.append("text")
    except Exception:
        pass
    try:
        if ctrl.GetScrollItemPattern():
            actions.append("scroll")
    except Exception:
        pass
    return actions


def _get_role_name(ctrl) -> str:
    """Get human-readable control type name."""
    try:
        ct = ctrl.ControlTypeName
        # uiautomation returns string like "ButtonControl", strip "Control" suffix
        if ct.endswith("Control"):
            ct = ct[:-7]
        return ct
    except Exception:
        return "Unknown"


def _get_rect(ctrl) -> Optional[tuple[int, int, int, int]]:
    """Get bounding rectangle as (left, top, width, height)."""
    try:
        rect = ctrl.BoundingRectangle
        if rect is None:
            return None
        # BoundingRectangle returns (left, top, right, bottom)
        return (rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)
    except Exception:
        return None


def _walk_tree(ctrl, depth: int, parent_idx: Optional[int],
               counter: list[int], elements: list[ElementInfo],
               tree_lines: list[str], max_depth: int, max_elements: int) -> None:
    """Recursively walk the UIA tree, assigning element_index to actionable nodes."""
    if depth > max_depth or len(elements) >= max_elements:
        return

    try:
        name = ctrl.Name or ""
        value = ""
        try:
            vp = ctrl.GetValuePattern()
            if vp:
                value = vp.Value or ""
        except Exception:
            pass

        is_enabled = True
        is_offscreen = False
        try:
            is_enabled = ctrl.IsEnabled
        except Exception:
            pass
        try:
            is_offscreen = ctrl.IsOffscreen
        except Exception:
            pass

        actions = _detect_actions(ctrl)
        role = _get_role_name(ctrl)
        rect = _get_rect(ctrl)

        # Determine if this element gets an index (matching CUA: has actions + enabled + not offscreen)
        my_index = None
        if actions and is_enabled and not is_offscreen and len(elements) < max_elements:
            my_index = counter[0]
            counter[0] += 1
            center = (rect[0] + rect[2] // 2, rect[1] + rect[3] // 2) if rect else (0, 0)
            elements.append(ElementInfo(
                element_index=my_index,
                role=role,
                label=name,
                value=value,
                actions=actions,
                frame=rect or (0, 0, 0, 0),
                center=center,
                depth=depth,
                parent_index=parent_idx,
                enabled=is_enabled,
                offscreen=is_offscreen,
                _control=ctrl,
            ))

        # Build markdown line (matching CUA's format_node_line)
        indent = "  " * depth
        if my_index is not None:
            action_str = ",".join(actions)
            display = name or value or ""
            if display:
                display = f'"{display}"'
            line = f"{indent}- [{my_index}] {role} {display} [actions=[{action_str}]]"
        else:
            # Non-actionable but still visible in tree
            display = name or value or ""
            if display:
                display = f'"{display}"'
            line = f"{indent}- {role} {display}"

        tree_lines.append(line)

        # Walk children
        try:
            children = ctrl.GetChildren()
            for child in children:
                _walk_tree(child, depth + 1, my_index, counter, elements,
                           tree_lines, max_depth, max_elements)
        except Exception:
            pass

    except Exception:
        pass


def get_window_state(pid: int, hwnd: int,
                     max_depth: int = MAX_DEPTH,
                     max_elements: int = MAX_ELEMENTS) -> WindowSnapshot:
    """Get complete window state: UIA tree + screenshot.

    This is the main entry point, equivalent to CUA's get_window_state.
    Returns a WindowSnapshot with element_index-able elements and markdown tree.
    """
    # Ensure COM is initialized (needed when called from worker threads)
    try:
        ctypes.windll.ole32.CoInitializeEx(None, 0x2)  # COINIT_MULTITHREADED
    except Exception:
        pass

    # Get window title
    try:
        title = ctypes.create_unicode_buffer(512)
        ctypes.windll.user32.GetWindowTextW(hwnd, title, 512)
        window_title = title.value
    except Exception:
        window_title = ""

    # Walk UIA tree
    try:
        ctrl = uia.ControlFromHandle(hwnd)
        if ctrl is None:
            raise ValueError(f"Cannot get UIA control for hwnd={hwnd}")
    except Exception as e:
        # Return empty snapshot if UIA fails
        screenshot = capture_window(hwnd)
        return WindowSnapshot(
            pid=pid, hwnd=hwnd, window_title=window_title,
            elements=[], tree_markdown=f"(UIA tree unavailable: {e})",
            screenshot_png=screenshot,
            screenshot_width=0, screenshot_height=0,
        )

    counter = [0]  # mutable counter for recursion
    elements: list[ElementInfo] = []
    tree_lines: list[str] = []

    _walk_tree(ctrl, depth=0, parent_idx=None, counter=counter,
               elements=elements, tree_lines=tree_lines,
               max_depth=max_depth, max_elements=max_elements)

    # Capture screenshot
    screenshot = capture_window(hwnd)

    # Get screenshot dimensions
    import io
    from PIL import Image
    img = Image.open(io.BytesIO(screenshot))
    sw, sh = img.size

    # Populate element cache for this hwnd
    _element_cache[hwnd] = {e.element_index: e._control for e in elements}

    return WindowSnapshot(
        pid=pid, hwnd=hwnd, window_title=window_title,
        elements=elements, tree_markdown="\n".join(tree_lines),
        screenshot_png=screenshot,
        screenshot_width=sw, screenshot_height=sh,
    )
