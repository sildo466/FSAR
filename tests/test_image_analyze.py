from types import SimpleNamespace

import pytest

from src.tools.builtin.image_analyze import ImageAnalyzeTool


async def _run(monkeypatch, get_config_side_effect):
    captured = {}

    class FakeResp:
        choices = [SimpleNamespace(message=SimpleNamespace(content="analyzed"))]

    def fake_chat_completion(client, **kwargs):
        captured["client"] = client
        captured["model"] = kwargs.get("model")
        return FakeResp()

    clients = []

    def fake_make_llm_client(provider_id, base_url="", api_key=""):
        clients.append((provider_id, base_url, api_key))
        return object()

    monkeypatch.setattr("src.tools.builtin.image_analyze.get_config", get_config_side_effect)
    monkeypatch.setattr("src.utils.llm_factory.chat_completion", fake_chat_completion)
    monkeypatch.setattr(
        "src.sandbox.tool_guard.guard_file_read",
        lambda path, cfg: None,
    )
    monkeypatch.setattr("src.tools.builtin.image_analyze.Path", lambda p: SimpleNamespace(
        exists=lambda: True, suffix=".png", read_bytes=lambda: b"\x89PNG",
    ))
    monkeypatch.setattr("src.utils.llm_factory.make_llm_client", fake_make_llm_client)

    tool = ImageAnalyzeTool()
    result = await tool.execute("x.png")
    return result, clients, captured


@pytest.mark.asyncio
async def test_image_analyze_uses_configured_vision_model(monkeypatch):
    def cfg_side():
        return SimpleNamespace(
            get_vision_model=lambda: {"base_url": "https://v", "api_key": "k", "model": "vl-1"},
        )

    result, clients, captured = await _run(monkeypatch, cfg_side)
    assert result == "analyzed"
    assert clients == [("vision", "https://v", "k")]
    assert captured["model"] == "vl-1"


@pytest.mark.asyncio
async def test_image_analyze_falls_back_to_main_model(monkeypatch):
    def cfg_side():
        return SimpleNamespace(
            get_vision_model=lambda: {"base_url": "", "api_key": "", "model": ""},
            get_active_provider=lambda: {"model": "main-model"},
            get=lambda k, d=None: "main-provider",
        )

    result, clients, captured = await _run(monkeypatch, cfg_side)
    assert result == "analyzed"
    assert clients == [("main-provider", "", "")]
    assert captured["model"] == "main-model"
