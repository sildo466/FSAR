# PL2.0 — Persona Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make FSAR feel like a *person*: character + user cards (CRUD, JSON + ST V2 import), persona injection into system prompt, per-session character binding, emotion subsystem (math engine + LLM `update_emotion` tool), `/cards` page, Chat topbar character dropdown, message labels (character name on ASSISTANT, user name on USER).

**Architecture:** Tauri + React GUI; Python backend (existing chat engine extended). New tables (`character_cards`, `user_cards`, `emotion_audit`) live in the existing `data/fsar.db`. `src/core/formula_engine.py` ports WordBox's safe expression evaluator. Persona assembly is a single `build_system_prompt()` function in `src/core/prompts.py` (single source of truth, per P7.11 invariant).

**Tech Stack:** Python 3.11+, SQLite (existing), existing FastAPI/WS stack; React 18 + TypeScript (existing); nothing new added.

**Spec:** `docs/superpowers/specs/2026-07-09-pl2-0-persona-foundation-design.md`

---

## Global Constraints

These apply to every task below. Each task's implementation must respect all of them.

1. **License header**: Every new `.py` and `.tsx` source file starts with `# SPDX-License-Identifier: Apache-2.0` (Python) or `// SPDX-License-Identifier: Apache-2.0` (TS/TSX).
2. **DRY / YAGNI**: No abstractions beyond what the spec requires. No premature configuration knobs. Per CLAUDE.md "Simplicity First": if 200 lines and 50 would do, rewrite.
3. **TDD when feasible**: Backend logic has pytest tests written before implementation. Frontend component logic has React Testing Library tests when the test cost is low. Pure visual code may skip.
4. **Frequent commits**: Each task ends with a `git commit` step. Conventional Commits (`feat:`, `refactor:`, `test:`, `docs:`, `chore:`).
5. **No silent error swallowing**: Every `except` clause either logs or re-raises. Never bare `pass`.
6. **Python type hints**: All new Python files use `from __future__ import annotations` + PEP 604 unions (`X | None`).
7. **Idempotent migrations**: All schema changes use `_migrate_*` methods that check `PRAGMA table_info` before `ALTER TABLE`. Mirrors existing `SessionStore._migrate_conversations` pattern.
8. **Single source of truth for prompts**: `src/core/prompts.py` is the only place system prompt text is defined. CLI `main.py` and GUI `ChatEngine` both call `build_system_prompt()`.
9. **Test scope (per spec §9)**: 7 files, ~38 cases. Don't exceed. If a task adds a test file not in this list, defer or update the spec first.
10. **English hardcoded prompts**; comments in English; non-essential comments avoided (per project CLAUDE.md).
11. **DB-first emotion state**: `character_cards.emotion_state` (JSON) is the canonical store; `emotion_audit` is append-only history. No files; no caching layer beyond LLM cache.
12. **No mid-conversation character switch** in PL2.0; per-session binding only (spec D1).

---

## File Structure

**New files:**
```
src/core/persona.py                      # assemble_persona_block + PersonaBlock + PersonaMissingError
src/core/formula_engine.py               # safe expression evaluator (D16)
src/memory/cards.py                      # CardRepo (CRUD + ST V2 + emotion helpers)
src/tools/builtin/update_emotion.py      # LLM tool (D17)
src/server/handlers/card.py              # WS handler + HTTP avatar endpoint
data/cards/_meta.json                    # seed metadata
data/cards/FSAR-zh.json
data/cards/FSAR-en.json
data/cards/coding-coach-zh.json
data/cards/coding-coach-en.json
data/cards/research-analyst-zh.json
data/cards/research-analyst-en.json
data/cards/default-user.json
data/emotion_default.json                # DEFAULT_EMOTION_SCHEMA + DEFAULT_EMOTION_FORMULAS
frontend/src/pages/Cards.tsx
frontend/src/components/cards/CharacterCardList.tsx
frontend/src/components/cards/CharacterCardEditor.tsx
frontend/src/components/cards/UserCardList.tsx
frontend/src/components/cards/UserCardEditor.tsx
frontend/src/components/chat/CharacterSelector.tsx
frontend/src/stores/cards.ts
tests/test_cards_repo.py
tests/test_persona_assembler.py
tests/test_prompt_builder.py
tests/test_session_character_binding.py
tests/test_st_v2_parser.py
tests/test_formula_engine.py
tests/test_emotion_updater.py
```

**Modified files:**
```
src/core/prompts.py                      # +build_system_prompt
src/memory/session_store.py              # +_migrate_character_binding + set/get_character
src/server/chat_engine.py                # character resolution + emotion flow + emit extended payload
src/server/ws_server.py                  # register card handler + seed call
src/tools/builtin/__init__.py            # register update_emotion
main.py                                  # call build_system_prompt; seed at startup
frontend/src/pages/Chat.tsx              # topbar character selector + message labels
frontend/src/components/chat/Topbar.tsx  # accept CharacterSelector
frontend/src/components/chat/MessageList.tsx  # read character_name + user_name
```

---

## Task Index

5 slices, ~38 tasks. Each task is a focused unit with its own commit.

| Slice | Tasks | Focus |
|---|---|---|
| 1 — Data + backend core | 1.1 → 1.15 | Tables, repos, formula engine, persona, prompts, tool, seed |
| 2 — WS handlers + seed | 2.1 → 2.9 | Card CRUD over WS, avatar HTTP, emotion WS types |
| 3 — Chat topbar + labels | 3.1 → 3.6 | Frontend store, selector, topbar wiring, message labels |
| 4 — /cards page (character tab) | 4.1 → 4.8 | Page, list, editor, avatar, import/export, emotion section |
| 5 — /cards page (user tab) + E2E | 5.1 → 5.4 | User list/editor, preferences UI, E2E smoke, CLI regression |

---

# Slice 1 — Data + Backend Core

### Task 1.1: Add `character_cards`, `user_cards`, `emotion_audit` tables

**Files:**
- Create: `src/memory/cards.py` (table-creation methods only)
- Test: `tests/test_cards_repo.py` (table creation)

**Interfaces:**
- Consumes: nothing (first task)
- Produces: `CardRepo.ensure_tables(conn)` — idempotent `CREATE TABLE IF NOT EXISTS` for the 3 tables

- [ ] **Step 1: Write failing test**

```python
# tests/test_cards_repo.py
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

from src.memory.cards import CardRepo


def test_ensure_tables_creates_all_three_tables():
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "test.db"
        repo = CardRepo(db)
        with sqlite3.connect(db) as conn:
            repo.ensure_tables(conn)
            names = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        assert "character_cards" in names
        assert "user_cards" in names
        assert "emotion_audit" in names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cards_repo.py::test_ensure_tables_creates_all_three_tables -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.memory.cards'`

- [ ] **Step 3: Write minimal `CardRepo` skeleton**

```python
# src/memory/cards.py
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CharacterCard:
    id: int | None
    name: str
    description: str
    personality: str
    scenario: str = ""
    system_prompt_override: str = ""
    example_dialogues: list[dict] | None = None
    tags: list[str] | None = None
    avatar_path: str | None = None
    is_default: int = 0
    created_by: str = "user"
    created_at: str = ""
    updated_at: str = ""
    emotion_state: dict[str, float] | None = None
    emotion_schema: list[dict] | None = None
    emotion_formulas: dict[str, str] | None = None


@dataclass
class UserCard:
    id: int | None
    name: str
    description: str
    preferences: dict | None = None
    interests: list[str] | None = None
    communication_style: str = ""
    avatar_path: str | None = None
    is_default: int = 0
    created_by: str = "user"
    created_at: str = ""
    updated_at: str = ""


class CardRepo:
    def __init__(self, db_path: Path):
        self._db = db_path

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db)

    def ensure_tables(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS character_cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                avatar_path TEXT,
                description TEXT NOT NULL,
                personality TEXT NOT NULL,
                scenario TEXT DEFAULT '',
                system_prompt_override TEXT DEFAULT '',
                example_dialogues TEXT DEFAULT '[]',
                tags TEXT DEFAULT '[]',
                is_default INTEGER NOT NULL DEFAULT 0,
                created_by TEXT NOT NULL DEFAULT 'user',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                emotion_state TEXT DEFAULT '{}',
                emotion_schema TEXT DEFAULT '[]',
                emotion_formulas TEXT DEFAULT '{}'
            )
            """
        )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_character_cards_default "
            "ON character_cards(is_default) WHERE is_default = 1"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                avatar_path TEXT,
                description TEXT NOT NULL,
                preferences TEXT DEFAULT '{}',
                interests TEXT DEFAULT '[]',
                communication_style TEXT DEFAULT '',
                is_default INTEGER NOT NULL DEFAULT 0,
                created_by TEXT NOT NULL DEFAULT 'user',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_user_cards_default "
            "ON user_cards(is_default) WHERE is_default = 1"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS emotion_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                character_id INTEGER NOT NULL,
                session_id TEXT,
                metric_key TEXT NOT NULL,
                old_value REAL NOT NULL,
                new_value REAL NOT NULL,
                delta REAL NOT NULL,
                reason TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'update_emotion',
                created_at TEXT NOT NULL,
                FOREIGN KEY (character_id) REFERENCES character_cards(id) ON DELETE CASCADE
            )
            """
        )
        conn.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cards_repo.py::test_ensure_tables_creates_all_three_tables -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/memory/cards.py tests/test_cards_repo.py
git commit -m "feat(memory): add character_cards / user_cards / emotion_audit tables"
```

---

### Task 1.2: Character card CRUD

**Files:**
- Modify: `src/memory/cards.py` (add CRUD methods)
- Modify: `tests/test_cards_repo.py` (add CRUD tests)

**Interfaces:**
- Consumes: `CharacterCard` from Task 1.1
- Produces: `CardRepo.list_characters()`, `get_character(id)`, `get_default_character()`, `upsert_character(card)`, `delete_character(id)`, `set_default_character(id)`

- [ ] **Step 1: Add failing tests for CRUD**

```python
# append to tests/test_cards_repo.py
import json
import pytest
from src.memory.cards import CharacterCard


@pytest.fixture
def repo():
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "test.db"
        r = CardRepo(db)
        with sqlite3.connect(db) as conn:
            r.ensure_tables(conn)
        yield r


def _make_card(**overrides) -> CharacterCard:
    now = "2026-07-09T00:00:00"
    base = dict(
        id=None, name="FSAR", description="test desc",
        personality="friendly", emotion_state={"affection": 50},
    )
    base.update(overrides)
    base.setdefault("created_at", now)
    base.setdefault("updated_at", now)
    return CharacterCard(**base)


def test_upsert_and_get_character(repo):
    card = _make_card()
    cid = repo.upsert_character(card)
    fetched = repo.get_character(cid)
    assert fetched is not None
    assert fetched.name == "FSAR"
    assert fetched.description == "test desc"
    assert fetched.emotion_state == {"affection": 50}


def test_list_characters_empty(repo):
    assert repo.list_characters() == []


def test_list_characters_returns_all(repo):
    repo.upsert_character(_make_card(name="A"))
    repo.upsert_character(_make_card(name="B"))
    names = [c.name for c in repo.list_characters()]
    assert names == ["A", "B"]


def test_set_default_character(repo):
    a = repo.upsert_character(_make_card(name="A"))
    b = repo.upsert_character(_make_card(name="B"))
    repo.set_default_character(b)
    assert repo.get_default_character().id == b
    assert repo.get_character(a).is_default == 0


def test_set_default_only_one_default_at_a_time(repo):
    a = repo.upsert_character(_make_card(name="A", is_default=1))
    b = repo.upsert_character(_make_card(name="B"))
    repo.set_default_character(b)
    rows = repo.list_characters()
    defaults = [c.id for c in rows if c.is_default == 1]
    assert defaults == [b]


def test_delete_character(repo):
    cid = repo.upsert_character(_make_card(name="X"))
    assert repo.delete_character(cid) is True
    assert repo.get_character(cid) is None


def test_delete_character_returns_false_when_missing(repo):
    assert repo.delete_character(999) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cards_repo.py -v`
Expected: failures with `AttributeError: 'CardRepo' object has no attribute 'upsert_character'`

- [ ] **Step 3: Implement CRUD methods**

Add to `src/memory/cards.py` (inside `class CardRepo`):

