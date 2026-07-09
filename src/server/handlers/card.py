# SPDX-License-Identifier: Apache-2.0
"""WS dispatcher for character + user card CRUD (spec §5.6)."""
from __future__ import annotations

import json
from typing import Any

from fastapi import WebSocket

from src.memory.cards import CardRepo, CharacterCard, UserCard


def parse_sillytavern_v2(json_text: str) -> CharacterCard:
    """Parse SillyTavern V2 JSON into a CharacterCard.

    V1 and V3 are tolerated; missing fields are filled with defaults.
    Lorebook / character_book is ignored in PL2.0.
    """
    raw = json.loads(json_text)
    data = raw.get("data", raw)
    spec = raw.get("spec", "")
    tags = list(data.get("tags", []) or [])
    if spec == "chara_card_v1" or "spec" not in raw:
        tags.append("st_v1")
    elif spec == "chara_card_v3":
        tags.append("st_v3")
    tags.append("imported")
    mes_example = data.get("mes_example", "") or ""
    dialogues: list[dict] = []
    if mes_example:
        for block in mes_example.split("\n\n"):
            lines = block.strip().split("\n")
            user = next((l[len("user:"):].strip() for l in lines if l.startswith("user:")), "")
            assistant = next((l[len("assistant:"):].strip() for l in lines if l.startswith("assistant:")), "")
            if user or assistant:
                dialogues.append({"user": user, "assistant": assistant})
    return CharacterCard(
        id=None,
        name=data.get("name", "Imported"),
        description=data.get("description", ""),
        personality=data.get("personality", "neutral"),
        scenario=data.get("scenario", ""),
        example_dialogues=dialogues,
        tags=tags,
        created_by="imported",
        created_at="",
        updated_at="",
    )


def _get_card_repo(ctx: dict[str, Any] | None) -> CardRepo:
    """Resolve the CardRepo from context, falling back to a fresh one."""
    if ctx and ctx.get("engine") is not None:
        return ctx["engine"].card_repo
    db_path = (ctx or {}).get("db_path", "data/memory.db")
    from pathlib import Path
    return CardRepo(Path(db_path))


