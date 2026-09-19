#!/usr/bin/env python
"""Group chat end-to-end: put four real character cards in one room and let the
group turn-taking run for real.

Sandboxed: FSAR_HOME is redirected to a temp directory, so the SQLite store and
the Chroma semantic store are throwaway. The real config is still read (for the
LLM provider) and the character cards are copied in read-only from the real DB,
so nothing in ~/.fsar is modified.

Usage:
    python verify_group_roast.py            # sandbox, cleaned up afterwards
    python verify_group_roast.py --keep     # keep the sandbox dir and print it
"""
from __future__ import annotations

import asyncio
import io
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

REAL_HOME = Path(
    os.environ.get("FSAR_HOME", "").strip() or (Path.home() / ".fsar")
)
REAL_CONFIG = Path(
    os.environ.get("FSAR_CONFIG_PATH", "").strip()
    or (REAL_HOME / "config" / "fsar.yaml")
)
REAL_DB = REAL_HOME / "data" / "memory.db"

KEEP = "--keep" in sys.argv
DRY = "--dry" in sys.argv
VERBOSE = "--verbose" in sys.argv


def _arg_value(flag: str) -> str:
    if flag in sys.argv:
        index = sys.argv.index(flag)
        if index + 1 < len(sys.argv):
            return sys.argv[index + 1]
    return ""


PROVIDER = _arg_value("--provider")
SANDBOX = Path(tempfile.mkdtemp(prefix="fsar-group-e2e-"))
os.environ["FSAR_HOME"] = str(SANDBOX)
os.environ["FSAR_CONFIG_PATH"] = str(REAL_CONFIG)

sys.path.insert(0, str(Path(__file__).parent))

from src.memory.rooms import RoomStore  # noqa: E402
from src.server.chat_engine import ChatEngine  # noqa: E402
from src.server.group_engine import GroupEngine, EAGER_THRESHOLD  # noqa: E402
from src.server.risk_bridge import RiskBridge  # noqa: E402
from src.utils.fsar_config import FsarConfig  # noqa: E402

if not VERBOSE:
    # The sandbox has no embedding server, so semantic recall/add warnings would
    # repeat on every turn and drown out the transcript.
    from loguru import logger as _loguru  # noqa: E402

    _loguru.disable("src.memory.semantic")
    _loguru.disable("src.memory.lmstudio_embed")

CAST_NAMES = ["Elara", "Bran", "Lila", "Vera"]

SCENARIO = (
    "你们四个此刻同处一间休息室。Vera刚当众宣称："
    "“这种小事也配占用我的时间？”——她一副懒得搭理任何人的样子。"
    "在场的人都不是好脾气，谁都不会因为她傲慢就让着她。"
)

ROOM_NAME = "休息室·喷Vera"
ROOM_DESC = "临时凑起来的一间休息室，气氛很不友好。"


def banner(text: str) -> None:
    print(f"\n{'=' * 72}\n{text}\n{'=' * 72}")