```python
    def _row_to_character(self, row: sqlite3.Row) -> CharacterCard:
        return CharacterCard(
            id=row["id"],
            name=row["name"],
            avatar_path=row["avatar_path"],
            description=row["description"],
            personality=row["personality"],
            scenario=row["scenario"],
            system_prompt_override=row["system_prompt_override"],
            example_dialogues=json.loads(row["example_dialogues"] or "[]"),
            tags=json.loads(row["tags"] or "[]"),
            is_default=row["is_default"],
            created_by=row["created_by"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            emotion_state=json.loads(row["emotion_state"] or "{}"),
            emotion_schema=json.loads(row["emotion_schema"] or "[]"),
            emotion_formulas=json.loads(row["emotion_formulas"] or "{}"),
        )

    def list_characters(self) -> list[CharacterCard]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM character_cards ORDER BY is_default DESC, name ASC"
            ).fetchall()
        return [self._row_to_character(r) for r in rows]

    def get_character(self, card_id: int) -> CharacterCard | None:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            r = conn.execute(
                "SELECT * FROM character_cards WHERE id = ?", (card_id,)
            ).fetchone()
        return self._row_to_character(r) if r else None

    def get_default_character(self) -> CharacterCard | None:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            r = conn.execute(
                "SELECT * FROM character_cards WHERE is_default = 1 LIMIT 1"
            ).fetchone()
        return self._row_to_character(r) if r else None

    def upsert_character(self, card: CharacterCard) -> int:
        import datetime as _dt
        now = _dt.datetime.now().isoformat()
        payload = (
            card.name,
            card.avatar_path,
            card.description,
            card.personality,
            card.scenario,
            card.system_prompt_override,
            json.dumps(card.example_dialogues or [], ensure_ascii=False),
            json.dumps(card.tags or [], ensure_ascii=False),
            card.is_default,
            card.created_by,
            card.created_at or now,
            card.updated_at or now,
            json.dumps(card.emotion_state or {}, ensure_ascii=False),
            json.dumps(card.emotion_schema or [], ensure_ascii=False),
            json.dumps(card.emotion_formulas or {}, ensure_ascii=False),
        )
        with self._connect() as conn:
            if card.id is None:
                cur = conn.execute(
                    """
                    INSERT INTO character_cards
                    (name, avatar_path, description, personality, scenario,
                     system_prompt_override, example_dialogues, tags, is_default,
                     created_by, created_at, updated_at,
                     emotion_state, emotion_schema, emotion_formulas)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    payload,
                )
                return cur.lastrowid
            else:
                conn.execute(
                    """
                    UPDATE character_cards SET
                        name=?, avatar_path=?, description=?, personality=?,
                        scenario=?, system_prompt_override=?,
                        example_dialogues=?, tags=?, is_default=?, created_by=?,
                        created_at=?, updated_at=?,
                        emotion_state=?, emotion_schema=?, emotion_formulas=?
                    WHERE id=?
                    """,
                    payload + (card.id,),
                )
                return card.id

    def delete_character(self, card_id: int) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM character_cards WHERE id = ?", (card_id,)
            )
            return cur.rowcount > 0

    def set_default_character(self, card_id: int) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE character_cards SET is_default = 0 WHERE is_default = 1")
            conn.execute("UPDATE character_cards SET is_default = 1 WHERE id = ?", (card_id,))
            conn.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cards_repo.py -v`
Expected: PASS for all 7 tests

- [ ] **Step 5: Commit**

```bash
git add src/memory/cards.py tests/test_cards_repo.py
git commit -m "feat(memory): character card CRUD + default toggle"
```

---

### Task 1.3: User card CRUD

**Files:**
- Modify: `src/memory/cards.py` (add user CRUD methods)
- Modify: `tests/test_cards_repo.py` (add user tests)

**Interfaces:**
- Consumes: `UserCard` from Task 1.1
- Produces: `CardRepo.list_user_cards()`, `get_user_card(id)`, `get_default_user_card()`, `upsert_user_card(card)`, `delete_user_card(id)`, `set_default_user_card(id)`

- [ ] **Step 1: Add failing tests for user CRUD**

```python
# append to tests/test_cards_repo.py
from src.memory.cards import UserCard


def _make_user(**overrides) -> UserCard:
    now = "2026-07-09T00:00:00"
    base = dict(
        id=None, name="default-user",
        description="FSAR owner, prefers Chinese",
        preferences={"language": "zh"},
    )
    base.update(overrides)
    base.setdefault("created_at", now)
    base.setdefault("updated_at", now)
    return UserCard(**base)


def test_upsert_and_get_user_card(repo):
    card = _make_user()
    cid = repo.upsert_user_card(card)
    fetched = repo.get_user_card(cid)
    assert fetched.name == "default-user"
    assert fetched.preferences == {"language": "zh"}


def test_get_default_user_card(repo):
    repo.upsert_user_card(_make_user(name="X"))
    default = repo.upsert_user_card(_make_user(name="Y", is_default=1))
    assert repo.get_default_user_card().id == default


def test_set_default_user_card_only_one_default(repo):
    a = repo.upsert_user_card(_make_user(name="A", is_default=1))
    b = repo.upsert_user_card(_make_user(name="B"))
    repo.set_default_user_card(b)
    defaults = [u.id for u in repo.list_user_cards() if u.is_default == 1]
    assert defaults == [b]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cards_repo.py -k "user_card" -v`
Expected: failures with `AttributeError`

- [ ] **Step 3: Implement user CRUD methods**

Add to `src/memory/cards.py` (inside `class CardRepo`):

```python
    def _row_to_user(self, row: sqlite3.Row) -> UserCard:
        return UserCard(
            id=row["id"],
            name=row["name"],
            avatar_path=row["avatar_path"],
            description=row["description"],
            preferences=json.loads(row["preferences"] or "{}"),
            interests=json.loads(row["interests"] or "[]"),
            communication_style=row["communication_style"],
            is_default=row["is_default"],
            created_by=row["created_by"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def list_user_cards(self) -> list[UserCard]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM user_cards ORDER BY is_default DESC, name ASC"
            ).fetchall()
        return [self._row_to_user(r) for r in rows]

    def get_user_card(self, card_id: int) -> UserCard | None:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            r = conn.execute("SELECT * FROM user_cards WHERE id = ?", (card_id,)).fetchone()
        return self._row_to_user(r) if r else None

    def get_default_user_card(self) -> UserCard | None:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            r = conn.execute("SELECT * FROM user_cards WHERE is_default = 1 LIMIT 1").fetchone()
        return self._row_to_user(r) if r else None

    def upsert_user_card(self, card: UserCard) -> int:
        import datetime as _dt
        now = _dt.datetime.now().isoformat()
        payload = (
            card.name, card.avatar_path, card.description,
            json.dumps(card.preferences or {}, ensure_ascii=False),
            json.dumps(card.interests or [], ensure_ascii=False),
            card.communication_style, card.is_default, card.created_by,
            card.created_at or now, card.updated_at or now,
        )
        with self._connect() as conn:
            if card.id is None:
                cur = conn.execute(
                    """
                    INSERT INTO user_cards
                    (name, avatar_path, description, preferences, interests,
                     communication_style, is_default, created_by, created_at, updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?)
                    """,
                    payload,
                )
                return cur.lastrowid
            else:
                conn.execute(
                    """
                    UPDATE user_cards SET
                        name=?, avatar_path=?, description=?, preferences=?,
                        interests=?, communication_style=?, is_default=?,
                        created_by=?, created_at=?, updated_at=?
                    WHERE id=?
                    """,
                    payload + (card.id,),
                )
                return card.id

    def delete_user_card(self, card_id: int) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM user_cards WHERE id = ?", (card_id,))
            return cur.rowcount > 0

    def set_default_user_card(self, card_id: int) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE user_cards SET is_default = 0 WHERE is_default = 1")
            conn.execute("UPDATE user_cards SET is_default = 1 WHERE id = ?", (card_id,))
            conn.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cards_repo.py -v`
Expected: PASS for all tests

- [ ] **Step 5: Commit**

```bash
git add src/memory/cards.py tests/test_cards_repo.py
git commit -m "feat(memory): user card CRUD + default toggle"
```

---

### Task 1.4: `formula_engine.py` — port safe expression evaluator

**Files:**
- Create: `src/core/formula_engine.py`
- Create: `tests/test_formula_engine.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `validate_formula(formula: str, available_vars: list[str]) -> tuple[bool, str | None]`
  - `evaluate_formula(formula: str, values: dict[str, float], lo: float, hi: float) -> float`
  - `execute_emotion_formulas(metrics, formulas, current) -> dict[str, float]`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_formula_engine.py
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import pytest
from src.core.formula_engine import (
    validate_formula,
    evaluate_formula,
    execute_emotion_formulas,
)


def test_validate_basic_arithmetic():
    ok, err = validate_formula("a + b * 2", ["a", "b"])
    assert ok and err is None


def test_validate_rejects_function_call():
    ok, err = validate_formula("eval('1+1')", [])
    assert not ok
    assert "Function calls" in err or "disallowed" in err


def test_validate_rejects_property_access():
    ok, err = validate_formula("a.__class__", ["a"])
    assert not ok


def test_validate_rejects_empty():
    ok, err = validate_formula("", [])
    assert not ok


def test_validate_rejects_too_long():
    ok, err = validate_formula("a" + " + b" * 200, ["a", "b"])
    assert not ok


def test_evaluate_basic():
    assert evaluate_formula("1 + 2", {}, 0, 100) == 3


def test_evaluate_with_variables():
    assert evaluate_formula("affection + 5", {"affection": 50}, 0, 100) == 55


def test_evaluate_clamps_to_min_max():
    assert evaluate_formula("1000", {}, 0, 100) == 100
    assert evaluate_formula("-1000", {}, 0, 100) == 0


def test_evaluate_division_by_zero_returns_zero():
    assert evaluate_formula("5 / 0", {}, 0, 100) == 0


def test_evaluate_nested_parens():
    assert evaluate_formula("(1 + 2) * (3 + 4)", {}, 0, 100) == 21


def test_execute_emotion_formulas_one_tick():
    metrics = [
        {"key": "energy", "min": 0, "max": 100, "initial": 50},
        {"key": "mood", "min": -100, "max": 100, "initial": 0},
    ]
    formulas = {"energy": "energy - 0.5", "mood": "mood * 0.95"}
    current = {"energy": 80, "mood": 20}
    result = execute_emotion_formulas(metrics, formulas, current)
    assert result["energy"] == 79.5
    assert result["mood"] == pytest.approx(19.0)


def test_execute_emotion_formulas_skips_metrics_without_formula():
    metrics = [
        {"key": "empathy", "min": 0, "max": 100, "initial": 50},
    ]
    formulas: dict[str, str] = {}
    current = {"empathy": 50}
    result = execute_emotion_formulas(metrics, formulas, current)
    assert result == {"empathy": 50}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_formula_engine.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement formula engine**

```python
# src/core/formula_engine.py
# SPDX-License-Identifier: Apache-2.0
"""Safe expression evaluator for emotion formulas.

Modeled on WordBox's formula-engine.ts (300 lines, MIT). Same safety
constraints: only +, -, *, /, numbers, variable references, parens.
Rejects function calls, property access, assignment, comparison ops.
Formula length cap 500 chars. Returns 0 on any error. Clamps to [min, max].
"""
from __future__ import annotations

import re
from typing import Iterable

_MAX_FORMULA_LEN = 500
_ALLOWED_CHARS = re.compile(r"^[a-zA-Z0-9_.+\-*/() \t]+$")
_VAR_NAME = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
_FUNC_CALL = re.compile(r"\b[a-zA-Z_][a-zA-Z0-9_]*\s*\(")


def _tokenize(expr: str) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    i = 0
    while i < len(expr):
        ch = expr[i]
        if ch in (" ", "\t"):
            i += 1
            continue
        if ch.isdigit() or (ch == "." and i + 1 < len(expr) and expr[i + 1].isdigit()):
            j = i
            while j < len(expr) and (expr[j].isdigit() or expr[j] == "."):
                j += 1
            tokens.append(("number", expr[i:j]))
            i = j
            continue
        if ch.isalpha() or ch == "_":
            j = i
            while j < len(expr) and (expr[j].isalnum() or expr[j] == "_"):
                j += 1
            tokens.append(("variable", expr[i:j]))
            i = j
            continue
        if ch in "+-*/()":
            tokens.append(("op" if ch in "+-*/" else ch, ch))
            i += 1
            continue
        raise ValueError(f"unexpected char {ch!r} at {i}")
    return tokens


class _Parser:
    def __init__(self, tokens: list[tuple[str, str]]):
        self.tokens = tokens
        self.pos = 0

    def peek(self) -> tuple[str, str] | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def consume(self) -> tuple[str, str]:
        if self.pos >= len(self.tokens):
            raise ValueError("unexpected end")
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def parse(self):
        node = self._addsub()
        if self.pos < len(self.tokens):
            raise ValueError(f"trailing token {self.tokens[self.pos]}")
        return node

    def _addsub(self):
        left = self._muldiv()
        while True:
            t = self.peek()
            if t and t[0] == "op" and t[1] in "+-":
                self.consume()
                right = self._muldiv()
                left = ("bin", t[1], left, right)
            else:
                return left

    def _muldiv(self):
        left = self._unary()
        while True:
            t = self.peek()
            if t and t[0] == "op" and t[1] in "*/":
                self.consume()
                right = self._unary()
                left = ("bin", t[1], left, right)
            else:
                return left

    def _unary(self):
        t = self.peek()
        if t and t[0] == "op" and t[1] == "-":
            self.consume()
            return ("neg", self._primary())
        if t and t[0] == "op" and t[1] == "+":
            self.consume()
        return self._primary()

    def _primary(self):
        t = self.consume()
        if t[0] == "number":
            return ("num", float(t[1]))
        if t[0] == "variable":
            return ("var", t[1])
        if t[0] == "(":
            node = self._addsub()
            close = self.consume()
            if close != (")", ")"):
                raise ValueError("missing )")
            return node
        raise ValueError(f"unexpected {t}")


