#!/usr/bin/env python
"""Group chat end-to-end: put four real character cards in one room and let the
group turn-taking run for real.

Sandboxed: FSAR_HOME is redirected to a temp directory, so the SQLite store and
the Chroma semantic store are throwaway. The real config is still read (for the
LLM provider) and the character cards are copied in read-only from the real DB,
so nothing in ~/.fsar is modified.

Usage:
    python verify_group_roast.py                      # default "roast" scene
    python verify_group_roast.py --scene kitchen      # the everyday scene
    python verify_group_roast.py --scene kitchen --turns 2 --rounds 3
    python verify_group_roast.py --dry                # no provider calls
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
# The product default is 0 (uncapped). A verification run may set a bound the
# same way a user would, so the harness never depends on killing the process.
_rounds_arg = _arg_value("--rounds")
ROUNDS = int(_rounds_arg) if _rounds_arg.isdigit() else 0
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

# Scenes are data, not code paths: the set-up states the facts and where each
# person stands, and lets the group find its own words. Nothing here dictates
# what anyone should say.
SCENES: dict[str, dict] = {
    "roast": {
        "room_name": "休息室·喷Vera",
        "room_desc": "临时凑起来的一间休息室，气氛很不友好。",
        "scenario": (
            "你们四个此刻同处一间休息室。Vera刚当众宣称："
            "“这种小事也配占用我的时间？”——她一副懒得搭理任何人的样子。"
            "在场的人都不是好脾气，谁都不会因为她傲慢就让着她。"
        ),
        # The point of this arc is that she 吃软不吃硬: pressing her does not
        # work, being straight with her does.
        "turns": [
            ("Vera，你刚才那句话是什么意思？大家都听见了，别装听不见。", True),
            ("行，你不说也行。可你刚才明明可以不说那句话，为什么还是说了？", False),
            ("我不是要你认错。我只是觉得，你要是真觉得这事无聊，你压根不会开口。", True),
            ("那你说吧，要怎样你才肯讲一句真的？", True),
            ("算了，不逼你了。谢谢你至少没直接走。", True),
        ],
    },
    "kitchen": {
        "room_name": "客厅·番茄炒蛋",
        "room_desc": "傍晚的客厅，很平常的一个晚上。",
        "scenario": (
            "客厅，傍晚。Elara在窗边翻一本旧笔记，Lila瘫在沙发上，"
            "Bran靠着门框没说话。你刚开口问了Vera一件很平常的小事，"
            "她当着一屋子人的面把你贬得一文不值，语气里全是“你也配”。"
            "在座的人跟你相处得不算差，谁也没打算替她那份傲慢让路。"
        ),
        "turns": [
            ("Vera，我在学做饭，今天想试试番茄炒蛋，火候怎么掌握？", True),
            ("……她平时都是这么说话的吗？", False),
            ("我不是要她道歉。我只是觉得，对一个真心问问题的人这样说话，挺没意思的。", False),
            ("算了。我接着炒我的蛋，糊了算我自己的。", False),
        ],
    },
}


def _scene() -> dict:
    return SCENES.get(_arg_value("--scene") or "roast", SCENES["roast"])


def _turn_limit() -> int:
    value = _arg_value("--turns")
    return int(value) if value.isdigit() else len(_scene()["turns"])


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
    plumbing can be exercised without spending any provider calls.

    The election fake settles after two rounds. A stub that stayed eager
    forever would spin until killed, because the product default is no round
    cap — a dry run must terminate on its own."""
    from src.server import group_engine as ge_module

    batches = {"n": 0}

    async def fake_batch(client, *, provider_id, model, prompts):
        batches["n"] += 1
        if batches["n"] <= 2:
            eager = 9 if batches["n"] == 1 else 6
        else:
            # This batch settles the chain, so the next one starts a fresh one.
            eager = 0
            batches["n"] = 0
        return [
            json.dumps({"eagerness": eager, "reason": "[dry run]"})
            for _prompt in enumerate(prompts)
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
TOOL_MARKUP_RE = re.compile(r"</?(?:tool_call|function_call)\b", re.IGNORECASE)


def leak_report(rooms: RoomStore, room_id: int, names: dict[int, str]) -> bool:
    """Check the input conventions did not leak into message bodies.

    Two failure modes, both now stripped deterministically and therefore must
    never appear:

    * **own marker** — the model prefixed its own reply with its own name,
      copying the transcript convention back in and compounding it over rounds.
    * **tool markup** — the model wrote
      `<tool_call>{"name":"update_emotion",...}</tool_call>` as visible text,
      because the persona advertised a tool that a group turn does not offer.

    Plus one that prompting only reduces: the model writing another
    character's lines. Nothing mechanical can tell the two voices apart after
    the fact, so it is surfaced as a known limitation rather than a failure.
    """
    own: list[tuple[int, str]] = []
    foreign: list[tuple[int, str]] = []
    tools: list[int] = []
    for row in rooms.messages_with_speaker(room_id):
        if row.role != "assistant":
            continue
        if TOOL_MARKUP_RE.search(row.content):
            tools.append(row.id)
        speaker = (names.get(row.character_card_id or -1) or "").strip()
        for match in LEAK_RE.finditer(row.content):
            label = match.group(0)
            if speaker and speaker in label:
                own.append((row.id, label))
            elif any(name in label for name in LEAK_NAMES) or label.startswith("[user]"):
                foreign.append((row.id, label))

    for row_id, label in own:
        print(f"    own-marker leak in row {row_id}: starts {label!r}")
    for row_id in tools:
        print(f"    tool-call markup leaked into row {row_id}")
    ok = not own and not tools
    print(f"\n[check] own speaker-marker stripped: {'PASS' if ok else 'FAIL'}")
    print(f"[check] tool-call markup stripped: {'PASS' if not tools else 'FAIL'}")
    if foreign:
        print(f"[check] known limitation: {len(foreign)} message(s) contain "
              f"another character's marker")
        for row_id, label in foreign:
            print(f"    row {row_id}: {label!r}")
    else:
        print("[check] no foreign speaker marker bleed")
    return ok


def viola_report(rooms: RoomStore, room_id: int, viola_id: int) -> None:
    """Show Vera's arc rather than judging it.

    An earlier version scanned her last message for concession markers and
    printed a verdict — and called a plainly-persuaded run "still digging in",
    because she concedes in her own idiom ("你倒是懂什么叫见好就收") rather than
    with the words a keyword scan expects. A wrong verdict is worse than none,
    so this prints the arc and lets the reader decide."""
    banner("did Vera come round?")
    rows = [
        row for row in rooms.messages_with_speaker(room_id)
        if row.role == "assistant" and row.character_card_id == viola_id
    ]
    if not rows:
        print("She never spoke at all.")
        return

    def show(label: str, text: str) -> None:
        print(f"{label}:")
        for line in text.strip().splitlines():
            print(f"    {line}")

    print(f"she spoke {len(rows)} time(s).\n")
    show("first", rows[0].content)
    if len(rows) > 1:
        print()
        show("last", rows[-1].content)
    print("\n(no verdict — she concedes in her own idiom, so a keyword scan "
          "gets it wrong; read the arc above)")


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

    scene = _scene()
    room = rooms.create(
        name=scene["room_name"],
        description=scene["room_desc"],
        scenario_prompt=scene["scenario"],
        user_card_id=None,
        character_ids=cast_ids,
        max_rounds=ROUNDS,
    )
    names = {cid: engine.card_repo.get_character(cid).name for cid in cast_ids}
    print(f"\nroom #{room.id} {room.name!r} session={room.session_id}")
    print(f"round cap: {'none (keeps going until it settles)' if ROUNDS == 0 else ROUNDS}")

    banner(f"scene: {scene['room_name']}")
    print(scene["scenario"])

    viola_id = copied["Vera"]
    group = GroupEngine(engine, rooms)
    user_card = engine.card_repo.get_default_user_card()
    collector = Collector()
    turns = scene["turns"][:_turn_limit()]

    for index, (text, mention_viola) in enumerate(turns, start=1):
        banner(f"turn {index}/{len(turns)}  user: {text}")
        if mention_viola:
            print("(@mention: Vera is short-circuited into this round)")
        engine.session_store.append_message(room.session_id, "user", text)
        before = len(collector.events)
        await group.run_chain(
            collector,
            room=room,
            user_input=text,
            mentioned=[viola_id] if mention_viola else [],
            user_card=user_card,
        )
        turns_slice = collector.events[before:]
        # speaker.done carries no name; speaker.start does.
        spoke = [
            (e.get("character_name") or "?").strip() for e in turns_slice
            if e["type"] == "group.speaker.start"
        ]
        finished = next(
            (e["reason"] for e in turns_slice
             if e["type"] == "group.chain.finished"),
            "?",
        )
        print(f"  [turn {index} summary] {len(spoke)} speeches "
              f"({finished}): {spoke}")

    transcript(rooms, room.id, names)
    leak_ok = leak_report(rooms, room.id, names)
    viola_report(rooms, room.id, viola_id)

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
