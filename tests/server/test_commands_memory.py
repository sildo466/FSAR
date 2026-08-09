import asyncio

from src.memory import LongTermMemory, UserModel
from src.server.handlers.commands import execute


class _FakeClear:
    def __init__(self):
        self.calls = 0

    def clear(self):
        self.calls += 1


class Engine:
    def __init__(self, long_memory, user_model):
        self.long_memory = long_memory
        self.user_model = user_model
        self.semantic = _FakeClear()
        self.short_memory = _FakeClear()


def _make_engine(tmp_path):
    return Engine(
        LongTermMemory(tmp_path / "memory.db"),
        UserModel(tmp_path / "user.db"),
    )


def test_memory_clear_wipes_all_stores(tmp_path):
    engine = _make_engine(tmp_path)
    engine.long_memory.save_message("s1", "user", "hello")
    engine.long_memory.save_message("s1", "assistant", "hi there")
    engine.long_memory.save_message("s2", "user", "another session")
    engine.user_model.set_preference("language", "zh")
    engine.user_model.set_profile("name", "tester")

    output = asyncio.run(execute(engine, "/memory clear"))

    assert engine.long_memory.get_stats() == {"total_messages": 0, "total_sessions": 0}
    assert engine.user_model.get_all_preferences() == {}
    assert engine.user_model.get_profile() == {}
    assert engine.semantic.calls == 1
    assert engine.short_memory.calls == 1
    assert "3 long-term message(s)" in output


def test_memory_clear_on_empty_stores_is_safe(tmp_path):
    engine = _make_engine(tmp_path)

    output = asyncio.run(execute(engine, "/memory clear"))

    assert "0 long-term message(s)" in output


def test_memory_unknown_subcommand_usage_lists_clear(tmp_path):
    engine = _make_engine(tmp_path)

    output = asyncio.run(execute(engine, "/memory bogus"))

    assert "clear" in output
    assert output.startswith("Usage:")