def copy_cards(src_db: Path, dst_db: Path) -> dict[str, int]:
    """Read-only copy of the cast's cards (and the default user card)."""
    src = sqlite3.connect(f"file:{src_db.as_posix()}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row
    dst = sqlite3.connect(dst_db)
    copied: dict[str, int] = {}
    for table, where in (
        ("character_cards", f"TRIM(name) IN ({','.join('?' * len(CAST_NAMES))})"),
        ("user_cards", "is_default = 1"),
    ):
        cols = [r[1] for r in src.execute(f"PRAGMA table_info({table})").fetchall()]
        rows = src.execute(f"SELECT * FROM {table} WHERE {where}", CAST_NAMES
                           if table == "character_cards" else []).fetchall()
        placeholders = ",".join("?" * len(cols))
        for row in rows:
            dst.execute(
                f"INSERT OR REPLACE INTO {table} ({','.join(cols)}) "
                f"VALUES ({placeholders})",
                [row[c] for c in cols],
            )
            if table == "character_cards":
                copied[str(row["name"]).strip()] = row["id"]
    dst.commit()
    src.close()
    dst.close()
    return copied


def _stub_llm() -> None:
    """--dry: replace both LLM entry points with deterministic fakes so the
    plumbing can be exercised without spending any provider calls."""
    from src.server import group_engine as ge_module

    async def fake_batch(client, *, provider_id, model, prompts):
        return [
            json.dumps({"eagerness": 9 if i % 2 == 0 else 6, "reason": "[dry run]"})
            for i, _prompt in enumerate(prompts)
        ]

    ge_module.run_batch_completions = fake_batch

    async def fake_stream(self, ws, **kwargs):
        text = f"[dry run reply from {kwargs.get('char_name')}]"
        for word in text.split():
            await ws.send_json({
                "type": "chat.delta",
                "message_id": kwargs["message_id"],
                "conversation_id": kwargs["conv_id"],
                "content": word + " ",
            })
        return text

    ChatEngine._stream_one_reply = fake_stream


class Collector:
    """Stands in for the GUI websocket: records every group.* event.

    Deltas are buffered and printed as one block per speaker so log lines
    cannot interleave inside a message."""

    def __init__(self) -> None:
        self.events: list[dict] = []
        self._buffer: list[str] = []
        self._speaker = ""

    async def send_json(self, payload: dict) -> None:
        self.events.append(payload)
        self._render(payload)

    def _render(self, payload: dict) -> None:
        kind = payload.get("type", "")
        if kind == "group.elect.started":
            print(f"\n[round {payload['round']}] election opened "
                  f"({len(payload['candidates'])} candidates)")
        elif kind == "group.elect.candidate":
            bar = "#" * payload["eagerness"] + "." * (10 - payload["eagerness"])
            print(f"    {payload['character_name']:<7} {bar} "
                  f"{payload['eagerness']:>2}/10  {payload['reason']}")
        elif kind == "group.elect.decided":
            print(f"  -> round {payload['round']} speakers: {payload['speakers']}")
        elif kind == "group.speaker.start":
            self._speaker = str(payload.get("character_name") or "?")
            self._buffer = []
        elif kind == "group.speaker.delta":
            self._buffer.append(payload["content"])
        elif kind == "group.speaker.done":
            print(f"\n{self._speaker.strip()}: {''.join(self._buffer).strip()}")
            state = payload.get("emotion_state")
            if state:
                top = sorted(state.items(), key=lambda kv: kv[1], reverse=True)[:3]
                print("    (emotion " +
                      ", ".join(f"{k}={v:.2f}" for k, v in top) + ")")
            self._buffer = []
        elif kind == "group.chain.finished":
            print(f"\n[chain finished: {payload['reason']}]")
        elif kind == "tts.synthesize_queued":
            print(f"    [tts queued] {payload['text_preview'][:60]}")
        elif kind == "group.error":
            print(f"    [group error] {payload['code']}: {payload['message']}")


def transcript(rooms: RoomStore, room_id: int, names: dict[int, str]) -> None:
    banner("persisted transcript (what the GUI would reload)")
    rows = rooms.messages_with_speaker(room_id)
    if not rows:
        print("(empty — the chain produced nothing)")
        return
    for row in rows:
        who = "user" if row.role == "user" else names.get(
            row.character_card_id or -1, f"card#{row.character_card_id}"
        )
        print(f"[{who}] {row.content}")


LEAK_RE = re.compile(r"\[[^\[\]\n]{1,24}\]\s*[:：]")
LEAK_NAMES = ["Elara", "Bran", "Lila", "Vera"]


def leak_report(rooms: RoomStore, room_id: int) -> bool:
    """Guard against the speaker-marker convention leaking into message bodies.

    The room history is written as "[Name]: text" so the model can tell voices
    apart. An early version also fed the trigger back in that shape and the
    model copied it — and once one reply contained another character's line,
    later turns copied the doubled form too. This checks that stays fixed."""
    leaks: list[tuple[int, str]] = []
    for row in rooms.messages_with_speaker(room_id):
        if row.role != "assistant":
            continue
        match = LEAK_RE.search(row.content)
        if match is None:
            continue
        label = match.group(0)
        if any(name in label for name in LEAK_NAMES) or label in ("[user]:",):
            leaks.append((row.id, label))
    if not leaks:
        print("\n[check] no speaker-marker leak in message bodies: PASS")
        return True
    print(f"\n[check] speaker-marker leak detected in {len(leaks)} message(s): FAIL")
    for row_id, label in leaks:
        print(f"    row {row_id} starts a line with {label!r}")
    return False


async def main() -> int:
    banner("sandbox")
    print(f"real home   : {REAL_HOME}")
    print(f"real config : {REAL_CONFIG}")
    print(f"real db     : {REAL_DB}  (read only)")
    print(f"sandbox     : {SANDBOX}")
    if not REAL_DB.exists():
        print(f"\nNo ${REAL_DB} - nothing to run against.")
        return 2

    config = FsarConfig(REAL_CONFIG)
    engine = ChatEngine(config, RiskBridge())
    if PROVIDER:
        # Instance-level override only: the config file on disk is untouched.
        override_model = str(
            (config.get_llm_config(PROVIDER) or {}).get("model") or ""
        )
        engine._session_model_override = f"{PROVIDER}:{override_model}"
        print(f"[override] provider {PROVIDER} / {override_model} for this run only")
    db_path = Path(config.memory_sqlite_path)
    rooms = RoomStore(db_path, engine.session_store)

    copied = copy_cards(REAL_DB, db_path)
    missing = [n for n in CAST_NAMES if n not in copied]
    if missing:
        print(f"\nMissing character cards: {missing}")
        return 2
    cast_ids = [copied[n] for n in CAST_NAMES]

    banner("cast")
    for name in CAST_NAMES:
        card = engine.card_repo.get_character(copied[name])
        print(f"  [{card.id:>3}] {card.name} — {card.personality[:48]}")

    client, model, provider_id = engine.client_and_model()
    banner("model")
    if DRY:
        print("[dry run] LLM calls are stubbed - no provider usage.")
        _stub_llm()
    else:
        print(f"provider={provider_id}  model={model}")
        if not model:
            print("No active chat model configured - configure one in Settings first.")
            return 2

    room = rooms.create(
        name=ROOM_NAME,
        description=ROOM_DESC,
        scenario_prompt=SCENARIO,
        user_card_id=None,
        character_ids=cast_ids,
    )
    names = {cid: engine.card_repo.get_character(cid).name for cid in cast_ids}
    print(f"\nroom #{room.id} {room.name!r} session={room.session_id}")

    banner("scenario prompt")
    print(SCENARIO)

    opening = "Vera，你刚才那句话是什么意思？大家都听见了，别装听不见。"
    mentioned = [copied["Vera"]]
    banner(f"user: {opening}")
    print(f"(@mention short-circuits the election for Vera -> {mentioned})")
    engine.session_store.append_message(room.session_id, "user", opening)

    collector = Collector()
    await GroupEngine(engine, rooms).run_chain(
        collector,
        room=room,
        user_input=opening,
        mentioned=mentioned,
        user_card=engine.card_repo.get_default_user_card(),
    )

    transcript(rooms, room.id, names)
    leak_ok = leak_report(rooms, room.id)

    banner("event log summary")
    counts: dict[str, int] = {}
    for event in collector.events:
        counts[event["type"]] = counts.get(event["type"], 0) + 1
    for kind, count in sorted(counts.items()):
        print(f"  {count:>3}  {kind}")

    speakers = [e for e in collector.events if e["type"] == "group.speaker.done"]
    print(f"\n{eager_note(speakers)}")

    if KEEP:
        print(f"\nSandbox kept at {SANDBOX}")
    else:
        shutil.rmtree(SANDBOX, ignore_errors=True)
        print("\nSandbox removed (nothing written to the real FSAR home).")
    return 0 if leak_ok else 1


def eager_note(speakers: list[dict]) -> str:
    return (
        f"{len(speakers)} character turns were produced "
        f"(threshold={EAGER_THRESHOLD}, hard caps 4 rounds / 24 calls)."
    )


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
