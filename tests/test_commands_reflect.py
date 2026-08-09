"""Regression: `/reflect` must unpack the (client, model, provider) triple."""
from __future__ import annotations

import asyncio

import src.memory as memory_mod
from src.server.handlers import commands


class FakeReport:
    profile: dict = {}
    preferences: dict = {}
    patterns: list = []


class FakeReflector:
    def __init__(self, **kwargs):
        pass

    def set_llm(self, client):
        pass

    def reflect(self, force: bool = False):
        return FakeReport()


class FakeEngine:
    long_memory = object()
    user_model = object()
    feedback = object()

    def client_and_model(self):
        return object(), "model-x", "prov"


def test_reflect_command_handles_three_tuple(monkeypatch):
    monkeypatch.setattr(memory_mod, "IdleReflector", FakeReflector)

    result = asyncio.run(commands.execute(FakeEngine(), "/reflect"))

    assert not result.startswith("Command failed"), result
    assert "Reflection complete" in result
