# SPDX-License-Identifier: MIT
"""One turn can be pointed at a different workspace than its conversation's."""

from __future__ import annotations

import types
from types import SimpleNamespace

from src.core.agent_runtime import AgentRunState
from src.memory.workspace import Workspace
from src.server import chat_engine as ce


def _ws(name: str) -> Workspace:
    return Workspace(id=1, name=name, root_path=f"/tmp/{name}", allowed_paths=["**"],
                     blocked_patterns=[], default_for_new=0, created_at="", updated_at="")


def _engine(**over) -> SimpleNamespace:
    base = {
        "workspace_repo": SimpleNamespace(
            get_or_create_binding=lambda cid: _ws("the-conversation-default"),
        ),
        "config": SimpleNamespace(get=lambda key, default=None: default),
        "_session_cwd_hint": "",
        "_room_sandbox_for": None,
    }
    base.update(over)
    engine = SimpleNamespace(**base)
    # The real engine always has these; binding the real methods keeps the stub
    # honest rather than growing a second copy of the rules inside the test.
    engine._turn_workspace = types.MethodType(ce.ChatEngine._turn_workspace, engine)
    engine.room_sandbox = types.MethodType(ce.ChatEngine.room_sandbox, engine)
    return engine


def test_the_run_state_carries_the_override() -> None:
    state = AgentRunState(root_task_id="t", profile=None)
    assert state.workspace_override is None


def test_the_prompt_names_the_override_not_the_binding() -> None:
    engine = _engine()
    out = ce.ChatEngine._workspace_context(engine, "s1", _ws("mira-stage"))
    assert "mira-stage" in out
    assert "the-conversation-default" not in out


def test_without_an_override_the_prompt_names_the_binding() -> None:
    """Proves the default path did not move."""
    engine = _engine()
    out = ce.ChatEngine._workspace_context(engine, "s1")
    assert "the-conversation-default" in out


def test_turn_workspace_prefers_the_override() -> None:
    engine = _engine()
    picked = ce.ChatEngine._turn_workspace(engine, "s1", _ws("staging"))
    assert picked.name == "staging"


def test_turn_workspace_falls_back_to_the_binding() -> None:
    engine = _engine()
    picked = ce.ChatEngine._turn_workspace(engine, "s1")
    assert picked.name == "the-conversation-default"


def test_run_agent_accepts_the_override_keyword() -> None:
    """The room hands a staging through this name; a signature that does not
    take it would only fail once a room actually ran."""
    import inspect

    params = inspect.signature(ce.ChatEngine._run_agent).parameters
    assert "workspace_override" in params
    assert params["workspace_override"].default is None


def test_the_guarded_paths_accept_the_override() -> None:
    import inspect

    for name in ("_execute_guarded", "_sandbox_tool_call", "_build_prompt"):
        params = inspect.signature(getattr(ce.ChatEngine, name)).parameters
        assert "workspace_override" in params, name
        assert params["workspace_override"].default is None, name


def test_a_room_conversation_uses_the_room_sandbox() -> None:
    """A room's chat turn is confined to the room's sandbox; an ordinary
    conversation keeps its own binding. This is the whole incident fix: the
    room used to inherit `default_for_new`, which on the affected install was
    `C:\`."""
    room_ws = _ws("the-room-sandbox")
    engine = _engine(
        _room_sandbox_for=lambda cid: room_ws if cid == "room-conv" else None,
    )

    assert ce.ChatEngine._turn_workspace(engine, "room-conv").name == "the-room-sandbox"
    assert ce.ChatEngine._turn_workspace(engine, "own-conv").name == "the-conversation-default"

    explicit = _ws("explicit")
    assert ce.ChatEngine._turn_workspace(engine, "room-conv", explicit) is explicit, (
        "an explicit override (work-turn staging) still wins over the sandbox"
    )


def test_room_sandbox_is_none_without_a_resolver() -> None:
    """The engine must degrade to no-room-policy, not to a crash, when nothing
    wired a resolver (tests, headless callers)."""
    engine = _engine()
    assert ce.ChatEngine.room_sandbox(engine, "anything") is None
    assert ce.ChatEngine.room_sandbox(engine, "") is None
