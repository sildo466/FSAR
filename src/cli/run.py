# SPDX-License-Identifier: MIT
"""`fsar run` — one-shot headless agent turn.

Meant for scripting FSAR and for letting a remote machine's FSAR act as a
room member. Drives the same agent loop the GUI uses, via the engine's
no-op websocket shim, so tools / memory / risk gating behave identically.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys


def _spawn_headless_turn(
    task: str,
    *,
    conversation_id: str | None = None,
    character_card_id: int | None = None,
) -> tuple[str, str, str]:
    """Run one turn on a fresh event loop. Separated so tests can stub it.

    Returns (conversation_id, conclusion, outcome) — outcome drives the exit
    code so a script can tell a real answer from a cancelled / failed run.
    """
    from src.server.chat_engine import handle_user_agent_message_result

    return asyncio.run(
        handle_user_agent_message_result(
            conversation_id, task, character_card_id=character_card_id,
        )
    )


def run_once(
    task: str,
    *,
    conversation_id: str | None = None,
    character_card_id: int | None = None,
) -> dict[str, str]:
    conv_id, conclusion, outcome = _spawn_headless_turn(
        task,
        conversation_id=conversation_id,
        character_card_id=character_card_id,
    )
    return {
        "conversation_id": conv_id,
        "conclusion": conclusion,
        "outcome": outcome,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fsar run",
        description="Run a single agent turn without the TUI.",
    )
    parser.add_argument("task", help="the user message to send")
    parser.add_argument(
        "--conversation-id", default=None,
        help="continue an existing conversation instead of starting one",
    )
    parser.add_argument(
        "--character-id", type=int, default=None,
        help="speak as this character card (default: the default card)",
    )
    parser.add_argument(
        "--json", action="store_true", help="print one JSON object",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_once(
        args.task,
        conversation_id=args.conversation_id,
        character_card_id=args.character_id,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(result["conclusion"])
    return 0 if result["outcome"] == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
