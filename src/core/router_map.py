"""Static bilingual intent→tools mapping for character-mode router."""

from __future__ import annotations

# Each rule: (frozenset of zh/en keywords, tool names to unlock)
_ROUTER_RULES: list[tuple[frozenset[str], tuple[str, ...]]] = [
    (frozenset({"读", "看", "文件", "内容", "read", "file", "open"}),
     ("file_ops",)),
    (frozenset({"运行", "命令", "脚本", "执行", "run", "command", "script"}),
     ("run_command",)),
    (frozenset({"搜", "查资料", "网页", "新闻", "search", "web", "news"}),
     ("web_search", "web_fetch")),
    (frozenset({"图", "照片", "看看这张图", "image", "picture", "photo", "看这张图"}),
     ("image_analyze",)),
    (frozenset({"改写", "编辑", "写进去", "edit", "rewrite", "modify"}),
     ("edit",)),
    (frozenset({"打开", "启动", "应用", "app", "launch", "start"}),
     ("app_control",)),
    (frozenset({"屏幕", "点击", "按键", "截图", "screen", "click", "key", "screenshot"}),
     ("cu_screenshot", "cu_click", "cu_type", "cu_keypress")),
]

_UNLOCK_DESCRIPTIONS: dict[str, str] = {
    "file_ops": "read and look through files",
    "run_command": "run a command on this machine",
    "web_search": "search the web",
    "web_fetch": "open a web page",
    "image_analyze": "look at an image",
    "edit": "write or change words in a file",
    "app_control": "open or control applications",
    "cu_screenshot": "see the screen",
    "cu_click": "click on the screen",
    "cu_type": "type something",
    "cu_keypress": "press a key",
}


def match_intent(keywords: str) -> list[str] | None:
    """Return tool names to unlock, or None if no keyword matches."""
    text = " ".join(keywords.strip().lower().split())
    if not text:
        return None
    for rule_keywords, tools in _ROUTER_RULES:
        if any(k in text for k in rule_keywords):
            return list(tools)
    return None


def unlock_description(tools: list[str]) -> str:
    names = ", ".join(_UNLOCK_DESCRIPTIONS.get(t, t) for t in tools)
    return f"The way opens: you can now {names}."