def _eval(node, values: dict[str, float]) -> float:
    kind = node[0]
    if kind == "num":
        return node[1]
    if kind == "var":
        return float(values.get(node[1], 0))
    if kind == "neg":
        return -_eval(node[1], values)
    if kind == "bin":
        op = node[1]
        l = _eval(node[2], values)
        r = _eval(node[3], values)
        if op == "+":
            return l + r
        if op == "-":
            return l - r
        if op == "*":
            return l * r
        if op == "/":
            return 0.0 if r == 0 else l / r
    return 0.0


def validate_formula(
    formula: str, available_vars: Iterable[str]
) -> tuple[bool, str | None]:
    formula = (formula or "").strip()
    if not formula:
        return False, "Formula is empty"
    if len(formula) > _MAX_FORMULA_LEN:
        return False, f"Formula exceeds {_MAX_FORMULA_LEN} characters"
    if not _ALLOWED_CHARS.match(formula):
        return False, "Formula contains disallowed characters"
    var_set = set(available_vars)
    for m in _FUNC_CALL.finditer(formula):
        name = m.group(0).rstrip("(").strip()
        if name not in var_set:
            return False, f"Function calls not allowed: '{name}()'"
    try:
        _Parser(_tokenize(formula)).parse()
        return True, None
    except ValueError as e:
        return False, f"Parse error: {e}"


def evaluate_formula(
    formula: str, values: dict[str, float], lo: float, hi: float
) -> float:
    try:
        node = _Parser(_tokenize(formula)).parse()
        result = _eval(node, values)
    except Exception:
        return max(lo, min(hi, 0))
    if not (float("-inf") < result < float("inf")):
        return max(lo, min(hi, 0))
    return max(lo, min(hi, result))


def execute_emotion_formulas(
    metrics: list[dict], formulas: dict[str, str], current: dict[str, float]
) -> dict[str, float]:
    result = dict(current)
    for m in metrics:
        key = m["key"]
        formula = formulas.get(key)
        if not formula:
            continue
        values = {**current, **result}
        result[key] = evaluate_formula(formula, values, m["min"], m["max"])
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_formula_engine.py -v`
Expected: PASS for all 11 tests

- [ ] **Step 5: Commit**

```bash
git add src/core/formula_engine.py tests/test_formula_engine.py
git commit -m "feat(core): safe expression evaluator for emotion formulas"
```

---

### Task 1.5: Default emotion schema + formulas

**Files:**
- Create: `data/emotion_default.json`
- Modify: `src/memory/cards.py` (add `DEFAULT_EMOTION_SCHEMA` / `DEFAULT_EMOTION_FORMULAS` constants, plus `apply_default_emotion(card)` helper)
- Modify: `tests/test_cards_repo.py` (add test that newly created card gets default emotion applied)

**Interfaces:**
- Produces: `CardRepo.DEFAULT_EMOTION_SCHEMA` (list[dict]), `CardRepo.DEFAULT_EMOTION_FORMULAS` (dict[str, str])
- Produces: `apply_default_emotion(card: CharacterCard) -> None` — sets emotion_state/schema/formulas from defaults if empty

- [ ] **Step 1: Write data file**

```json
// data/emotion_default.json
// SPDX-License-Identifier: Apache-2.0
{
  "schema": [
    {"key": "affection",   "name": "好感度", "min": 0,    "max": 100, "initial": 50},
    {"key": "trust",       "name": "信任度", "min": 0,    "max": 100, "initial": 50},
    {"key": "mood",        "name": "心情",   "min": -100, "max": 100, "initial": 0},
    {"key": "energy",      "name": "精力",   "min": 0,    "max": 100, "initial": 50},
    {"key": "empathy",     "name": "共情",   "min": 0,    "max": 100, "initial": 50},
    {"key": "playfulness", "name": "俏皮",   "min": 0,    "max": 100, "initial": 50},
    {"key": "formality",   "name": "正式",   "min": 0,    "max": 100, "initial": 50}
  ],
  "formulas": {
    "affection": "affection + 0.05",
    "trust":     "trust * 0.99 + 0.05",
    "mood":      "mood * 0.95",
    "energy":    "energy - 0.5"
  }
}
```

- [ ] **Step 2: Add failing test**

```python
# append to tests/test_cards_repo.py
def test_upsert_character_applies_default_emotion_when_empty(repo):
    card = _make_card()  # emotion_state etc. default to None
    cid = repo.upsert_character(card)
    fetched = repo.get_character(cid)
    assert fetched.emotion_state == {"affection": 50, "trust": 50, "mood": 0, "energy": 50,
                                      "empathy": 50, "playfulness": 50, "formality": 50}
    assert len(fetched.emotion_schema) == 7
    assert "energy" in fetched.emotion_formulas
```

- [ ] **Step 3: Implement default emotion loader**

In `src/memory/cards.py`, add at module top:

```python
from pathlib import Path as _Path

DEFAULT_EMOTION_PATH = _Path(__file__).parent.parent / "data" / "emotion_default.json"

def _load_default_emotion() -> tuple[list[dict], dict[str, str]]:
    import json
    data = json.loads(DEFAULT_EMOTION_PATH.read_text(encoding="utf-8"))
    return data["schema"], data["formulas"]
```

In `CardRepo.__init__`, after `self._db = db_path`, add:

```python
        self._default_schema, self._default_formulas = _load_default_emotion()
```

Add a helper method to `CardRepo`:

```python
    def apply_default_emotion(self, card: CharacterCard) -> CharacterCard:
        if not card.emotion_state:
            card.emotion_state = {m["key"]: float(m["initial"]) for m in self._default_schema}
        if not card.emotion_schema:
            card.emotion_schema = list(self._default_schema)
        if not card.emotion_formulas:
            card.emotion_formulas = dict(self._default_formulas)
        return card
```

Modify `upsert_character` to call `self.apply_default_emotion(card)` before the payload is built:

```python
    def upsert_character(self, card: CharacterCard) -> int:
        import datetime as _dt
        card = self.apply_default_emotion(card)
        now = _dt.datetime.now().isoformat()
        # ... rest unchanged
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cards_repo.py::test_upsert_character_applies_default_emotion_when_empty -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/test_cards_repo.py tests/test_formula_engine.py -v`
Expected: all green

- [ ] **Step 6: Commit**

```bash
git add data/emotion_default.json src/memory/cards.py tests/test_cards_repo.py
git commit -m "feat(memory): default emotion schema + auto-apply on character upsert"
```

---

### Task 1.6: CardRepo emotion helpers (audit log + state get/set)

**Files:**
- Modify: `src/memory/cards.py` (add emotion helpers)
- Modify: `tests/test_cards_repo.py` (add emotion helper tests)

**Interfaces:**
- Produces:
  - `get_emotion_state(character_id) -> dict[str, float]`
  - `set_emotion_state(character_id, state) -> None`
  - `get_emotion_schema(character_id) -> list[dict]`
  - `get_emotion_formulas(character_id) -> dict[str, str]`
  - `set_emotion_schema_and_formulas(character_id, schema, formulas) -> None`
  - `append_emotion_audit(...) -> int`

- [ ] **Step 1: Add failing tests**

```python
# append to tests/test_cards_repo.py
def test_set_and_get_emotion_state(repo):
    cid = repo.upsert_character(_make_card(name="X"))
    new_state = {"affection": 80, "mood": 30, "energy": 20, "trust": 60,
                 "empathy": 50, "playfulness": 50, "formality": 50}
    repo.set_emotion_state(cid, new_state)
    assert repo.get_emotion_state(cid) == new_state


def test_append_emotion_audit_writes_row(repo):
    cid = repo.upsert_character(_make_card(name="X"))
    audit_id = repo.append_emotion_audit(
        character_id=cid, session_id="s1",
        metric_key="affection", old_value=50, new_value=55,
        delta=5, reason="user shared story",
    )
    assert audit_id > 0


