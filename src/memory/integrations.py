"""Persistence and graph validation for recursive integrations."""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.utils.fsar_config import get_default_config

_MODEL_REGISTRY: dict[int, "ModelSpec"] = {}
_INTEGRATION_REGISTRY: dict[int, "Integration"] = {}


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _db_path() -> Path:
    return Path(get_default_config().memory_sqlite_path)


def _conn() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA foreign_keys = ON")
    _ensure_schema(conn)
    return conn


def _close_conn(conn: sqlite3.Connection) -> None:
    if getattr(_conn, "__module__", __name__) == __name__:
        conn.close()


def _ensure_schema(conn: sqlite3.Connection) -> None:
    import importlib

    migration = importlib.import_module(
        "data.migrations.2026_07_16_pl2_6_integration_tables"
    )
    migration.up(conn)


@dataclass
class ModelSpec:
    provider: str
    model: str
    persona_prompt: str
    base_url: str = ""
    api_key: str = ""
    protocol: str = ""
    specialty: str = ""
    temperature: float = 0.7
    max_tokens: int | None = None
    id: int | None = None
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        if self.id is not None:
            _MODEL_REGISTRY[int(self.id)] = self

    @property
    def kind(self) -> str:
        return "model"

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "model",
            "id": self.id,
            "provider": self.provider,
            "base_url": self.base_url,
            "api_key": self.api_key,
            "protocol": self.protocol,
            "model": self.model,
            "persona_prompt": self.persona_prompt,
            "specialty": self.specialty,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class IntegrationSub:
    display_name: str
    kind: str = "model"
    model_id: int | None = None
    child_integration_id: int | None = None
    id: int | None = None
    position: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "position": self.position,
            "display_name": self.display_name,
            "kind": self.kind,
            "model_id": self.model_id,
            "child_integration_id": self.child_integration_id,
        }


@dataclass
class Integration:
    id: int | None
    name: str
    description: str
    main_model_id: int
    rounds: int = 2
    max_depth: int = 2
    max_subs_picked: int | None = 2
    is_default: int = 0
    subs: list[IntegrationSub] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        if self.id is not None:
            _INTEGRATION_REGISTRY[int(self.id)] = self

    @property
    def kind(self) -> str:
        return "integration"

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "integration",
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "main_model_id": self.main_model_id,
            "rounds": self.rounds,
            "max_depth": self.max_depth,
            "max_subs_picked": self.max_subs_picked,
            "is_default": self.is_default,
            "subs": [sub.to_dict() for sub in self.subs],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class CycleError(ValueError):
    code = "cycle"

    def __init__(self, integration_id: int, path: list[int] | None = None):
        self.integration_id = integration_id
        self.path = list(path or [integration_id])
        super().__init__(f"integration cycle detected: {' -> '.join(map(str, self.path))}")


class NotFoundError(LookupError):
    pass


def _row_to_model(row: sqlite3.Row | tuple[Any, ...]) -> ModelSpec:
    return ModelSpec(
        id=row[0], provider=row[1], base_url=row[2] or "", model=row[3], persona_prompt=row[4],
        specialty=row[5] or "", temperature=float(row[6] if row[6] is not None else 0.7),
        max_tokens=row[7], created_at=row[8] or "", updated_at=row[9] or "",
        api_key=(row[10] or "") if len(row) > 10 else "",
        protocol=(row[11] or "") if len(row) > 11 else "",
    )


def _row_to_sub(row: sqlite3.Row | tuple[Any, ...]) -> IntegrationSub:
    return IntegrationSub(
        id=row[0], position=int(row[1]), display_name=row[2], kind=row[3],
        model_id=row[4], child_integration_id=row[5],
    )


