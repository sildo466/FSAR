import pytest

from src.server.handlers import settings as settings_mod


class _Ws:
    def __init__(self):
        self.sent = []

    async def send_json(self, payload):
        self.sent.append(payload)


class _Cfg:
    def __init__(self, vm=None):
        self._vm = vm
        self.saved = False

    def get_vision_model(self):
        return self._vm or {"base_url": "", "api_key": "", "model": ""}

    def set_vision_model(self, cfg):
        self._vm = cfg

    def save(self):
        self.saved = True


@pytest.mark.asyncio
async def test_llm_get_vision():
    cfg = _Cfg({"base_url": "https://v", "api_key": "k", "model": "m"})
    ws = _Ws()
    handled = await settings_mod.dispatch(ws, {"type": "llm.get_vision"}, cfg)
    assert handled is True
    assert ws.sent == [{
        "type": "llm.vision_config",
        "vision_model": {"base_url": "https://v", "api_key": "k", "model": "m"},
    }]


@pytest.mark.asyncio
async def test_llm_set_vision_persists():
    cfg = _Cfg()
    ws = _Ws()
    handled = await settings_mod.dispatch(
        ws,
        {"type": "llm.set_vision", "base_url": "https://v", "api_key": "k", "model": "m"},
        cfg,
    )
    assert handled is True
    assert cfg._vm == {"base_url": "https://v", "api_key": "k", "model": "m"}
    assert cfg.saved is True
    assert ws.sent == [{
        "type": "llm.vision_changed",
        "vision_model": {"base_url": "https://v", "api_key": "k", "model": "m"},
    }]


@pytest.mark.asyncio
async def test_llm_set_vision_resets_when_empty():
    cfg = _Cfg({"base_url": "https://v", "api_key": "k", "model": "m"})
    ws = _Ws()
    handled = await settings_mod.dispatch(
        ws,
        {"type": "llm.set_vision", "base_url": "", "api_key": "", "model": ""},
        cfg,
    )
    assert handled is True
    assert cfg._vm == {"base_url": "", "api_key": "", "model": ""}