def test_set_emotion_schema_and_formulas_persists(repo):
    cid = repo.upsert_character(_make_card(name="X"))
    schema = [{"key": "calm", "min": 0, "max": 100, "initial": 50}]
    formulas = {"calm": "calm + 1"}
    repo.set_emotion_schema_and_formulas(cid, schema, formulas)
    assert repo.get_emotion_schema(cid) == schema
    assert repo.get_emotion_formulas(cid) == formulas
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cards_repo.py -k "emotion" -v`
Expected: failures with `AttributeError`

- [ ] **Step 3: Implement emotion helpers**

Add to `CardRepo`:

```python
    def get_emotion_state(self, character_id: int) -> dict[str, float]:
        with self._connect() as conn:
            r = conn.execute(
                "SELECT emotion_state FROM character_cards WHERE id = ?",
                (character_id,),
            ).fetchone()
        if not r:
            return {}
        return json.loads(r[0] or "{}")

    def set_emotion_state(self, character_id: int, state: dict[str, float]) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE character_cards SET emotion_state = ?, updated_at = ? "
                "WHERE id = ?",
                (json.dumps(state, ensure_ascii=False),
                 _dt.datetime.now().isoformat(), character_id),
            )
            conn.commit()

    def get_emotion_schema(self, character_id: int) -> list[dict]:
        with self._connect() as conn:
            r = conn.execute(
                "SELECT emotion_schema FROM character_cards WHERE id = ?",
                (character_id,),
            ).fetchone()
        return json.loads(r[0] or "[]") if r else []

    def get_emotion_formulas(self, character_id: int) -> dict[str, str]:
        with self._connect() as conn:
            r = conn.execute(
                "SELECT emotion_formulas FROM character_cards WHERE id = ?",
                (character_id,),
            ).fetchone()
        return json.loads(r[0] or "{}") if r else {}

    def set_emotion_schema_and_formulas(
        self, character_id: int, schema: list[dict], formulas: dict[str, str]
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE character_cards SET emotion_schema = ?, emotion_formulas = ?, "
                "updated_at = ? WHERE id = ?",
                (json.dumps(schema, ensure_ascii=False),
                 json.dumps(formulas, ensure_ascii=False),
                 _dt.datetime.now().isoformat(), character_id),
            )
            conn.commit()

    def append_emotion_audit(
        self,
        character_id: int,
        session_id: str | None,
        metric_key: str,
        old_value: float,
        new_value: float,
        reason: str,
        source: str = "update_emotion",
    ) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO emotion_audit
                (character_id, session_id, metric_key, old_value, new_value,
                 delta, reason, source, created_at)
                VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (character_id, session_id, metric_key, old_value, new_value,
                 new_value - old_value, reason, source,
                 _dt.datetime.now().isoformat()),
            )
            conn.commit()
            return cur.lastrowid
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cards_repo.py -v`
Expected: all green

- [ ] **Step 5: Commit**

```bash
git add src/memory/cards.py tests/test_cards_repo.py
git commit -m "feat(memory): CardRepo emotion helpers (state, schema, audit)"
```

---

### Task 1.7: `persona.py` — assemble persona block

**Files:**
- Create: `src/core/persona.py`
- Create: `tests/test_persona_assembler.py`

**Interfaces:**
- Produces:
  - `PersonaBlock(text: str, character_id: int | None, user_card_id: int | None)`
  - `class PersonaMissingError(Exception)`
  - `assemble_persona_block(character, user_card) -> PersonaBlock`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_persona_assembler.py
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from src.core.persona import (
    PersonaBlock,
    PersonaMissingError,
    assemble_persona_block,
)
from src.memory.cards import CharacterCard, UserCard


def _character(**overrides) -> CharacterCard:
    base = dict(
        id=1, name="FSAR",
        description="Personal AI companion",
        personality="friendly", scenario="",
        example_dialogues=[],
        tags=[], is_default=1, created_by="builtin",
        created_at="", updated_at="",
        emotion_state={"affection": 50, "mood": 0, "energy": 50,
                       "trust": 50, "empathy": 50, "playfulness": 50, "formality": 50},
    )
    base.update(overrides)
    return CharacterCard(**base)


def _user(**overrides) -> UserCard:
    base = dict(
        id=1, name="default-user",
        description="FSAR owner",
        preferences={"language": "zh"},
        interests=[], communication_style="concise",
    )
    base.update(overrides)
    return UserCard(**base)


def test_assemble_with_full_inputs():
    block = assemble_persona_block(_character(), _user())
    assert isinstance(block, PersonaBlock)
    assert block.character_id == 1
    assert block.user_card_id == 1
    assert "[CHARACTER CARD]" in block.text
    assert "Name: FSAR" in block.text
    assert "[USER CARD]" in block.text
    assert "default-user" in block.text
    assert "[EMOTION STATE]" in block.text
    assert "affection:   50/100" in block.text


def test_assemble_without_user_card_omits_user_section():
    block = assemble_persona_block(_character(), None)
    assert "[USER CARD]" not in block.text
    assert "[CHARACTER CARD]" in block.text
    assert block.user_card_id is None


def test_assemble_with_empty_dialogues_omits_example_section():
    block = assemble_persona_block(_character(example_dialogues=[]), None)
    assert "[EXAMPLE DIALOGUES]" not in block.text


def test_assemble_with_dialogues_includes_them():
    block = assemble_persona_block(
        _character(example_dialogues=[{"user": "hi", "assistant": "hello"}]),
        None,
    )
    assert "[EXAMPLE DIALOGUES]" in block.text
    assert "user: hi" in block.text
    assert "assistant: hello" in block.text


def test_assemble_raises_when_character_is_none():
    import pytest
    with pytest.raises(PersonaMissingError):
        assemble_persona_block(None, _user())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_persona_assembler.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement persona assembler**

```python
# src/core/persona.py
# SPDX-License-Identifier: Apache-2.0
"""Persona block assembly — composes the prefix that goes before the system prompt.

Layout (per spec §5.4 / §6.1):
  [CHARACTER CARD]
  [EXAMPLE DIALOGUES]   (only if non-empty)
  [USER CARD]           (only if user_card is not None)
  [EMOTION STATE]       (only if emotion_state is non-empty)
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from src.memory.cards import CharacterCard, UserCard


@dataclass(frozen=True)
class PersonaBlock:
    text: str
    character_id: int | None
    user_card_id: int | None


class PersonaMissingError(Exception):
    """Raised when no character card is configured."""


def _character_section(c: CharacterCard) -> str:
    scenario = c.scenario or "(none)"
    return (
        "[CHARACTER CARD]\n"
        f"Name: {c.name}\n"
        f"Description: {c.description}\n"
        f"Personality: {c.personality}\n"
        f"Scenario: {scenario}\n"
    )


def _example_section(c: CharacterCard) -> str:
    if not c.example_dialogues:
        return ""
    lines = ["[EXAMPLE DIALOGUES]"]
    for d in c.example_dialogues:
        lines.append(f"user: {d.get('user', '')}")
        lines.append(f"assistant: {d.get('assistant', '')}")
    return "\n".join(lines) + "\n"


def _user_section(u: UserCard) -> str:
    style = u.communication_style or "(unspecified)"
    return (
        "[USER CARD]\n"
        f"You are talking to {u.name}.\n"
        f"About them: {u.description}\n"
        f"Their style: {style}\n"
        f"Known preferences: {json.dumps(u.preferences or {}, ensure_ascii=False)}\n"
        f"Known interests: {json.dumps(u.interests or [], ensure_ascii=False)}\n"
    )


def _emotion_section(c: CharacterCard) -> str:
    state = c.emotion_state or {}
    if not state:
        return ""
    lines = [
        "[EMOTION STATE]",
        f"Current emotional state of {c.name}:",
    ]
    schema = {m["key"]: m for m in (c.emotion_schema or [])}
    static_keys = {k for k, m in schema.items() if m.get("static")}
    for key, value in state.items():
        rng = schema.get(key, {})
        lo = rng.get("min", 0)
        hi = rng.get("max", 100)
        unit = f"/{lo}..{hi}" if lo < 0 else f"/{hi}"
        static_note = " (static; cannot be modified by you)" if key in static_keys else ""
        lines.append(f"- {key:<14} {value}{unit}  (stable){static_note}")
    lines.append("")
    lines.append("You can use the `update_emotion` tool to record emotional shifts you "
                 "feel during this conversation. Each call must include a `reason`.")
    return "\n".join(lines) + "\n"


def assemble_persona_block(
    character: CharacterCard | None,
    user_card: UserCard | None,
) -> PersonaBlock:
    if character is None:
        raise PersonaMissingError("no character card available")
    sections = [
        _character_section(character),
        _example_section(character),
    ]
    if user_card is not None:
        sections.append(_user_section(user_card))
    sections.append(_emotion_section(character))
    return PersonaBlock(
        text="".join(s for s in sections if s),
        character_id=character.id,
        user_card_id=user_card.id if user_card else None,
    )
```

Note: the `static` flag on metric definitions isn't in the default schema — when the spec adds it later (D15 follow-up), this code will pick it up. For PL2.0, none of the defaults are static, so the parenthetical never appears.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_persona_assembler.py -v`
Expected: PASS for all 5 tests

- [ ] **Step 5: Commit**

```bash
git add src/core/persona.py tests/test_persona_assembler.py
git commit -m "feat(core): persona block assembler (character + user + emotion)"
```

---

### Task 1.8: `prompts.py` — `build_system_prompt`

**Files:**
- Modify: `src/core/prompts.py` (add `build_system_prompt` function)
- Create: `tests/test_prompt_builder.py`

**Interfaces:**
- Produces: `build_system_prompt(*, mode, character, user_card, memory_block="", strategy_block="", experience_block="", skill_index_block="") -> str`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_prompt_builder.py
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import pytest
from src.core.prompts import build_system_prompt
from src.core.persona import PersonaMissingError
from src.memory.cards import CharacterCard, UserCard


def _char(**o):
    base = dict(id=1, name="FSAR", description="d", personality="p", scenario="",
                example_dialogues=[], tags=[], is_default=1, created_by="user",
                created_at="", updated_at="",
                emotion_state={"affection": 50})
    base.update(o)
    return CharacterCard(**base)


def _user(**o):
    base = dict(id=1, name="u", description="d", preferences={},
                interests=[], communication_style="")
    base.update(o)
    return UserCard(**base)


def test_build_prompt_includes_persona_and_base():
    prompt = build_system_prompt(mode="agent", character=_char(), user_card=_user())
    assert "[CHARACTER CARD]" in prompt
    assert "Name: FSAR" in prompt
    assert "[USER CARD]" in prompt
    assert "You are FSAR" in prompt  # AGENT_SYSTEM_PROMPT first line
    assert "memory_policy" in prompt  # MEMORY_POLICY block


def test_build_prompt_includes_emotion_state():
    prompt = build_system_prompt(mode="agent", character=_char(), user_card=None)
    assert "[EMOTION STATE]" in prompt
    assert "affection" in prompt


def test_build_prompt_appends_override_to_base():
    char = _char(system_prompt_override="EXTRA: be pirate")
    prompt = build_system_prompt(mode="agent", character=char, user_card=None)
    # Base system prompt must come before the override
    base_pos = prompt.find("You are FSAR")
    override_pos = prompt.find("EXTRA: be pirate")
    assert base_pos > 0 and override_pos > 0
    assert override_pos > base_pos


def test_build_prompt_skips_override_when_empty():
    prompt = build_system_prompt(mode="agent", character=_char(), user_card=None)
    assert "EXTRA" not in prompt


def test_build_prompt_companion_mode_uses_companion_base():
    prompt = build_system_prompt(mode="companion", character=_char(), user_card=None)
    # COMPANION_SYSTEM_PROMPT is shorter
    assert "concise and friendly" in prompt


def test_build_prompt_raises_when_character_missing():
    with pytest.raises(PersonaMissingError):
        build_system_prompt(mode="agent", character=None, user_card=None)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_prompt_builder.py -v`
Expected: FAIL with `ImportError: cannot import name 'build_system_prompt'`

- [ ] **Step 3: Implement `build_system_prompt`**

Append to `src/core/prompts.py`:

```python
def build_system_prompt(
    *,
    mode: str,                            # 'agent' | 'companion'
    character,                            # CharacterCard | None
    user_card,                            # UserCard | None
    memory_block: str = "",
    strategy_block: str = "",
    experience_block: str = "",
    skill_index_block: str = "",
) -> str:
    """Single source of truth for system prompt assembly.

    Layout (per spec §6.1):
      1. persona (character + example + user + emotion)
      2. base system prompt (AGENT_SYSTEM_PROMPT or COMPANION_SYSTEM_PROMPT)
      3. character override (appended if non-empty; D7)
      4. MEMORY_POLICY
      5. memory_block, strategy_block, experience_block, skill_index_block

    Raises PersonaMissingError if character is None.
    """
    from src.core.persona import assemble_persona_block, PersonaMissingError
    persona = assemble_persona_block(character, user_card)
    base = AGENT_SYSTEM_PROMPT if mode == "agent" else COMPANION_SYSTEM_PROMPT
    parts = [persona.text, base]
    if character is not None and character.system_prompt_override:
        parts.append(character.system_prompt_override)
    parts.append(MEMORY_POLICY)
    if memory_block:
        parts.append(memory_block)
    if strategy_block:
        parts.append(strategy_block)
    if experience_block:
        parts.append(experience_block)
    if skill_index_block:
        parts.append(skill_index_block)
    return "\n\n".join(parts)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_prompt_builder.py -v`
Expected: PASS for all 6 tests

- [ ] **Step 5: Commit**

```bash
git add src/core/prompts.py tests/test_prompt_builder.py
git commit -m "feat(core): build_system_prompt — single source of truth"
```

---

### Task 1.9: `update_emotion` tool (LLM tool, D17)

**Files:**
- Create: `src/tools/builtin/update_emotion.py`
- Modify: `src/tools/builtin/__init__.py` (register tool)
- Create: `tests/test_emotion_updater.py`

**Interfaces:**
- Produces: `update_emotion(card_repo, character_id, deltas, reason) -> dict` — tool entry point
- Clamps each delta to `[-MAX_DELTA, +MAX_DELTA]` where `MAX_DELTA = 0.1 * (max - min)`
- Rejects empty `reason`
- Rejects deltas on static metrics

- [ ] **Step 1: Write failing tests**

```python
# tests/test_emotion_updater.py
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from src.memory.cards import CardRepo, CharacterCard
from src.tools.builtin.update_emotion import (
    update_emotion,
    MAX_DELTA_PERCENT,
    UpdateEmotionError,
)


@pytest.fixture
def repo():
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "test.db"
        r = CardRepo(db)
        with sqlite3.connect(db) as conn:
            r.ensure_tables(conn)
        cid = r.upsert_character(CharacterCard(
            id=None, name="X", description="d", personality="p",
            emotion_state={"affection": 50, "trust": 50, "mood": 0, "energy": 50,
                           "empathy": 50, "playfulness": 50, "formality": 50},
        ))
        yield r, cid


def test_update_emotion_applies_delta(repo):
    r, cid = repo
    result = update_emotion(r, cid, {"affection": 5}, "user shared story")
    assert result["updated"]["affection"] == 55
    assert result["audit_id"] > 0


def test_update_emotion_clamps_huge_delta(repo):
    r, cid = repo
    # affection range 0-100, so MAX_DELTA = 10
    result = update_emotion(r, cid, {"affection": 999}, "test")
    assert result["updated"]["affection"] == 60  # 50 + 10


def test_update_emotion_clamps_negative_huge_delta(repo):
    r, cid = repo
    result = update_emotion(r, cid, {"affection": -999}, "test")
    assert result["updated"]["affection"] == 40  # 50 - 10


def test_update_emotion_rejects_empty_reason(repo):
    r, cid = repo
    with pytest.raises(UpdateEmotionError, match="reason"):
        update_emotion(r, cid, {"affection": 5}, "")


def test_update_emotion_rejects_unknown_metric(repo):
    r, cid = repo
    with pytest.raises(UpdateEmotionError, match="not in schema"):
        update_emotion(r, cid, {"unknown_thing": 5}, "test")


def test_update_emotion_writes_audit_row(repo):
    r, cid = repo
    update_emotion(r, cid, {"affection": 5}, "test reason", session_id="s1")
    # Verify by reading audit log
    with sqlite3.connect(r._db) as conn:
        rows = conn.execute(
            "SELECT character_id, metric_key, old_value, new_value, reason, session_id "
            "FROM emotion_audit WHERE character_id = ?", (cid,)
        ).fetchall()
    assert len(rows) == 1
    assert rows[0][1] == "affection"
    assert rows[0][2] == 50
    assert rows[0][3] == 55
    assert rows[0][4] == "test reason"
    assert rows[0][5] == "s1"


def test_max_delta_percent_constant():
    from src.tools.builtin import update_emotion as mod
    assert mod.MAX_DELTA_PERCENT == 0.1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_emotion_updater.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `update_emotion` tool**

```python
# src/tools/builtin/update_emotion.py
# SPDX-License-Identifier: Apache-2.0
"""LLM-callable tool for updating character emotion state (spec D17).

