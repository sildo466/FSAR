"""Verify FSAR's tool-task system prompt teaches the LLM:
  1. The right MCP install flow (English)
  2. The "user-language" reply rule (not hard-coded Chinese)
  3. No leftover Chinese in the prompt

Run:  python tests/test_mcp_prompt.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    src = (ROOT / "main.py").read_text(encoding="utf-8")

    # Anchor on the tool-task prompt header.
    marker = "You are FSAR, a personal AI companion"
    idx = src.find(marker)
    if idx < 0:
        print("FAIL: tool task system prompt not found in main.py")
        return 1

    # End at the closing ')},' that ends the content block.
    end = src.find(')},\n        ]', idx)
    if end < 0:
        print("FAIL: cannot find end of prompt")
        return 1
    prompt = src[idx:end + 4]
    print(f"[prompt-test] extracted {len(prompt)} chars of system prompt")

    must_have = [
        ("You are FSAR", "English persona header"),
        ("HOW TO ADD AN MCP SERVER", "English MCP install section header"),
        ("run_command", "Mentions run_command as the tool to use"),
        ("file_ops", "Mentions file_ops for reading config"),
        ("python -m src.mcp.cli add", "Shows the exact CLI command"),
        ("--risk", "Mentions risk level flag"),
        ("--help", "Tells LLM to only run --help"),
        ("/mcp reload", "Tells user how to activate"),
        ("NEVER DO THIS", "Has a clear 'don't do this' section"),
        ("stdin", "Warns about the hang / stdin issue"),
        ("JSON-RPC", "Explains WHY it hangs (JSON-RPC stdin)"),
        ("acts as the parent", "Mentions parent process requirement"),
        ("Reply in the user's language", "User-language reply rule (no hardcoded language)"),
    ]

    failed = []
    for needle, desc in must_have:
        if needle in prompt:
            print(f"  OK: contains '{needle}' ({desc})")
        else:
            print(f"  FAIL: missing '{needle}' ({desc})")
            failed.append(needle)

    # Negative checks:
    #   - Prompt should NOT contain any Chinese characters (hardcoded prompts are English).
    #   - Prompt should NOT say "directly run the binary to test".
    #   - Prompt should NOT hardcode a specific reply language.
    cjk_in_prompt = re.findall(r'[一-鿿]', prompt)
    if cjk_in_prompt:
        print(f"  FAIL: prompt contains {len(cjk_in_prompt)} CJK chars: {set(cjk_in_prompt)}")
        failed.append("cjk-chars")
    else:
        print("  OK: no CJK characters in prompt (all hardcoded text is English)")

    forbidden = [
        ("Reply in Chinese", "Should not hardcode a reply language"),
        ("reply in Chinese", "Lowercase variant"),
        ("回复用中文", "Old Chinese instruction, must be removed"),
        ("run_command`<binary>` to test", "Should not encourage direct execution"),  # example
    ]
    for needle, desc in forbidden:
        if needle in prompt:
            print(f"  FAIL: prompt contains forbidden phrase '{needle}' ({desc})")
            failed.append(needle)
        else:
            print(f"  OK: does not contain forbidden '{needle}'")

    # Also verify the chat-only prompt is English and has the user-language rule.
    chat_marker = "Reply in the user's language"
    chat_idx = src.find(chat_marker)
    if chat_idx >= 0:
        print(f"  OK: chat prompt also has 'Reply in the user's language' rule")
    else:
        print(f"  FAIL: chat prompt is missing 'Reply in the user's language' rule")
        failed.append("chat-language-rule")

    if failed:
        print(f"\nFAIL: {len(failed)} missing/forbidden items")
        return 1
    print(f"\nALL OK: English system prompts, user-language rule, no Chinese")
    return 0


if __name__ == "__main__":
    sys.exit(main())