# SPDX-License-Identifier: MIT
from __future__ import annotations

import asyncio
from pathlib import Path

from src.notifications.store import NotificationStore
from src.server import birthday_runner as br
from src.server import group_engine
from src.utils.fsar_config import FsarConfig


def _config(tmp_path: Path, monkeypatch, **settings) -> FsarConfig:
    monkeypatch.setenv("FSAR_CONFIG_PATH", str(tmp_path / "fsar.yaml"))
    cfg = FsarConfig()
    cfg.patch("data.skins_dir", str(tmp_path / "skins"))
    for key, value in settings.items():
        cfg.patch(key, value)
    return cfg


def _store(tmp_path: Path) -> NotificationStore:
    return NotificationStore(tmp_path / "memory.db")


def _stub_prompt(template: str, seen: list | None = None):
    async def build(conv_id, user_input, character, tools_enabled=True):
        if seen is not None:
            seen.append(tools_enabled)
        return template.format(name=character.name)
    return build


def _engine_with_characters(tmp_path, monkeypatch, names: list[str]):
    from src.memory.cards import CharacterCard
    from src.server.chat_engine import ChatEngine
    from src.server.risk_bridge import RiskBridge

    monkeypatch.setattr("src.memory.semantic.DATA_DIR", tmp_path)
    db_path = tmp_path / "memory.db"
    monkeypatch.setattr(
        FsarConfig, "memory_sqlite_path", property(lambda self: str(db_path)),
    )
    engine = ChatEngine(FsarConfig(), RiskBridge())
    for name in names:
        engine.card_repo.upsert_character(CharacterCard(
            id=None, name=name, description="d", personality="p",
        ))
    return engine


class _FakeWS:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        self.messages.append(payload)


def test_unlock_skin_copies_the_asset_once(tmp_path, monkeypatch):
    cfg = _config(tmp_path, monkeypatch)
    assert br.unlock_skin(cfg) is True
    target = br.skins_dir(cfg) / br.SKIN_ID / "skin.json"
    assert target.is_file()
    assert br.unlock_skin(cfg) is False


def test_skin_id_matches_the_folder_name(tmp_path, monkeypatch):
    """skin_store rejects a skin whose json id does not equal its folder."""
    import json

    cfg = _config(tmp_path, monkeypatch)
    br.unlock_skin(cfg)
    raw = json.loads(
        (br.skins_dir(cfg) / br.SKIN_ID / "skin.json").read_text(encoding="utf-8")
    )
    assert raw["id"] == br.SKIN_ID
    assert raw["base"] == "light"


def test_header_notification_is_written_once_per_year(tmp_path):
    store = _store(tmp_path)
    assert br.write_header_notification(store, 2026, "en") is True
    assert br.write_header_notification(store, 2026, "en") is False
    assert br.write_header_notification(store, 2027, "en") is True


def test_letters_year_reads_the_header_row(tmp_path):
    store = _store(tmp_path)
    assert br.letters_year(store) is None
    br.write_header_notification(store, 2026, "en")
    assert br.letters_year(store) == 2026


def test_letters_land_one_by_one_and_nudge_the_client(tmp_path, monkeypatch):
    engine = _engine_with_characters(tmp_path, monkeypatch, ["Mira", "Kai"])
    monkeypatch.setattr(engine, "client_and_model", lambda: (object(), "m", "stub"))
    monkeypatch.setattr(engine, "_build_character_prompt", _stub_prompt("you are {name}"))
    monkeypatch.setattr(
        group_engine, "_one_completion",
        lambda *a, **k: "happy birthday from me",
    )
    store = _store(tmp_path)
    ws = _FakeWS()

    written = asyncio.run(br.write_character_letters(
        ws=ws, config=engine.config, engine=engine, store=store,
        locale="en", year=2026,
    ))

    assert written == 2
    rows = store.list(kind="birthday")
    bodies = {r["title"]: r["body"] for r in rows}
    assert set(bodies) == {"Mira", "Kai"}
    assert all(bodies[n] for n in ("Mira", "Kai"))
    nudges = [m for m in ws.messages if m["type"] == "notifications.changed"]
    assert len(nudges) == 2