def _row_to_integration(row: sqlite3.Row | tuple[Any, ...], conn: sqlite3.Connection) -> Integration:
    intg_id = int(row[0])
    subs = conn.execute(
        "SELECT id,position,display_name,kind,model_id,child_integration_id "
        "FROM integration_subs WHERE integration_id=? ORDER BY position",
        (intg_id,),
    ).fetchall()
    return Integration(
        id=intg_id, name=row[1], description=row[2] or "", main_model_id=int(row[3]),
        rounds=int(row[4]), max_depth=int(row[5]), max_subs_picked=row[6],
        is_default=int(row[7]), subs=[_row_to_sub(s) for s in subs],
        created_at=row[8] or "", updated_at=row[9] or "",
    )


def _integration_row(conn: sqlite3.Connection, integration_id: int):
    return conn.execute(
        "SELECT id,name,description,main_model_id,rounds,max_depth,max_subs_picked,"
        "is_default,created_at,updated_at FROM integrations WHERE id=?",
        (integration_id,),
    ).fetchone()


def get_model(model_id: int) -> ModelSpec:
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT id,provider,base_url,model,persona_prompt,specialty,temperature,max_tokens,created_at,updated_at,api_key,protocol "
            "FROM models WHERE id=?", (model_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"model {model_id} not found")
        return _row_to_model(row)
    finally:
        _close_conn(conn)


def _registered_model(model_id: int) -> ModelSpec | None:
    return _MODEL_REGISTRY.get(int(model_id))


def _registered_integration(integration_id: int) -> Integration | None:
    return _INTEGRATION_REGISTRY.get(int(integration_id))


def _resolve_model_for_sub(sub: IntegrationSub) -> ModelSpec:
    if sub.model_id is None:
        raise NotFoundError("sub model is missing")
    return get_model(int(sub.model_id))


def list_models() -> list[ModelSpec]:
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT id,provider,base_url,model,persona_prompt,specialty,temperature,max_tokens,created_at,updated_at,api_key,protocol "
            "FROM models ORDER BY id"
        ).fetchall()
        return [_row_to_model(row) for row in rows]
    finally:
        _close_conn(conn)


def upsert_model(model: ModelSpec) -> int:
    now = model.updated_at or _now()
    created = model.created_at or now
    conn = _conn()
    try:
        if model.id is None:
            cur = conn.execute(
                "INSERT INTO models(provider,base_url,model,persona_prompt,specialty,temperature,max_tokens,created_at,updated_at,api_key,protocol) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (model.provider, model.base_url, model.model, model.persona_prompt, model.specialty,
                 model.temperature, model.max_tokens, created, now, model.api_key, model.protocol),
            )
            model.id = int(cur.lastrowid)
        else:
            conn.execute(
                "UPDATE models SET provider=?,base_url=?,model=?,persona_prompt=?,specialty=?,temperature=?,max_tokens=?,updated_at=?,api_key=?,protocol=? WHERE id=?",
                (model.provider, model.base_url, model.model, model.persona_prompt, model.specialty,
                 model.temperature, model.max_tokens, now, model.api_key, model.protocol, model.id),
            )
            if conn.total_changes == 0:
                raise NotFoundError(f"model {model.id} not found")
        conn.commit()
        return int(model.id)
    finally:
        _close_conn(conn)


def list_integrations() -> list[Integration]:
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT id,name,description,main_model_id,rounds,max_depth,max_subs_picked,is_default,created_at,updated_at "
            "FROM integrations ORDER BY name"
        ).fetchall()
        return [_row_to_integration(row, conn) for row in rows]
    finally:
        _close_conn(conn)


def get_integration(integration_id: int) -> Integration:
    conn = _conn()
    try:
        row = _integration_row(conn, int(integration_id))
        if row is None:
            raise NotFoundError(f"integration {integration_id} not found")
        return _row_to_integration(row, conn)
    finally:
        _close_conn(conn)


def _walk_ancestors_for_validation(conn: sqlite3.Connection, intg_id: int, seen: set[int], path: list[int]) -> None:
    if intg_id in seen:
        raise CycleError(intg_id, path + [intg_id])
    row = _integration_row(conn, intg_id)
    if row is None:
        raise NotFoundError(f"integration {intg_id} not found")
    next_seen = seen | {intg_id}
    next_path = path + [intg_id]
    for child_id, in conn.execute(
        "SELECT child_integration_id FROM integration_subs "
        "WHERE integration_id=? AND kind='integration'", (intg_id,)
    ):
        if child_id is not None:
            _walk_ancestors_for_validation(conn, int(child_id), next_seen, next_path)


