# SPDX-License-Identifier: MIT
from __future__ import annotations

from datetime import datetime

import pytest

from src.memory.experience_store import ExperienceStore
from src.memory.reflection import ReflectionStore, TaskReflection
from src.memory.user_model import UserModel


@pytest.fixture
def user_model(tmp_path):
    return UserModel(tmp_path / "memory.db")


def test_delete_preference(user_model):
    user_model.set_preference("editor", "nvim")
    assert user_model.delete_preference("editor") is True
    assert user_model.get_preference("editor") is None
    assert user_model.delete_preference("editor") is False


def test_delete_preference_leaves_others(user_model):
    user_model.set_preference("editor", "nvim")
    user_model.set_preference("shell", "bash")
    user_model.delete_preference("editor")
    assert list(user_model.get_all_preferences()) == ["shell"]


def test_delete_pattern(user_model):
    user_model.record_pattern("asks for markdown", "seen 3x")
    assert user_model.delete_pattern("asks for markdown") is True
    assert user_model.get_top_patterns() == []
    assert user_model.delete_pattern("asks for markdown") is False


def test_delete_reflection(tmp_path):
    store = ReflectionStore(tmp_path / "memory.db")
    ref = TaskReflection(
        task_id="t1",
        outcome="success",
        failure_modes=[],
        success_patterns=[],
        suggested_strategy="do the thing",
        step_count=3,
        tools_used=["read"],
        error_count=0,
        generated_at=datetime.now(),
    )
    rid = store.save(ref, session_id="s1")
    assert store.list_recent(limit=10)
    assert store.delete_reflection(rid) is True
    assert store.list_recent(limit=10) == []
    assert store.delete_reflection(rid) is False


def test_list_all_chunks_is_not_capped_at_hundred(tmp_path):
    store = ExperienceStore(tmp_path / "memory.db")
    for i in range(150):
        store.add_chunk(source="user_fact", title=f"t{i}", body=f"body {i}")
    chunks = store.list_all_chunks()
    assert len(chunks) == 150
    assert chunks[0].body == "body 0"
    assert chunks[0].id is not None
