import ssl

import httpx

from src.social.adapters.wechat import WeChatAdapter


def _adapter(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "src.social.adapters.wechat._TOKEN_PATH",
        tmp_path / "wechat.json",
    )
    return WeChatAdapter()


def test_client_verifies_against_system_trust_store(tmp_path, monkeypatch):
    """httpx defaults to the certifi bundle, which omits locally installed CAs.

    On machines behind a TLS-terminating proxy that breaks every iLink call with
    CERTIFICATE_VERIFY_FAILED, so the adapter must supply its own context.
    """
    captured: dict = {}
    real_client = httpx.AsyncClient

    def spy(*args, **kwargs):
        captured.update(kwargs)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", spy)
    adapter = _adapter(tmp_path, monkeypatch)

    adapter._ensure_client()

    assert isinstance(captured.get("verify"), ssl.SSLContext)


def test_client_trust_store_includes_local_authorities(tmp_path, monkeypatch):
    captured: dict = {}
    real_client = httpx.AsyncClient

    def spy(*args, **kwargs):
        captured.update(kwargs)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", spy)
    adapter = _adapter(tmp_path, monkeypatch)

    adapter._ensure_client()

    context = captured["verify"]
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.get_ca_certs(), "context loaded no certificate authorities"