def test_the_letters_carry_the_per_character_system_prompt(tmp_path, monkeypatch):
    engine = _engine_with_characters(tmp_path, monkeypatch, ["Mira"])
    monkeypatch.setattr(engine, "client_and_model", lambda: (object(), "m", "stub"))
    monkeypatch.setattr(engine, "_build_character_prompt", _stub_prompt("you are {name}"))
    seen: list[dict] = []
    monkeypatch.setattr(
        group_engine, "_one_completion",
        lambda *a, **k: seen.append({"args": a, "kw": k}) or "hello",
    )

    asyncio.run(br.write_character_letters(
        ws=_FakeWS(), config=engine.config, engine=engine, store=_store(tmp_path),
        locale="en", year=2026,
    ))

    assert seen[0]["args"][4] == "you are Mira"


def test_a_failed_letter_is_simply_missing(tmp_path, monkeypatch):
    engine = _engine_with_characters(tmp_path, monkeypatch, ["Mira", "Kai"])
    monkeypatch.setattr(engine, "client_and_model", lambda: (object(), "m", "stub"))
    monkeypatch.setattr(engine, "_build_character_prompt", _stub_prompt("you are {name}"))
    store = _store(tmp_path)
    calls = {"n": 0}

    def flaky(*a, **k):
        calls["n"] += 1
        return "" if calls["n"] == 1 else "hello"

    monkeypatch.setattr(group_engine, "_one_completion", flaky)

    written = asyncio.run(br.write_character_letters(
        ws=_FakeWS(), config=engine.config, engine=engine, store=store,
        locale="en", year=2026,
    ))

    assert written == 1
    assert len(store.list(kind="birthday")) == 1


def test_no_characters_writes_nothing(tmp_path, monkeypatch):
    engine = _engine_with_characters(tmp_path, monkeypatch, [])
    store = _store(tmp_path)
    written = asyncio.run(br.write_character_letters(
        ws=_FakeWS(), config=engine.config, engine=engine, store=store,
        locale="en", year=2026,
    ))
    assert written == 0
    assert store.list(kind="birthday") == []


def test_the_most_used_characters_come_first(tmp_path, monkeypatch):
    engine = _engine_with_characters(tmp_path, monkeypatch, ["Rare", "Often"])
    often = next(c for c in engine.card_repo.list_characters() if c.name == "Often")
    for _ in range(3):
        conv = engine.session_store.create()
        engine.session_store.set_character(conv.id, often.id)

    ordered = [c.name for c in br._characters_by_use(engine)]
    assert ordered[0] == "Often"
    assert "Rare" in ordered


def test_letters_are_written_without_advertising_tools(tmp_path, monkeypatch):
    """Telling a character it has update_emotion while offering no tools makes
    it write the call out as text, which is how a letter came back as markup."""
    engine = _engine_with_characters(tmp_path, monkeypatch, ["Mira"])
    monkeypatch.setattr(engine, "client_and_model", lambda: (object(), "m", "stub"))
    seen: list = []
    monkeypatch.setattr(
        engine, "_build_character_prompt", _stub_prompt("you are {name}", seen),
    )
    monkeypatch.setattr(group_engine, "_one_completion", lambda *a, **k: "hello")

    asyncio.run(br.write_character_letters(
        ws=_FakeWS(), config=engine.config, engine=engine, store=_store(tmp_path),
        locale="en", year=2026,
    ))

    assert seen == [False]


def test_a_letter_that_is_only_a_tool_call_is_not_stored(tmp_path, monkeypatch):
    MARKER = chr(0xFF5C) * 2 + "DSML" + chr(0xFF5C) * 2
    engine = _engine_with_characters(tmp_path, monkeypatch, ["Mira"])
    monkeypatch.setattr(engine, "client_and_model", lambda: (object(), "m", "stub"))
    monkeypatch.setattr(engine, "_build_character_prompt", _stub_prompt("you are {name}"))
    leaked = chr(10).join([
        f"<{MARKER} calls>",
        f'<{MARKER} invoke name="update_emotion">',
        f"</{MARKER} invoke>",
        f"</{MARKER} calls>",
    ])
    monkeypatch.setattr(group_engine, "_one_completion", lambda *a, **k: leaked)
    store = _store(tmp_path)

    written = asyncio.run(br.write_character_letters(
        ws=_FakeWS(), config=engine.config, engine=engine, store=store,
        locale="en", year=2026,
    ))

    assert written == 0
    assert store.list(kind="birthday") == []
