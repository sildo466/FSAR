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
    }
    base.update(over)
    engine = SimpleNamespace(**base)
    # The real engine always has this; binding the real method keeps the stub
    # honest rather than growing a second copy of the rule inside the test.
    engine._turn_workspace = types.MethodType(ce.ChatEngine._turn_workspace, engine)
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
