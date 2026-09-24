import pytest

from src.server.handlers import settings as settings_mod


class _Ws:
    def __init__(self):
        self.sent = []

    async def send_json(self, payload):
        self.sent.append(payload)


class _Cfg:
    def __init__(self, vm=None, fail_save=False):
        self._vm = vm
        self.saved = False
        self.fail_save = fail_save

    def get_vision_model(self):
        return self._vm or {"base_url": "", "api_key": "", "model": ""}

    def set_vision_model(self, cfg):
        self._vm = cfg

    def save(self):
        self.saved = True
        if self.fail_save:
            raise OSError("disk full")


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


@pytest.mark.asyncio
async def test_llm_set_vision_rejects_incomplete_custom():
    cfg = _Cfg()
    ws = _Ws()
    handled = await settings_mod.dispatch(
        ws,
        {"type": "llm.set_vision", "base_url": "", "api_key": "k", "model": "vl-1"},
        cfg,
    )
    assert handled is True
    assert cfg._vm is None  # not applied
    assert ws.sent[0]["type"] == "error"
    assert ws.sent[0]["code"] == "incomplete_vision_model"


@pytest.mark.asyncio
async def test_llm_set_vision_surfaces_save_error():
    cfg = _Cfg(fail_save=True)
    ws = _Ws()
    handled = await settings_mod.dispatch(
        ws,
        {"type": "llm.set_vision", "base_url": "https://v", "api_key": "k", "model": "m"},
        cfg,
    )
    assert handled is True
    assert ws.sent[0]["type"] == "error"
    assert ws.sent[0]["code"] == "save_failed"


class _JudgeCfg(_Cfg):
    def __init__(self, judge=None, fail_save=False):
        super().__init__(fail_save=fail_save)
        self._judge = judge

    def get_judge(self):
        return self._judge or {"base_url": "", "api_key": "", "model": ""}

    def set_judge(self, cfg):
        self._judge = cfg


@pytest.mark.asyncio
async def test_llm_get_judge():
    cfg = _JudgeCfg({"base_url": "https://j", "api_key": "k", "model": "typesafe/jev"})
    ws = _Ws()
    handled = await settings_mod.dispatch(ws, {"type": "llm.get_judge"}, cfg)
    assert handled is True
    assert ws.sent == [{
        "type": "llm.judge_config",
        "judge": {"base_url": "https://j", "api_key": "k", "model": "typesafe/jev"},
    }]


@pytest.mark.asyncio
async def test_llm_set_judge_persists():
    cfg = _JudgeCfg()
    ws = _Ws()
    handled = await settings_mod.dispatch(
        ws,
        {"type": "llm.set_judge", "base_url": "https://j", "api_key": "k",
         "model": "typesafe/jev"},
        cfg,
    )
    assert handled is True
    assert cfg._judge == {"base_url": "https://j", "api_key": "k", "model": "typesafe/jev"}
    assert cfg.saved is True
    assert ws.sent == [{
        "type": "llm.judge_changed",
        "judge": {"base_url": "https://j", "api_key": "k", "model": "typesafe/jev"},
    }]


@pytest.mark.asyncio
async def test_llm_set_judge_rejects_incomplete_custom():
    cfg = _JudgeCfg()
    ws = _Ws()
    handled = await settings_mod.dispatch(
        ws, {"type": "llm.set_judge", "base_url": "https://j", "api_key": "k", "model": ""},
        cfg,
    )
    assert handled is True
    assert cfg._judge is None  # not applied
    assert ws.sent[0]["type"] == "error"
    assert ws.sent[0]["code"] == "incomplete_judge"


@pytest.mark.asyncio
async def test_llm_set_judge_clears_when_all_empty():
    cfg = _JudgeCfg({"base_url": "https://j", "api_key": "k", "model": "m"})
    ws = _Ws()
    await settings_mod.dispatch(
        ws, {"type": "llm.set_judge", "base_url": "", "api_key": "", "model": ""}, cfg,
    )
    assert cfg._judge == {"base_url": "", "api_key": "", "model": ""}


@pytest.mark.asyncio
async def test_llm_set_judge_surfaces_save_error():
    cfg = _JudgeCfg(fail_save=True)
    ws = _Ws()
    await settings_mod.dispatch(
        ws, {"type": "llm.set_judge", "base_url": "https://j", "api_key": "k", "model": "m"},
        cfg,
    )
    assert ws.sent[0]["type"] == "error"
    assert ws.sent[0]["code"] == "save_failed"


class _ActiveCfg(_Cfg):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.patched = {}
        self.active = None

    def get(self, key, default=None):
        return default

    def patch(self, key, value):
        self.patched[key] = value

    def set_active_provider(self, provider_id):
        self.active = provider_id

    def get_active_provider(self):
        return {"model": "m"}


class _Engine:
    def __init__(self):
        self.refreshes = 0

    def refresh_injection_pipeline(self):
        self.refreshes += 1


@pytest.mark.asyncio
async def test_set_active_refreshes_the_injection_pipeline():
    """The judge client is captured at build time, so a provider switch must rebuild."""
    cfg = _ActiveCfg()
    engine = _Engine()
    handled = await settings_mod.dispatch(
        _Ws(), {"type": "llm.set_active", "provider_id": "p1"}, cfg, engine,
    )
    assert handled is True
    assert engine.refreshes == 1


@pytest.mark.asyncio
async def test_patching_the_injection_budget_refreshes_the_pipeline():
    cfg = _ActiveCfg()
    engine = _Engine()
    handled = await settings_mod.dispatch(
        _Ws(),
        {"type": "settings.patch", "patch": {"memory.inject_budget_chars": 999}},
        cfg, engine,
    )
    assert handled is True
    assert engine.refreshes == 1


@pytest.mark.asyncio
async def test_patching_an_unrelated_setting_does_not_refresh():
    cfg = _ActiveCfg()
    engine = _Engine()
    await settings_mod.dispatch(
        _Ws(), {"type": "settings.patch", "patch": {"style.locale": "ja"}}, cfg, engine,
    )
    assert engine.refreshes == 0


@pytest.mark.asyncio
async def test_set_active_without_an_engine_still_succeeds():
    cfg = _ActiveCfg()
    handled = await settings_mod.dispatch(
        _Ws(), {"type": "llm.set_active", "provider_id": "p1"}, cfg,
    )
    assert handled is True
