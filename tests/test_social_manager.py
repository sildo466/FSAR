from src.social.manager import build_router_and_adapters


def test_manager_returns_empty_when_all_disabled(monkeypatch):
    monkeypatch.setattr("src.social.manager._load_config", lambda: {})

    router, adapters = build_router_and_adapters()

    assert router is not None
    assert adapters == []


def test_manager_builds_wechat_for_qr_login(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "src.social.manager._load_config",
        lambda: {"wechat": {"enabled": True}},
    )
    monkeypatch.setattr(
        "src.social.adapters.wechat._TOKEN_PATH",
        tmp_path / "wechat.json",
    )

    _, adapters = build_router_and_adapters()

    assert [adapter.name for adapter in adapters] == ["wechat"]
    assert adapters[0].status()["login_required"] is True