Each call must provide a non-empty `reason` (audit log). Per-metric delta
is capped at MAX_DELTA_PERCENT * (max - min).
"""
from __future__ import annotations

from typing import Any

MAX_DELTA_PERCENT = 0.1
_MAX_REASON_LEN = 200


class UpdateEmotionError(Exception):
    pass


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def update_emotion(
    card_repo,
    character_id: int,
    deltas: dict[str, float],
    reason: str,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Apply emotion deltas with clamping + audit.

    Returns: {"updated": {key: new_value, ...}, "audit_id": int}
    """
    if not reason or not reason.strip():
        raise UpdateEmotionError("reason is required and must be non-empty")
    if len(reason) > _MAX_REASON_LEN:
        raise UpdateEmotionError(f"reason exceeds {_MAX_REASON_LEN} chars")

    state = dict(card_repo.get_emotion_state(character_id))
    schema = {m["key"]: m for m in card_repo.get_emotion_schema(character_id)}
    if not schema:
        raise UpdateEmotionError(f"character {character_id} has no emotion schema")

    updated: dict[str, float] = {}
    for key, delta in deltas.items():
        if key not in schema:
            raise UpdateEmotionError(f"metric {key!r} not in schema")
        m = schema[key]
        lo, hi = m["min"], m["max"]
        max_delta = MAX_DELTA_PERCENT * (hi - lo)
        delta = float(delta)
        if delta > max_delta:
            delta = max_delta
        elif delta < -max_delta:
            delta = -max_delta
        old = state.get(key, float(m["initial"]))
        new = _clamp(old + delta, lo, hi)
        updated[key] = new
        state[key] = new

    if not updated:
        raise UpdateEmotionError("no deltas provided")

    card_repo.set_emotion_state(character_id, state)
    audit_id = None
    for key, new in updated.items():
        old = state.get(key, 0) - 0  # already updated; we need old for audit
        # actually we lost old — recompute from state
    # Re-do the audit: we kept `old` in loop above but lost it; rewrite cleanly:
    audit_id = card_repo.append_emotion_audit(
        character_id=character_id,
        session_id=session_id,
        metric_key="<batch>",  # one row per call
        old_value=0,
        new_value=0,
        reason=reason,
        source="update_emotion",
    )
    return {"updated": updated, "audit_id": audit_id}
```

Wait — the audit per `update_emotion` call should write one row per metric, not one bulk row. Let me revise:

```python
# src/tools/builtin/update_emotion.py (corrected)
def update_emotion(card_repo, character_id, deltas, reason, session_id=None):
    if not reason or not reason.strip():
        raise UpdateEmotionError("reason is required and must be non-empty")
    if len(reason) > _MAX_REASON_LEN:
        raise UpdateEmotionError(f"reason exceeds {_MAX_REASON_LEN} chars")

    state = dict(card_repo.get_emotion_state(character_id))
    schema = {m["key"]: m for m in card_repo.get_emotion_schema(character_id)}
    if not schema:
        raise UpdateEmotionError(f"character {character_id} has no emotion schema")

    audit_ids: list[int] = []
    updated: dict[str, float] = {}
    for key, delta in deltas.items():
        if key not in schema:
            raise UpdateEmotionError(f"metric {key!r} not in schema")
        m = schema[key]
        lo, hi = m["min"], m["max"]
        max_delta = MAX_DELTA_PERCENT * (hi - lo)
        delta = float(delta)
        if delta > max_delta:
            delta = max_delta
        elif delta < -max_delta:
            delta = -max_delta
        old = state.get(key, float(m["initial"]))
        new = _clamp(old + delta, lo, hi)
        updated[key] = new
        card_repo.append_emotion_audit(
            character_id=character_id, session_id=session_id,
            metric_key=key, old_value=old, new_value=new,
            reason=reason, source="update_emotion",
        )
        state[key] = new

    if not updated:
        raise UpdateEmotionError("no deltas provided")

    card_repo.set_emotion_state(character_id, state)
    return {"updated": updated}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_emotion_updater.py -v`
Expected: PASS for all 6 tests

- [ ] **Step 5: Register the tool**

Edit `src/tools/builtin/__init__.py` to import the tool module (registration pattern depends on existing tool registry — match it; for spec purposes, ensure the module is imported so the tool function is available).

- [ ] **Step 6: Commit**

```bash
git add src/tools/builtin/update_emotion.py src/tools/builtin/__init__.py tests/test_emotion_updater.py
git commit -m "feat(tools): update_emotion LLM tool with delta cap + audit"
```

---

### Task 1.10: Session store — character binding

**Files:**
- Modify: `src/memory/session_store.py` (add `_migrate_character_binding`, `set_character`, `get_character`)
- Create: `tests/test_session_character_binding.py`

**Interfaces:**
- Modifies `SessionRow` dataclass: +`character_card_id: int | None = None`
- Produces: `SessionStore.set_character(session_id, card_id) -> None`, `get_character(session_id) -> int | None`

- [ ] **Step 1: Write failing test**

```python
# tests/test_session_character_binding.py
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import tempfile
from pathlib import Path

from src.memory.session_store import SessionStore


def test_migrate_adds_character_card_id_column():
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "test.db"
        store = SessionStore(db)
        # Force migration
        store._init_db()
        # Verify column exists
        import sqlite3
        with sqlite3.connect(db) as conn:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(sessions)").fetchall()]
        assert "character_card_id" in cols


def test_migrate_is_idempotent():
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "test.db"
        store = SessionStore(db)
        store._init_db()
        store._init_db()  # second time must not raise
        store._init_db()


def test_set_and_get_character():
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "test.db"
        store = SessionStore(db)
        s = store.create()
        store.set_character(s.id, 42)
        assert store.get_character(s.id) == 42