async def dispatch(ws: WebSocket, msg: dict[str, Any], ctx: dict[str, Any] | None = None) -> bool:
    t = msg.get("type")
    if not t or not t.startswith("card."):
        return False
    repo = _get_card_repo(ctx)
    kind = msg.get("kind")  # 'character' | 'user' — only set for card-level types

    if t == "card.list":
        if kind == "character":
            cards = repo.list_characters()
        elif kind == "user":
            cards = repo.list_user_cards()
        else:
            await ws.send_json({"type": "card.error", "code": "bad_kind", "message": str(kind)})
            return True
        await ws.send_json({
            "type": "card.list_result",
            "kind": kind,
            "cards": [_card_to_dict(c) for c in cards],
        })
        return True

    if t == "card.get":
        cid = msg.get("id")
        if kind == "character":
            card = repo.get_character(cid) if cid is not None else None
        elif kind == "user":
            card = repo.get_user_card(cid) if cid is not None else None
        else:
            card = None
        if card is None:
            await ws.send_json({"type": "card.error", "code": "not_found"})
        else:
            await ws.send_json({"type": "card.got", "kind": kind, "card": _card_to_dict(card)})
        return True

    if t == "card.upsert":
        data = msg.get("card") or {}
        if kind == "character":
            card = CharacterCard(
                id=data.get("id"),
                name=data.get("name", ""),
                description=data.get("description", ""),
                personality=data.get("personality", ""),
                scenario=data.get("scenario", ""),
                system_prompt_override=data.get("system_prompt_override", ""),
                example_dialogues=data.get("example_dialogues") or [],
                tags=data.get("tags") or [],
                avatar_path=data.get("avatar_path"),
                is_default=int(bool(data.get("is_default", 0))),
                created_by=data.get("created_by", "user"),
                created_at=data.get("created_at", ""),
                updated_at=data.get("updated_at", ""),
                emotion_state=data.get("emotion_state"),
                emotion_schema=data.get("emotion_schema"),
                emotion_formulas=data.get("emotion_formulas"),
            )
            cid = repo.upsert_character(card)
        elif kind == "user":
            card = UserCard(
                id=data.get("id"),
                name=data.get("name", ""),
                description=data.get("description", ""),
                preferences=data.get("preferences") or {},
                interests=data.get("interests") or [],
                communication_style=data.get("communication_style", ""),
                avatar_path=data.get("avatar_path"),
                is_default=int(bool(data.get("is_default", 0))),
                created_by=data.get("created_by", "user"),
                created_at=data.get("created_at", ""),
                updated_at=data.get("updated_at", ""),
            )
            cid = repo.upsert_user_card(card)
        else:
            await ws.send_json({"type": "card.error", "code": "bad_kind"})
            return True
        await ws.send_json({"type": "card.upserted", "kind": kind, "id": cid})
        return True

    if t == "card.delete":
        cid = msg.get("id")
        if kind == "character":
            ok = repo.delete_character(cid)
        elif kind == "user":
            ok = repo.delete_user_card(cid)
        else:
            ok = False
        await ws.send_json({"type": "card.deleted", "kind": kind, "id": cid, "ok": ok})
        return True

    if t == "card.set_default":
        cid = msg.get("id")
        if kind == "character":
            repo.set_default_character(cid)
        elif kind == "user":
            repo.set_default_user_card(cid)
        else:
            await ws.send_json({"type": "card.error", "code": "bad_kind"})
            return True
        await ws.send_json({"type": "card.default_changed", "kind": kind, "id": cid})
        return True

    if t == "card.import_v2":
        try:
            card = parse_sillytavern_v2(msg.get("json_text", ""))
        except Exception as e:
            await ws.send_json({"type": "card.error", "code": "import_failed", "message": str(e)})
            return True
        cid = repo.upsert_character(card)
        await ws.send_json({"type": "card.imported", "card_id": cid, "warnings": []})
        return True

    if t == "card.export":
        cid = msg.get("id")
        card = repo.get_character(cid)
        if card is None:
            await ws.send_json({"type": "card.error", "code": "not_found"})
        else:
            await ws.send_json({"type": "card.exported", "card": _card_to_dict(card)})
        return True

    if t == "card.set_session_character":
        session_id = msg.get("session_id")
        character_id = msg.get("character_id")
        ctx["engine"].session_store.set_character(session_id, character_id)
        await ws.send_json({
            "type": "card.session_character_set",
            "session_id": session_id,
            "character_id": character_id,
        })
        return True

    if t == "card.list_session_character":
        session_id = msg.get("session_id")
        cid = ctx["engine"].session_store.get_character(session_id)
        await ws.send_json({
            "type": "card.session_character",
            "session_id": session_id,
            "character_id": cid,
        })
        return True

    if t == "card.validate_formula":
        from src.core.formula_engine import validate_formula
        cid = msg.get("character_id")
        available = [m["key"] for m in repo.get_emotion_schema(cid)]
        ok, err = validate_formula(msg.get("formula", ""), available)
        await ws.send_json({"type": "card.formula_validated", "valid": ok, "error": err})
        return True

    if t == "card.get_emotion":
        cid = msg.get("character_id")
        await ws.send_json({
            "type": "card.emotion",
            "character_id": cid,
            "state": repo.get_emotion_state(cid),
            "schema": repo.get_emotion_schema(cid),
            "formulas": repo.get_emotion_formulas(cid),
        })
        return True

    if t == "card.set_emotion_schema":
        cid = msg.get("character_id")
        repo.set_emotion_schema_and_formulas(
            cid, msg.get("schema", []), msg.get("formulas", {})
        )
        await ws.send_json({"type": "card.emotion_schema_set", "character_id": cid})
        return True

    return False


def _card_to_dict(card: Any) -> dict:
    """Serialize a CharacterCard or UserCard to a dict for WS transport."""
    from dataclasses import asdict, is_dataclass
    if is_dataclass(card):
        return asdict(card)
    return dict(card)