def _validate_sub(sub: IntegrationSub) -> None:
    if sub.kind not in {"model", "integration"}:
        raise ValueError(f"invalid integration sub kind: {sub.kind}")
    if sub.kind == "model" and sub.model_id is None:
        raise ValueError("model sub requires model_id")
    if sub.kind == "integration" and sub.child_integration_id is None:
        raise ValueError("integration sub requires child_integration_id")


def upsert_integration(intg: Integration) -> int:
    now = intg.updated_at or _now()
    created = intg.created_at or now
    if not intg.name.strip():
        raise ValueError("integration name is required")
    if not 1 <= int(intg.rounds) <= 5:
        raise ValueError("rounds must be between 1 and 5")
    if not 1 <= int(intg.max_depth) <= 8:
        raise ValueError("max_depth must be between 1 and 8")
    conn = _conn()
    try:
        conn.execute("BEGIN")
        if intg.id is None:
            cur = conn.execute(
                "INSERT INTO integrations(name,description,main_model_id,rounds,max_depth,max_subs_picked,is_default,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (intg.name.strip(), intg.description or "", intg.main_model_id,
                 intg.rounds, intg.max_depth, intg.max_subs_picked, intg.is_default,
                 created, now),
            )
            intg.id = int(cur.lastrowid)
        else:
            if _integration_row(conn, int(intg.id)) is None:
                raise NotFoundError(f"integration {intg.id} not found")
            conn.execute(
                "UPDATE integrations SET name=?,description=?,main_model_id=?,rounds=?,max_depth=?,max_subs_picked=?,is_default=?,updated_at=? WHERE id=?",
                (intg.name.strip(), intg.description or "", intg.main_model_id,
                 intg.rounds, intg.max_depth, intg.max_subs_picked, intg.is_default,
                 now, intg.id),
            )
        conn.execute("DELETE FROM integration_subs WHERE integration_id=?", (intg.id,))
        for position, sub in enumerate(intg.subs):
            _validate_sub(sub)
            conn.execute(
                "INSERT INTO integration_subs(integration_id,position,display_name,kind,model_id,child_integration_id) "
                "VALUES(?,?,?,?,?,?)",
                (intg.id, position, sub.display_name, sub.kind,
                 sub.model_id if sub.kind == "model" else None,
                 sub.child_integration_id if sub.kind == "integration" else None),
            )
        _walk_ancestors_for_validation(conn, int(intg.id), set(), [])
        if intg.is_default:
            conn.execute("UPDATE integrations SET is_default=0 WHERE id<>?", (intg.id,))
        conn.commit()
        return int(intg.id)
    except Exception:
        conn.rollback()
        raise
    finally:
        _close_conn(conn)


def delete_integration(integration_id: int) -> None:
    conn = _conn()
    try:
        cur = conn.execute("DELETE FROM integrations WHERE id=?", (integration_id,))
        if cur.rowcount == 0:
            raise NotFoundError(f"integration {integration_id} not found")
        conn.commit()
        _INTEGRATION_REGISTRY.pop(int(integration_id), None)
    finally:
        _close_conn(conn)


def find_default_integration() -> Integration | None:
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT id,name,description,main_model_id,rounds,max_depth,max_subs_picked,is_default,created_at,updated_at "
            "FROM integrations WHERE is_default=1 ORDER BY id LIMIT 1"
        ).fetchone()
        return _row_to_integration(row, conn) if row else None
    finally:
        _close_conn(conn)