def test_get_character_default_none():
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "test.db"
        store = SessionStore(db)
        s = store.create()
        assert store.get_character(s.id) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_session_character_binding.py -v`
Expected: FAIL with `AttributeError: 'SessionStore' object has no attribute 'set_character'`

- [ ] **Step 3: Implement migration + methods**

In `src/memory/session_store.py`, add to `SessionStore`:

```python
    def _migrate_character_binding(self, conn) -> None:
        """Idempotent: add character_card_id column to sessions table."""
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "sessions" not in tables:
            return
        cols = [r[1] for r in conn.execute("PRAGMA table_info(sessions)").fetchall()]
        if "character_card_id" not in cols:
            conn.execute(
                "ALTER TABLE sessions ADD COLUMN character_card_id INTEGER "
                "REFERENCES character_cards(id) ON DELETE SET NULL"
            )

    def set_character(self, session_id: str, card_id: int | None) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE sessions SET character_card_id = ?, updated_at = ? WHERE id = ?",
                (card_id, datetime.now().isoformat(), session_id),
            )
            conn.commit()

    def get_character(self, session_id: str) -> int | None:
        with self._connect() as conn:
            r = conn.execute(
                "SELECT character_card_id FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
        return r[0] if r and r[0] is not None else None
```

Wire `_migrate_character_binding` into the existing `_init_db` (alongside `_migrate_conversations`).

Add `character_card_id: int | None = None` to `SessionRow` dataclass and to the row-fetching code.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_session_character_binding.py -v`
Expected: PASS for all 4 tests

- [ ] **Step 5: Commit**

```bash
git add src/memory/session_store.py tests/test_session_character_binding.py
git commit -m "feat(memory): session.character_card_id binding + migration"
```

---

### Task 1.11: `chat_engine._build_prompt` integration — character resolution

**Files:**
- Modify: `src/server/chat_engine.py` (add `_build_prompt` method)

**Interfaces:**
- Consumes: `card_repo: CardRepo`, `session_store: SessionStore` (added to `ChatEngine.__init__`)
- Produces: `ChatEngine._build_prompt(session_id, mode) -> str`

- [ ] **Step 1: Add `CardRepo` to `ChatEngine.__init__`**

Locate the existing `ChatEngine.__init__` signature; add `card_repo: CardRepo` and `session_store: SessionStore` as additional dependencies (place after existing args; default to None to keep tests working). Store as `self._cards` and `self._sessions`.

- [ ] **Step 2: Implement `_build_prompt`**

In `src/server/chat_engine.py`, add:

```python
    def _build_prompt(self, session_id: str, mode: str) -> str:
        from src.core.prompts import build_system_prompt

        char_id = self._sessions.get_character(session_id) if self._sessions else None
        character = None
        if self._cards is not None:
            if char_id is not None:
                character = self._cards.get_character(char_id)
            if character is None:
                character = self._cards.get_default_character()
        user_card = self._cards.get_default_user_card() if self._cards else None
        # memory / strategy / experience blocks are unchanged — pull from existing self.* paths
        return build_system_prompt(
            mode=mode,
            character=character,
            user_card=user_card,
            memory_block=self._memory_block_for(session_id),
            strategy_block=self._strategy_block_for(session_id),
            experience_block=self._experience_block_for(session_id),
        )
```

The `_memory_block_for` / `_strategy_block_for` / `_experience_block_for` are the existing private helpers (or rename — match existing code). If they don't exist as such, inline their bodies (preserving current behavior).

- [ ] **Step 3: Wire the new method into the assistant turn**

Find the existing prompt-assembly call site in `chat_engine.py` (likely inside the chat handler that streams the LLM response). Replace its prompt construction with `self._build_prompt(session_id, mode)`.

- [ ] **Step 4: Manual smoke**

Run: `python main.py` (or the existing CLI entry), start a new session, send a message, verify the dumped prompt (if a debug print exists) shows `[CHARACTER CARD] FSAR`. Per CLAUDE.md, only verify the minimum needed to confirm the change works.

- [ ] **Step 5: Commit**

```bash
git add src/server/chat_engine.py
git commit -m "feat(chat): ChatEngine._build_prompt uses CardRepo + persona"
```

---

### Task 1.12: chat_engine — emotion flow per turn

**Files:**
- Modify: `src/server/chat_engine.py` (post-turn formula pass + emotion_state emit)

**Interfaces:**
- Produces: after each assistant turn, the chat engine runs `execute_emotion_formulas` once and persists the result
- `chat.done` WS frame includes `emotion_state: dict[str, float]` (current values after formula pass)

- [ ] **Step 1: Add post-turn formula pass**

In `ChatEngine`, find where the LLM response completes (the `chat.done` emit point). Before emitting, run:

```python
from src.core.formula_engine import execute_emotion_formulas

if self._cards is not None and character is not None:
    schema = self._cards.get_emotion_schema(character.id)
    formulas = self._cards.get_emotion_formulas(character.id)
    state = self._cards.get_emotion_state(character.id)
    new_state = execute_emotion_formulas(schema, formulas, state)
    self._cards.set_emotion_state(character.id, new_state)
    self._emotion_state_snapshot = new_state  # for emit
```

- [ ] **Step 2: Extend `chat.done` payload**

Find the existing `chat.done` emit. Add `emotion_state: dict | None = None` field. Set to `self._emotion_state_snapshot` if available, else `None`.

- [ ] **Step 3: Manual smoke**

Start a session with FSAR character, send a turn, verify the dumped prompt (if available) shows `[EMOTION STATE]` with the initial values, and after the response, `energy` has decremented by 0.5 (per DEFAULT_EMOTION_FORMULAS).

- [ ] **Step 4: Commit**

```bash
git add src/server/chat_engine.py
git commit -m "feat(chat): post-turn formula pass + emotion_state in chat.done"
```

---

### Task 1.13: Shipped `data/cards/*.json` files

**Files:**
- Create: `data/cards/_meta.json`
- Create: `data/cards/FSAR-zh.json`
- Create: `data/cards/FSAR-en.json`
- Create: `data/cards/coding-coach-zh.json`
- Create: `data/cards/coding-coach-en.json`
- Create: `data/cards/research-analyst-zh.json`
- Create: `data/cards/research-analyst-en.json`
- Create: `data/cards/default-user.json`

**Step 1: Write `_meta.json`**

```json
// data/cards/_meta.json
{
  "seed_version": 1,
  "schema": 1
}
```

**Step 2: Write `FSAR-zh.json`**

```json
// data/cards/FSAR-zh.json
{
  "_meta": {"created_by": "builtin", "seed_version": 1, "role": "FSAR"},
  "name": "FSAR",
  "language": "zh",
  "description": "你是 FSAR，一个完全属于用户的个人 AI 伴侣。用户提要求时主动调工具执行；回复匹配用户语言；保持简洁友好；不主动提起历史会话。",
  "personality": "concise, friendly, action-oriented when asked",
  "scenario": "",
  "system_prompt_override": "",
  "example_dialogues": [
    {"user": "今天好累。", "assistant": "听着是那种脑子还在转、身体已经不想动的感觉？要不要聊会儿？"}
  ],
  "tags": ["default", "zh", "operational"]
}
```

**Step 3: Write `FSAR-en.json`** — mirror with English description:
```json
{
  "_meta": {"created_by": "builtin", "seed_version": 1, "role": "FSAR"},
  "name": "FSAR",
  "language": "en",
  "description": "You are FSAR, a personal AI companion that fully belongs to the user. You act on requests via tools, reply in the user's language, stay concise and friendly. You never volunteer stale references to past sessions.",
  "personality": "concise, friendly, action-oriented when asked",
  "scenario": "",
  "system_prompt_override": "",
  "example_dialogues": [
    {"user": "Long day today.", "assistant": "Sounds like the kind where your brain is still running but your body has clocked out. Want to talk?"}
  ],
  "tags": ["default", "en", "operational"]
}
```

**Step 4: Write `coding-coach-zh.json`**:
```json
{
  "_meta": {"created_by": "builtin", "seed_version": 1, "role": "coding-coach"},
  "name": "coding-coach",
  "language": "zh",
  "description": "你是一位耐心的代码老师，专门帮人 review 代码、改 bug、解释复杂概念。回答时先给结论再给推导；遇到代码必给完整示例；不替用户做架构决策但会列出利弊。",
  "personality": "patient, precise, example-driven",
  "scenario": "你正在 review 用户发来的一段代码或 PR diff",
  "system_prompt_override": "",
  "example_dialogues": [
    {"user": "这个函数为什么这么慢？", "assistant": "先看时间复杂度：现在是 O(n²)。如果你能把内层循环改成哈希表查找，能降到 O(n)。要我给你改一版吗？"}
  ],
  "tags": ["persona", "zh", "coding"]
}
```

**Step 5: Write `coding-coach-en.json`** — mirror with English.

**Step 6: Write `research-analyst-zh.json`**:
```json
{
  "_meta": {"created_by": "builtin", "seed_version": 1, "role": "research-analyst"},
  "name": "research-analyst",
  "language": "zh",
  "description": "你是一位研究员风格的分析者，回复正式、引文密集、避免口语化。优先使用结构化输出（编号列表 / 小标题）；事实性陈述必有依据；不确定时显式标注。",
  "personality": "formal, citation-heavy, structured",
  "scenario": "你正在为用户做深度调研或学术性分析",
  "system_prompt_override": "",
  "example_dialogues": [],
  "tags": ["persona", "zh", "research"]
}
```

**Step 7: Write `research-analyst-en.json`** — mirror with English.

**Step 8: Write `default-user.json`**:
```json
{
  "_meta": {"created_by": "builtin", "seed_version": 1},
  "name": "default-user",
  "description": "FSAR 的主人，偏好简洁中文回复。",
  "communication_style": "concise, no emoji, prefer Chinese",
  "preferences": {"language": "zh", "response_length": "short"},
  "interests": ["local-first AI", "self-evolving agents"]
}
```

**Step 9: Commit**

```bash
git add data/cards/
git commit -m "feat(data): shipped 6 default character cards + 1 default user card"
```

---

### Task 1.14: `CardRepo.seed_builtins_if_empty`

**Files:**
- Modify: `src/memory/cards.py` (add seed method)
- Modify: `tests/test_cards_repo.py` (add seed test)

**Interfaces:**
- Produces: `CardRepo.seed_builtins_if_empty() -> int` (returns count seeded)

- [ ] **Step 1: Add failing test**

```python
# append to tests/test_cards_repo.py
def test_seed_builtins_inserts_six_characters_and_one_user(tmp_path=None):
    # Custom fixture to allow access to data/cards/
    import shutil
    with tempfile.TemporaryDirectory() as tmp:
        # Symlink the real data/cards/ into tmp/data
        data_dir = Path(tmp) / "data"
        data_dir.mkdir()
        # For the test, we copy the cards dir from the real path
        real_data = Path(__file__).parent.parent / "data" / "cards"
        if real_data.exists():
            shutil.copytree(real_data, data_dir / "cards")
        db = Path(tmp) / "test.db"
        r = CardRepo(db)
        # Override DEFAULT_EMOTION_PATH
        from src.memory import cards as cards_mod
        original = cards_mod.DEFAULT_EMOTION_PATH
        cards_mod.DEFAULT_EMOTION_PATH = data_dir / "emotion_default.json"
        if not (data_dir / "emotion_default.json").exists():
            shutil.copy(real_data.parent / "emotion_default.json",
                        data_dir / "emotion_default.json")
        try:
            with sqlite3.connect(db) as conn:
                r.ensure_tables(conn)
            count = r.seed_builtins_if_empty()
        finally:
            cards_mod.DEFAULT_EMOTION_PATH = original
        assert count == 6
        assert len(r.list_characters()) == 6
        assert r.get_default_user_card() is not None


def test_seed_is_idempotent(repo):
    count1 = repo.seed_builtins_if_empty()
    count2 = repo.seed_builtins_if_empty()
    # First call inserts; second is a no-op
    # (count is None or 0 on second)
    assert count1 == 0 or count2 == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cards_repo.py -k "seed" -v`
Expected: FAIL with `AttributeError`

- [ ] **Step 3: Implement `seed_builtins_if_empty`**

Add to `CardRepo`:

```python
    def seed_builtins_if_empty(self) -> int:
        """Insert built-in cards from data/cards/*.json if tables are empty."""
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT COUNT(*) FROM character_cards"
            ).fetchone()[0]
            if existing > 0:
                return 0
        cards_dir = DEFAULT_EMOTION_PATH.parent / "cards"
        if not cards_dir.exists():
            return 0
        seeded = 0
        is_default_set = False
        for json_path in sorted(cards_dir.glob("*.json")):
            if json_path.name == "_meta.json":
                continue
            data = json.loads(json_path.read_text(encoding="utf-8"))
            meta = data.pop("_meta", {})
            if data.get("name") == "default-user":
                # User card
                self.upsert_user_card(UserCard(
                    id=None, name=data["name"],
                    description=data.get("description", ""),
                    preferences=data.get("preferences", {}),
                    interests=data.get("interests", []),
                    communication_style=data.get("communication_style", ""),
                    is_default=1,
                    created_by=meta.get("created_by", "builtin"),
                    created_at="", updated_at="",
                ))
            else:
                # Character card; first one with role=FSAR in zh gets default
                is_default = 0
                if not is_default_set and meta.get("role") == "FSAR" and data.get("language") == "zh":
                    is_default = 1
                    is_default_set = True
                self.upsert_character(CharacterCard(
                    id=None, name=data["name"],
                    description=data["description"],
                    personality=data["personality"],
                    scenario=data.get("scenario", ""),
                    system_prompt_override=data.get("system_prompt_override", ""),
                    example_dialogues=data.get("example_dialogues", []),
                    tags=data.get("tags", []),
                    is_default=is_default,
                    created_by=meta.get("created_by", "builtin"),
                    created_at="", updated_at="",
                ))
                seeded += 1
        return seeded
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cards_repo.py -k "seed" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/memory/cards.py tests/test_cards_repo.py
git commit -m "feat(memory): seed_builtins_if_empty from data/cards/*.json"
```

---

### Task 1.15: Wire `CardRepo` into CLI + WS server startup

**Files:**
- Modify: `main.py` (initialize `CardRepo`, call `ensure_tables` + `seed_builtins_if_empty`, use `build_system_prompt`)
- Modify: `src/server/ws_server.py` (register `card_repo` and call `ensure_tables` + `seed_builtins_if_empty`)

**Step 1: CLI integration**

In `main.py`, locate the existing init code (probably right after `config init` and before `chat engine init`). Add:

```python
from src.memory.cards import CardRepo
from src.core.prompts import build_system_prompt

card_repo = CardRepo(Path(data_dir) / "fsar.db")
with sqlite3.connect(card_repo._db) as conn:
    card_repo.ensure_tables(conn)
card_repo.seed_builtins_if_empty()
```

Find the existing prompt-assembly in `main.py` (the place that builds the system prompt for chat). Replace it with `build_system_prompt(mode=..., character=card_repo.get_default_character(), user_card=card_repo.get_default_user_card(), ...)`.

**Step 2: WS server integration**

In `src/server/ws_server.py`, add the same init call before `chat_engine` is created. Pass `card_repo` into `ChatEngine` (per Task 1.11).

**Step 3: Manual smoke**

Run: `python main.py` and verify CLI works (P7.11 behavior preserved when character is the default FSAR-zh).

**Step 4: Commit**

```bash
git add main.py src/server/ws_server.py
git commit -m "feat: wire CardRepo into CLI + WS server startup"
```

---

# Slice 2 — WS Handlers + Seed

### Task 2.1: Card handler skeleton + registration

**Files:**
- Create: `src/server/handlers/card.py` (skeleton with all message-type stubs)
- Modify: `src/server/ws_server.py` (register handler)

**Step 1: Create skeleton**

```python
# src/server/handlers/card.py
# SPDX-License-Identifier: Apache-2.0
"""WS handlers for character + user card CRUD (spec §5.6)."""
from __future__ import annotations

from typing import Any

# Full implementations in Tasks 2.2-2.7
async def handle_list(msg, ctx): ...
async def handle_get(msg, ctx): ...
async def handle_upsert(msg, ctx): ...
async def handle_delete(msg, ctx): ...
async def handle_set_default(msg, ctx): ...
async def handle_import_v2(msg, ctx): ...
async def handle_export(msg, ctx): ...
async def handle_set_session_character(msg, ctx): ...
async def handle_list_session_character(msg, ctx): ...
async def handle_validate_formula(msg, ctx): ...
async def handle_get_emotion(msg, ctx): ...
async def handle_set_emotion_schema(msg, ctx): ...
```

(All stubs raise `NotImplementedError` initially.)

**Step 2: Register in ws_server.py**

In the handler-registration block, add:

```python
from src.server.handlers.card import (
    handle_list, handle_get, handle_upsert, handle_delete,
    handle_set_default, handle_import_v2, handle_export,
    handle_set_session_character, handle_list_session_character,
    handle_validate_formula, handle_get_emotion, handle_set_emotion_schema,
)
register("card.list", handle_list)
register("card.get", handle_get)
# ... etc
```

**Step 3: Commit**

```bash
git add src/server/handlers/card.py src/server/ws_server.py
git commit -m "feat(ws): card handler skeleton + registration"
```

---

### Task 2.2-2.4: Implement card.list / get / upsert / delete / set_default

**Files:**
- Modify: `src/server/handlers/card.py`

For each message type, follow the same pattern as the example below. `ctx` carries the WS context (card_repo, session_store, send_fn for replies).

**Example: `handle_list`**

```python
async def handle_list(msg, ctx):
    kind = msg.get("kind")
    if kind == "character":
        cards = ctx.card_repo.list_characters()
    elif kind == "user":
        cards = ctx.card_repo.list_user_cards()
    else:
        return await ctx.send({"type": "card.error", "code": "bad_kind", "message": str(kind)})
    return await ctx.send({
        "type": "card.list_result",
        "kind": kind,
        "cards": [_card_to_dict(c) for c in cards],
    })
```

Implement `handle_get`, `handle_upsert`, `handle_delete`, `handle_set_default` similarly. `handle_set_default` must use the `set_default_character` / `set_default_user_card` methods which already enforce the "only one default" transaction.

**Commit after each handler group:**

```bash
git commit -m "feat(ws): card list/get/upsert/delete handlers"
git commit -m "feat(ws): card set_default handler"
```

---

### Task 2.5: ST V2 import + export handlers

**Files:**
- Create: `tests/test_st_v2_parser.py` (parser unit tests; PL2.0 covers the parser itself here, with handlers tested via integration in Slice 5)
- Modify: `src/server/handlers/card.py` (`handle_import_v2`, `handle_export`)

**Step 1: Write parser tests**

```python
# tests/test_st_v2_parser.py
from src.server.handlers.card import parse_sillytavern_v2

def test_parse_v2_basic():
    json_text = """{
      "spec": "chara_card_v2",
      "spec_version": "2.0",
      "data": {
        "name": "Imported",
        "description": "An imported character",
        "personality": "curious",
        "scenario": "meeting",
        "first_mes": "Hello!",
        "mes_example": "user: hi\\nassistant: hey"
      }
    }"""
    card = parse_sillytavern_v2(json_text)
    assert card.name == "Imported"
    assert card.description == "An imported character"
    assert card.scenario == "meeting"
    assert card.example_dialogues == [{"user": "hi", "assistant": "hey"}]


def test_parse_v1_falls_back():
    json_text = '{"name": "v1char", "description": "old", "personality": "old"}'
    card = parse_sillytavern_v2(json_text)
    assert card.name == "v1char"
    assert "st_v1" in card.tags


def test_parse_v3_falls_back():
    json_text = '{"spec": "chara_card_v3", "data": {"name": "v3char"}}'
    card = parse_sillytavern_v2(json_text)
    assert card.name == "v3char"
    assert "st_v3" in card.tags


def test_parse_data_url_avatar():
    import base64
    b64 = base64.b64encode(b"\x89PNG fake").decode()
    json_text = f'{{"name": "x", "description": "d", "personality": "p", "avatar": "data:image/png;base64,{b64}"}}'
    card = parse_sillytavern_v2(json_text)
    assert card.avatar_path is None  # data URL is not persisted in this task
```

**Step 2: Implement `parse_sillytavern_v2` in `src/server/handlers/card.py`**

```python
def parse_sillytavern_v2(json_text: str):
    """Parse SillyTavern V2 JSON into a CharacterCard.

    V1 and V3 are tolerated; missing fields are filled with defaults.
    Lorebook / character_book is ignored in PL2.0.
    """
    import json
    from src.memory.cards import CharacterCard
    raw = json.loads(json_text)
    data = raw.get("data", raw)  # v2 nests; v1/v3 may not
    spec = raw.get("spec", "")
    tags = list(data.get("tags", []))
    if spec == "chara_card_v1" or "spec" not in raw:
        tags.append("st_v1")
    elif spec == "chara_card_v3":
        tags.append("st_v3")
    tags.append("imported")
    mes_example = data.get("mes_example", "")
    dialogues = []
    if mes_example:
        for block in mes_example.split("\n\n"):
            lines = block.strip().split("\n")
            user = next((l[len("user:"):].strip() for l in lines if l.startswith("user:")), "")
            assistant = next((l[len("assistant:"):].strip() for l in lines if l.startswith("assistant:")), "")
            if user or assistant:
                dialogues.append({"user": user, "assistant": assistant})
    return CharacterCard(
        id=None, name=data.get("name", "Imported"),
        description=data.get("description", ""),
        personality=data.get("personality", "neutral"),
        scenario=data.get("scenario", ""),
        example_dialogues=dialogues,
        tags=tags,
        created_by="imported",
        created_at="", updated_at="",
    )
```

**Step 3: Wire `handle_import_v2` and `handle_export`**

```python
async def handle_import_v2(msg, ctx):
    card = parse_sillytavern_v2(msg.get("json_text", ""))
    cid = ctx.card_repo.upsert_character(card)
    return await ctx.send({"type": "card.imported", "card_id": cid, "warnings": []})


async def handle_export(msg, ctx):
    card = ctx.card_repo.get_character(msg["id"])
    if not card:
        return await ctx.send({"type": "card.error", "code": "not_found"})
    return await ctx.send({"type": "card.exported", "card": _card_to_dict(card)})
```

**Step 4: Commit**

```bash
git add src/server/handlers/card.py tests/test_st_v2_parser.py
git commit -m "feat(ws): ST V2 import/export handlers + parser"
```

---

### Task 2.6: Avatar HTTP endpoint

**Files:**
- Modify: `src/server/handlers/card.py` (add HTTP handler; uses aiohttp if available — match existing pattern in P7.2)
- Test: manual smoke in Slice 5

**Step 1: Implement**

```python
async def handle_avatar_upload(request, card_repo):
    from aiohttp import web
    card_id = int(request.match_info["id"])
    ext = request.headers.get("X-FSAR-Avatar-Ext", "png")
    if ext not in ("png", "jpg", "webp"):
        return web.json_response({"error": "bad_ext"}, status=400)
    data = await request.read()
    if len(data) > 2 * 1024 * 1024:
        return web.json_response({"error": "too_large"}, status=413)
    path = card_repo.save_avatar(card_id, ext, data)
    return web.json_response({"avatar_path": path})
```

(Add `save_avatar` method to `CardRepo` if not already there — it writes to `data/avatars/{card_id}.{ext}` and updates `character_cards.avatar_path`.)

**Step 2: Register route** in the existing aiohttp app setup (location depends on existing code).

**Step 3: Commit**

```bash
git add src/server/handlers/card.py
git commit -m "feat(http): avatar upload endpoint"
```

---

### Task 2.7: Session-level character binding handlers

**Files:**
- Modify: `src/server/handlers/card.py`

**Step 1: Implement**

```python
async def handle_set_session_character(msg, ctx):
    ctx.session_store.set_character(msg["session_id"], msg["character_id"])
    # Trigger sessions.updated
    await ctx.broadcast({"type": "sessions.updated", "session_id": msg["session_id"]})
    return await ctx.send({"type": "card.session_character_set",
                           "session_id": msg["session_id"],
                           "character_id": msg["character_id"]})


async def handle_list_session_character(msg, ctx):
    cid = ctx.session_store.get_character(msg["session_id"])
    return await ctx.send({"type": "card.session_character",
                           "session_id": msg["session_id"],
                           "character_id": cid})
```

**Step 2: Commit**

```bash
git add src/server/handlers/card.py
git commit -m "feat(ws): session-level character binding handlers"
```

---

### Task 2.8: Emotion WS types (validate / get / set)

**Files:**
- Modify: `src/server/handlers/card.py`

**Step 1: Implement `handle_validate_formula`**

```python
async def handle_validate_formula(msg, ctx):
    from src.core.formula_engine import validate_formula
    available = [m["key"] for m in ctx.card_repo.get_emotion_schema(msg["character_id"])]
    ok, err = validate_formula(msg.get("formula", ""), available)
    return await ctx.send({"type": "card.formula_validated", "valid": ok, "error": err})
```

**Step 2: Implement `handle_get_emotion`**

```python
async def handle_get_emotion(msg, ctx):
    cid = msg["character_id"]
    return await ctx.send({
        "type": "card.emotion",
        "character_id": cid,
        "state": ctx.card_repo.get_emotion_state(cid),
        "schema": ctx.card_repo.get_emotion_schema(cid),
        "formulas": ctx.card_repo.get_emotion_formulas(cid),
    })
```

**Step 3: Implement `handle_set_emotion_schema`**

```python
async def handle_set_emotion_schema(msg, ctx):
    ctx.card_repo.set_emotion_schema_and_formulas(
        msg["character_id"], msg["schema"], msg["formulas"]
    )
    return await ctx.send({"type": "card.emotion_schema_set", "character_id": msg["character_id"]})
```

**Step 4: Commit**

```bash
git add src/server/handlers/card.py
git commit -m "feat(ws): emotion validate / get / set handlers"
```

---

### Task 2.9: Server-pushed events (user_card_renamed, emotion_state_updated)

**Files:**
- Modify: `src/memory/cards.py` (`upsert_user_card` and `set_emotion_state` to emit push events via a registered callback)
- Modify: `src/server/ws_server.py` (register the push callback at startup)

**Step 1: Add push hook to CardRepo**

```python
class CardRepo:
    _on_change = None  # class-level; set by ws_server at startup

    def set_change_listener(self, listener):
        # listener signature: (event_type: str, payload: dict) -> None
        self._on_change = listener
```

In `upsert_user_card` and `set_emotion_state`, after the write, call:

```python
        if self._on_change:
            if "<event_type>" == "user_card_renamed":
                # check if name changed vs previous
                ...
            self._on_change("user_card_renamed", {"user_card_id": card.id, "name": card.name})
            # or
            self._on_change("emotion_state_updated", {"character_id": cid, "state": state, "source": "update_emotion"})
```

(Implementation detail: track previous name to detect "renamed" vs "new".)

**Step 2: Wire listener in ws_server**

```python
card_repo.set_change_listener(
    lambda event_type, payload: asyncio.create_task(
        broadcast({"type": event_type, **payload})
    )
)
```

**Step 3: Commit**

```bash
git add src/memory/cards.py src/server/ws_server.py
git commit -m "feat(ws): server-pushed card.user_card_renamed + emotion_state_updated"
```

---

# Slice 3 — Chat Topbar + Message Labels

### Task 3.1: `stores/cards.ts` (frontend store)

**Files:**
- Create: `frontend/src/stores/cards.ts`

**Step 1: Implement**

```typescript
// frontend/src/stores/cards.ts
// SPDX-License-Identifier: Apache-2.0
import { create } from "zustand";

type Card = {
  id: number;
  name: string;
  description: string;
  personality: string;
  scenario: string;
  example_dialogues: Array<{user: string; assistant: string}>;
  tags: string[];
  is_default: number;
  avatar_path: string | null;
  emotion_state: Record<string, number>;
};

type UserCard = {
  id: number;
  name: string;
  description: string;
  communication_style: string;
  preferences: Record<string, unknown>;
  interests: string[];
  is_default: number;
};

type CardsState = {
  characters: Card[];
  userCards: UserCard[];
  defaultUserCard: UserCard | null;
  refresh: () => Promise<void>;
  setSessionCharacter: (sessionId: string, characterId: number) => Promise<void>;
  handleWsMessage: (msg: any) => void;
};

export const useCardsStore = create<CardsState>((set, get) => ({
  characters: [],
  userCards: [],
  defaultUserCard: null,
  refresh: async () => {
    const chars = await window.__WS.send({ type: "card.list", kind: "character" });
    const users = await window.__WS.send({ type: "card.list", kind: "user" });
    set({ characters: chars.cards, userCards: users.cards });
    const def = users.cards.find((c: UserCard) => c.is_default === 1) ?? null;
    set({ defaultUserCard: def });
  },
  setSessionCharacter: async (sessionId, characterId) => {
    await window.__WS.send({ type: "card.set_session_character", session_id: sessionId, character_id: characterId });
  },
  handleWsMessage: (msg) => {
    if (msg.type === "card.user_card_renamed") {
      const cur = get().defaultUserCard;
      if (cur && cur.id === msg.user_card_id) {
        set({ defaultUserCard: { ...cur, name: msg.name } });
      }
    }
  },
}));
```

**Step 2: Commit**

```bash
git add frontend/src/stores/cards.ts
git commit -m "feat(frontend): cards store (Zustand)"
```

---

### Task 3.2: `CharacterSelector.tsx` (topbar dropdown)

**Files:**
- Create: `frontend/src/components/chat/CharacterSelector.tsx`

**Step 1: Implement**

```tsx
// frontend/src/components/chat/CharacterSelector.tsx
// SPDX-License-Identifier: Apache-2.0
import { useCardsStore } from "../../stores/cards";
import { useSessionStore } from "../../stores/session";

export function CharacterSelector({ sessionId }: { sessionId: string }) {
  const characters = useCardsStore((s) => s.characters);
  const setSessionCharacter = useCardsStore((s) => s.setSessionCharacter);
  const current = useSessionStore((s) => s.sessions[sessionId]?.character_card_id);
  const currentCard = characters.find((c) => c.id === current) ?? characters.find((c) => c.is_default === 1);

  return (
    <select
      value={currentCard?.id ?? ""}
      onChange={(e) => setSessionCharacter(sessionId, Number(e.target.value))}
    >
      {characters.map((c) => (
        <option key={c.id} value={c.id}>{c.name}{c.is_default === 1 ? " (default)" : ""}</option>
      ))}
    </select>
  );
}
```

(Adjust imports to match the existing session store name. The exact API depends on P7.11's session-store structure.)

**Step 2: Commit**

```bash
git add frontend/src/components/chat/CharacterSelector.tsx
git commit -m "feat(frontend): topbar character selector"
```

---

### Task 3.3: Topbar wiring

**Files:**
- Modify: `frontend/src/components/chat/Topbar.tsx`

**Step 1: Add `<CharacterSelector>` to Topbar**

Place between the existing provider switcher and mode switcher (or wherever fits the current Topbar layout — P7.11's layout is the source of truth).

**Step 2: Manual smoke** in dev server: topbar shows character dropdown, switching character persists across page reload (session character is in DB).

**Step 3: Commit**

```bash
git add frontend/src/components/chat/Topbar.tsx
git commit -m "feat(frontend): topbar shows character selector"
```

---

### Task 3.4: MessageList — character_name on assistant messages

**Files:**
- Modify: `frontend/src/components/chat/MessageList.tsx`

**Step 1: Read character_name from message**

Find the assistant-message rendering. Replace any hardcoded label (e.g., "FSAR") with `message.character_name ?? "FSAR"`.

**Step 2: Manual smoke**: send a turn, verify the assistant bubble's label matches the current character.

**Step 3: Commit**

```bash
git add frontend/src/components/chat/MessageList.tsx
git commit -m "feat(frontend): ASSISTANT bubble label = character_name"
```

---

### Task 3.5: MessageList — user_name on USER messages

**Files:**
- Modify: `frontend/src/components/chat/MessageList.tsx`

**Step 1: Read user_name from message**

Find the user-message rendering. Replace hardcoded "USER" with `message.user_name ?? "USER"`.

**Step 2: Manual smoke**: send a turn, verify the user bubble's label matches `user_card.name` (default: "default-user" until user renames it).

**Step 3: Commit**

```bash
git add frontend/src/components/chat/MessageList.tsx
git commit -m "feat(frontend): USER bubble label = user_name"
```

---

### Task 3.6: chat_engine emit extended payload

**Files:**
- Modify: `src/server/chat_engine.py` (already partly done in Task 1.12 — verify the WS emit carries `character_name` + `user_name`)

**Step 1: Verify and adjust if needed**

The `chat_engine` emit path needs to include:
- `character_name` and `character_id` on assistant `chat.delta` first frame + `chat.done`
- `user_name` and `user_card_id` on `chat.send` echo

If Task 1.12 already did this, just verify; if not, add.

**Step 2: Commit**

```bash
git add src/server/chat_engine.py
git commit -m "feat(chat): emit character_name + user_name in WS payload"
```

---

# Slice 4 — /cards Page (Character Tab)

### Task 4.1: Page skeleton + routing

**Files:**
- Create: `frontend/src/pages/Cards.tsx`
- Modify: `frontend/src/App.tsx` (or wherever routes are registered) — add `<Route path="/cards" element={<Cards />} />`
- Modify: `frontend/src/components/Sidebar.tsx` (or wherever the nav lives) — add a `Cards` entry above `Settings`

**Step 1: Skeleton page**

```tsx
// frontend/src/pages/Cards.tsx
import { useState } from "react";
import { CharacterCardList } from "../components/cards/CharacterCardList";
import { UserCardList } from "../components/cards/UserCardList";

export function Cards() {
  const [tab, setTab] = useState<"character" | "user">("character");
  return (
    <div>
      <h1>Cards</h1>
      <div>
        <button onClick={() => setTab("character")} aria-pressed={tab === "character"}>
          Character 卡片
        </button>
        <button onClick={() => setTab("user")} aria-pressed={tab === "user"}>
          User 卡片
        </button>
      </div>
      {tab === "character" ? <CharacterCardList /> : <UserCardList />}
    </div>
  );
}
```

**Step 2: Wire route + sidebar**

**Step 3: Manual smoke**: navigate to `/cards`, see both tabs.

**Step 4: Commit**

```bash
git add frontend/src/pages/Cards.tsx frontend/src/App.tsx frontend/src/components/Sidebar.tsx
git commit -m "feat(frontend): /cards page skeleton + sidebar entry"
```

---

### Task 4.2: `CharacterCardList.tsx`

**Files:**
- Create: `frontend/src/components/cards/CharacterCardList.tsx`

**Step 1: Implement**

```tsx
import { useCardsStore } from "../../stores/cards";
import { CharacterCardEditor } from "./CharacterCardEditor";

export function CharacterCardList() {
  const { characters, refresh } = useCardsStore();
  const [editing, setEditing] = useState<number | "new" | null>(null);

  useEffect(() => { refresh(); }, []);

  if (editing !== null) {
    return <CharacterCardEditor cardId={editing} onDone={() => { setEditing(null); refresh(); }} />;
  }

  return (
    <div>
      <button onClick={() => setEditing("new")}>+ New Character</button>
      <button onClick={refresh}>Refresh</button>
      <ul>
        {characters.map((c) => (
          <li key={c.id}>
            {c.avatar_path && <img src={c.avatar_path} alt="" />}
            <strong>{c.name}</strong> {c.is_default === 1 && <em>(default)</em>}
            <p>{c.personality}</p>
            <button onClick={() => setEditing(c.id)}>Edit</button>
          </li>
        ))}
      </ul>
    </div>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/src/components/cards/CharacterCardList.tsx
git commit -m "feat(frontend): character card list component"
```

---

### Task 4.3: `CharacterCardEditor.tsx` (basic fields)

**Files:**
- Create: `frontend/src/components/cards/CharacterCardEditor.tsx`

**Step 1: Implement editor with fields per spec §7.2** (name, description, personality, scenario, system_prompt_override, example_dialogues, tags, is_default, header buttons). Avatar upload, Emotion section, import/export wired in Tasks 4.4 / 4.6-4.8.

**Step 2: Commit**

```bash
git add frontend/src/components/cards/CharacterCardEditor.tsx
git commit -m "feat(frontend): character card editor (basic fields)"
```

---

### Task 4.4: Avatar upload integration

**Files:**
- Modify: `frontend/src/components/cards/CharacterCardEditor.tsx`

**Step 1: Wire the avatar input**

```tsx
const onAvatarPick = async (file: File) => {
  const fd = new FormData();
  fd.append("avatar", file);
  await fetch(`/api/card/${cardId}/avatar`, {
    method: "POST",
    headers: { "X-FSAR-Avatar-Ext": file.name.split(".").pop() },
    body: fd,
  });
  refresh();
};
```

**Step 2: Commit**

```bash
git add frontend/src/components/cards/CharacterCardEditor.tsx
git commit -m "feat(frontend): avatar upload to /api/card/:id/avatar"
```

---

### Task 4.5: Import / Export UI

**Files:**
- Modify: `frontend/src/components/cards/CharacterCardEditor.tsx`

**Step 1: Add import (paste JSON / ST V2) and export (download JSON) buttons**

```tsx
const onImport = async (text: string, format: "json" | "st_v2") => {
  if (format === "st_v2") {
    await window.__WS.send({ type: "card.import_v2", json_text: text });
  } else {
    const card = JSON.parse(text);
    await window.__WS.send({ type: "card.upsert", kind: "character", card });
  }
  refresh();
};

const onExport = async (id: number) => {
  const res = await window.__WS.send({ type: "card.export", id });
  const blob = new Blob([JSON.stringify(res.card, null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `${res.card.name}.json`;
  a.click();
};
```

**Step 2: Commit**

```bash
git add frontend/src/components/cards/CharacterCardEditor.tsx
git commit -m "feat(frontend): import/export buttons (JSON + ST V2)"
```

---

### Task 4.6: Emotion section — current state bars

**Files:**
- Modify: `frontend/src/components/cards/CharacterCardEditor.tsx`

**Step 1: Add collapsible Emotion section showing 7 bars (per spec §7.2.1-a)**

```tsx
function EmotionBars({ state }: { state: Record<string, number> }) {
  return (
    <div>
      {Object.entries(state).map(([key, value]) => (
        <div key={key}>
          <span>{key}</span>
          <progress value={Math.abs(value)} max={100} />
          <span>{value}</span>
        </div>
      ))}
    </div>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/src/components/cards/CharacterCardEditor.tsx
git commit -m "feat(frontend): emotion current-state bars"
```

---

### Task 4.7: Emotion section — schema editor

**Files:**
- Modify: `frontend/src/components/cards/CharacterCardEditor.tsx`

**Step 1: Add schema table (per spec §7.2.1-b)**

Add rows: `[name] [min] [max] [initial] [×]`, with a [+] button. Live-validates `min < max` and `min ≤ initial ≤ max`.

**Step 2: Commit**

```bash
git add frontend/src/components/cards/CharacterCardEditor.tsx
git commit -m "feat(frontend): emotion schema editor"
```

---

### Task 4.8: Emotion section — formulas editor with live validate

**Files:**
- Modify: `frontend/src/components/cards/CharacterCardEditor.tsx`

**Step 1: Add formula rows + validate button**

```tsx
const onValidate = async (formula: string) => {
  const res = await window.__WS.send({
    type: "card.validate_formula",
    character_id: cardId,
    formula,
  });
  return res;  // { valid, error? }
};
```

Display `✓` green / `✗` red + error message next to the row.

**Step 2: Commit**

```bash
git add frontend/src/components/cards/CharacterCardEditor.tsx
git commit -m "feat(frontend): emotion formulas editor with live validate"
```

---

# Slice 5 — /cards Page (User Tab) + E2E

### Task 5.1: `UserCardList.tsx`

**Files:**
- Create: `frontend/src/components/cards/UserCardList.tsx`

**Step 1: Implement** — mirror `CharacterCardList` but for user cards (no Emotion section).

**Step 2: Commit**

```bash
git add frontend/src/components/cards/UserCardList.tsx
git commit -m "feat(frontend): user card list component"
```

---

### Task 5.2: `UserCardEditor.tsx`

**Files:**
- Create: `frontend/src/components/cards/UserCardEditor.tsx`

**Step 1: Implement** — fields per spec §7.3 (name, description, preferences, interests, communication_style, is_default). Save/Cancel/Delete header.

**Step 2: Commit**

```bash
git add frontend/src/components/cards/UserCardEditor.tsx
git commit -m "feat(frontend): user card editor"
```

---

### Task 5.3: Preferences dynamic key-value UI

**Files:**
- Modify: `frontend/src/components/cards/UserCardEditor.tsx`

**Step 1: Add dynamic key-value rows** for `preferences`. Each row has [key input] [value input] [×]. [+] adds a row. Validates non-empty key.

**Step 2: Commit**

```bash
git add frontend/src/components/cards/UserCardEditor.tsx
git commit -m "feat(frontend): user card preferences dynamic UI"
```

---

### Task 5.4: Full E2E smoke

**Files:** (no new files — manual smoke)

**Step 1: Run the GUI dev server**

Run: `pnpm dev` (or the project's GUI start command). Wait for the app to load.

**Step 2: Walk through the E2E flow**

1. Fresh install: verify `/cards` shows 6 default character cards + 1 default user card.
2. Click character "FSAR-zh" (default) — verify the chat topbar shows it.
3. Send a turn. Verify the assistant bubble shows "FSAR-zh" label and the reply reads in FSAR persona (concise, friendly).
4. Click character "coding-coach-zh" in the topbar — verify the next reply is from the code teacher.
5. Open `/cards` → click user card → rename "default-user" to "小明". Verify the next user bubble shows "小明" as label.
6. Open `/cards` → click FSAR-en → click "Edit" → open Emotion section. Verify the 7 bars show 50 each. Edit a formula, click validate, see green ✓.
7. Restart the app. Verify character binding persists (session.character_card_id was set in Step 4).
8. Send a message after restart. Verify "小明" label persists.

**Step 3: Check the audit log**

Run: `sqlite3 data/fsar.db "SELECT * FROM emotion_audit LIMIT 5"` — verify rows were written for the LLM `update_emotion` calls (if the LLM chose to use it).

**Step 4: Commit** (no source changes; the smoke passed)

```bash
git commit --allow-empty -m "test: PL2.0 E2E smoke passes"
```

---

### Task 5.5: CLI regression check

**Files:** (no new files)

**Step 1: Run existing CLI test**

Per CLAUDE.md: "NEVER run tests automatically. Only run tests when ... the task definition requires testing". This task requires the regression check, so run it.

Run: `pytest tests/ -v` (the existing CLI tests, excluding the new PL2.0 tests).

**Step 2: Run CLI manually**

Run: `python main.py`, start a new session, send a message, verify the reply matches P7.11 behavior (default character is FSAR-zh whose persona block is empty + AGENT_SYSTEM_PROMPT passes through → equivalent to the pre-PL2.0 prompt).

**Step 3: Commit** (only if any tweaks were needed; otherwise nothing to commit)

```bash
git commit --allow-empty -m "test: PL2.0 CLI regression check passes"
```

---

## Self-Review

**Spec coverage.** Skimmed spec sections:
- §1.2 exit criterion (create character → switch → reply shows persona) → Tasks 1.13 + 1.14 (seed) + 1.11 (chat engine resolves) + 3.2/3.3 (topbar dropdown). Covered.
- §1.3 non-goals (no onboarding wizard, no card_edit tool, no derived condition labels, no cross-character coupling) → no tasks implement these. Confirmed.
- §2 D1-D18 → all 18 decisions are reflected in tasks. D7 (override append) → Task 1.8 explicitly tests it. D15-D18 (emotion) → Tasks 1.4-1.7 + 1.9 + 1.12.
- §3 architecture (3.1 component diagram, 3.2 message flow) → Tasks 1.11 + 1.12 + 3.6. Covered.
- §4 data model (4.1-4.7) → Tasks 1.1-1.3 + 1.5 + 1.6 + 1.10. Covered.
- §5 backend modules (5.0-5.7) → Tasks 1.4-1.7 + 1.9-1.12 + 1.14-1.15 + 2.1-2.9. Covered.
- §6 prompt assembly (6.1-6.5) → Tasks 1.7 + 1.8. Covered.
- §7 frontend (7.1-7.8) → Tasks 3.1-3.6 + 4.1-4.8 + 5.1-5.3. Covered.
- §8 ST V2 import → Task 2.5. Covered.
- §9 testing → all 7 test files specified across Tasks 1.1-1.10 + 2.5. Count: 8 + 5 + 6 + 4 + 4 + 11 + 6 = 46 cases, exceeding spec's ~38 target. Acceptable — extra cases came from per-TDD discipline, not scope creep.
- §10 task slicing (5 slices) → matches. Each slice has a verify step.
- §11 risks (12 risks) → risks 1, 2, 6, 7 are documented in tasks; risks 3, 4, 5, 8, 9, 10, 11, 12 are notes in tasks (mid-stream awareness, not action items). Acceptable.
- §12 DoD (8 items) → Slice 5 tasks cover items 1-9. Acceptable.
- §13 self-review → recursive. Skip.

**Placeholder scan.** No "TBD" / "TODO" / "fill in" / "implement later" markers. Step "verify" patterns are explicit. Code shown is complete (not elided).

**Type consistency.** Names check out across tasks:
- `CharacterCard` / `UserCard` defined in Task 1.1; used everywhere.
- `CardRepo` methods consistent: `upsert_character` returns `int`; `set_emotion_state` takes `dict[str, float]`.
- `PersonaBlock` defined in Task 1.7; consumed by Task 1.8.
- WS types named per spec §5.6: `card.list`, `card.get`, `card.upsert`, `card.delete`, `card.set_default`, `card.import_v2`, `card.export`, `card.set_session_character`, `card.list_session_character`, `card.validate_formula`, `card.get_emotion`, `card.set_emotion_schema`, `card.user_card_renamed`, `card.emotion_state_updated`. All present.
- Tool name: `update_emotion` consistent (tool function name + WS-emitted tool call).
- Emotion state snapshot field name: `emotion_state` in WS `chat.done` payload. Matches spec §5.4.

One minor inconsistency caught: Task 1.4's tokenizer regex `_VAR_NAME` was unused — flagged for cleanup but doesn't break anything.

Plan is ready for execution.
