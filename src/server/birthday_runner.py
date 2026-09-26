# SPDX-License-Identifier: MIT
"""Effects behind the birthday decisions: unlock the skin, write the
notifications, and have the most-used characters each write a letter.

The skin, the header notification and the "show the letter" flag are fast and
run on the connect path. The per-character letters are model calls and run in
the background, landing one at a time so the notification list fills in.
"""
from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import Any

from src.core.birthday import SKIN_ID, letter_for, letters_instruction
from src.notifications.store import NotificationStore
from src.utils.logger import logger

CHARACTER_LIMIT = 10
LETTER_CONCURRENCY = 3

_HEADER_TITLE = {
    "zh-Hans": "生日快乐",
    "zh-Hant": "生日快樂",
    "en": "Happy birthday",
    "ja": "お誕生日おめでとう",
    "de": "Alles Gute zum Geburtstag",
    "fr": "Joyeux anniversaire",
}


def skins_dir(config: Any) -> Path:
    return Path(config.get("data.skins_dir", "data/skins"))


def skin_source_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "assets" / "birthday_skin"


def unlock_skin(config: Any) -> bool:
    """Copy the birthday skin into the user's skin directory. Returns True when
    it actually copied — the folder's presence is the only record of "already
    unlocked", so deleting it re-arms the gift."""
    target = skins_dir(config) / SKIN_ID
    if target.exists():
        return False
    source = skin_source_dir()
    if not (source / "skin.json").is_file():
        logger.warning(f"birthday skin asset missing at {source}")
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target)
    return True


def letters_year(store: NotificationStore) -> int | None:
    """The newest year that already has character letters."""
    years = [
        int(row["ref"]) for row in store.list(kind="birthday")
        if (row.get("ref") or "").isdigit()
    ]
    return max(years) if years else None


def write_header_notification(store: NotificationStore, year: int,
                              locale: str) -> bool:
    title = _HEADER_TITLE.get(locale, _HEADER_TITLE["en"])
    row_id = store.add(
        kind="birthday", title=title, body=letter_for(locale), ref=str(year),
    )
    return row_id is not None


def _characters_by_use(engine: Any) -> list[Any]:
    counted: list[tuple[int, Any]] = []
    for card in engine.card_repo.list_characters():
        if getattr(card, "id", None) is None:
            continue
        try:
            sessions = engine.session_store.session_ids_for_character(card.id)
        except Exception:
            sessions = []
        counted.append((len(sessions), card))
    counted.sort(key=lambda pair: (-pair[0], pair[1].id))
    return [card for _, card in counted[:CHARACTER_LIMIT]]


async def write_character_letters(
    *, ws: Any, config: Any, engine: Any, store: NotificationStore,
    locale: str, year: int, concurrency: int = LETTER_CONCURRENCY,
) -> int:
    """One in-character call per character, inserted as each one lands."""
    characters = _characters_by_use(engine)
    if not characters:
        return 0
    client, model, provider_id = engine.client_and_model()
    if client is None:
        return 0

    from src.server.group_engine import _one_completion, strip_tool_call_markup

    instruction = letters_instruction(locale)
    gate = asyncio.Semaphore(max(1, concurrency))
    written = 0

    async def one(character: Any) -> None:
        nonlocal written
        async with gate:
            try:
                # No tools are offered here, so the prompt must not advertise
                # any — a character told it has update_emotion writes the call.
                system = await engine._build_character_prompt(
                    "", instruction, character, tools_enabled=False,
                )
                text = await asyncio.to_thread(
                    _one_completion, client, provider_id, model, instruction, system,
                )
            except Exception as e:
                logger.debug(f"birthday letter failed for {character.name}: {e}")
                return
        body = strip_tool_call_markup(text or "")
        if not body:
            return
        row_id = store.add(
            kind="birthday", title=character.name, body=body,
            ref=f"{year}:{character.id}",
            payload={"character_id": character.id},
        )
        if row_id is None:
            return
        written += 1
        try:
            await ws.send_json({"type": "notifications.changed"})
        except Exception:
            pass

    await asyncio.gather(*(one(c) for c in characters))
    return written