def set_default_integration(integration_id: int | None) -> None:
    conn = _conn()
    try:
        conn.execute("UPDATE integrations SET is_default=0")
        if integration_id is not None:
            cur = conn.execute("UPDATE integrations SET is_default=1 WHERE id=?", (integration_id,))
            if cur.rowcount == 0:
                raise NotFoundError(f"integration {integration_id} not found")
        conn.commit()
    finally:
        _close_conn(conn)


def create_run(integration_id: int, user_message: str, status: str = "running") -> int:
    conn = _conn()
    try:
        cur = conn.execute(
            "INSERT INTO integration_runs(integration_id,started_at,user_message,status) VALUES(?,?,?,?)",
            (integration_id, _now(), user_message, status),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        _close_conn(conn)


def finish_run(run_id: int, *, final_reply: str = "", status: str = "ok", total_calls: int = 0, total_cost_usd: float | None = None) -> None:
    conn = _conn()
    try:
        conn.execute(
            "UPDATE integration_runs SET finished_at=?,final_reply=?,status=?,total_calls=?,total_cost_usd=? WHERE id=?",
            (_now(), final_reply, status, total_calls, total_cost_usd, run_id),
        )
        conn.commit()
    finally:
        _close_conn(conn)


def record_token_usage(*, provider: str, model: str, input_tokens: int, output_tokens: int,
                       integration_run_id: int | None = None, cost_usd: float | None = None) -> int:
    conn = _conn()
    try:
        cur = conn.execute(
            "INSERT INTO llm_token_usage(ts,integration_run_id,provider,model,input_tokens,output_tokens,cost_usd) VALUES(?,?,?,?,?,?,?)",
            (_now(), integration_run_id, provider, model, int(input_tokens), int(output_tokens), cost_usd),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        _close_conn(conn)


def get_token_usage_by_provider(*, from_ts: str = "", to_ts: str = "",
                                db_path: str | Path | None = None) -> list[dict]:
    """Aggregate real LLM token usage per provider from llm_token_usage.

    Returns rows [{provider, model, prompt_tokens, completion_tokens,
    cost_usd}] ordered by total tokens desc. `db_path` overrides the default
    memory DB (used by the usage handler, which resolves its own DB)."""
    path = Path(db_path) if db_path else _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    try:
        _ensure_schema(conn)
        where: list[str] = []
        params: list[str] = []
        if from_ts:
            where.append("date(ts) >= date(?)")
            params.append(from_ts)
        if to_ts:
            where.append("date(ts) <= date(?)")
            params.append(to_ts)
        cond = (" WHERE " + " AND ".join(where)) if where else ""
        rows = conn.execute(
            "SELECT provider, model, SUM(input_tokens), SUM(output_tokens),"
            " SUM(COALESCE(cost_usd, 0)) FROM llm_token_usage"
            + cond +
            " GROUP BY provider, model"
            " ORDER BY SUM(input_tokens) + SUM(output_tokens) DESC",
            params,
        ).fetchall()
    finally:
        conn.close()
    merged: dict[str, dict] = {}
    for provider, model, prompt, completion, cost in rows:
        row = merged.get(provider) or {
            "provider": provider or "unknown",
            "model": model,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "cost_usd": 0.0,
            "_best": 0,
        }
        prompt = int(prompt or 0)
        completion = int(completion or 0)
        row["prompt_tokens"] += prompt
        row["completion_tokens"] += completion
        row["cost_usd"] += float(cost or 0)
        if prompt + completion > row["_best"]:
            row["model"] = model
            row["_best"] = prompt + completion
        merged[provider] = row
    return [
        {k: row[k] for k in ("provider", "model", "prompt_tokens", "completion_tokens", "cost_usd")}
        for row in merged.values() if row["_best"] > 0
    ]


__all__ = [
    "CycleError", "NotFoundError", "Integration", "IntegrationSub", "ModelSpec",
    "list_integrations", "get_integration", "upsert_integration", "delete_integration",
    "find_default_integration", "set_default_integration", "list_models", "get_model",
    "upsert_model", "create_run", "finish_run", "record_token_usage", "_conn",
    "_resolve_model_for_sub", "_registered_model", "_registered_integration",
]
