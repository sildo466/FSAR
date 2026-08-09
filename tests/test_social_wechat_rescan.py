import json

import pytest

from src.social.adapters.wechat import WeChatAdapter


def _adapter(tmp_path, monkeypatch, **kwargs):
    monkeypatch.setattr(
        "src.social.adapters.wechat._TOKEN_PATH",
        tmp_path / "wechat.json",
    )
    return WeChatAdapter(**kwargs)


def _stub_api(adapter, monkeypatch, qr_response, status_response):
    async def fake_get(base_url, endpoint):
        if "get_bot_qrcode" in endpoint:
            return qr_response
        return status_response

    monkeypatch.setattr(adapter, "_api_get", fake_get)


def _logged_in(tmp_path, monkeypatch):
    adapter = _adapter(tmp_path, monkeypatch)
    adapter._account_id = "old-bot"
    adapter._token = "old-token"
    adapter._store.set_credentials(
        {
            "account_id": "old-bot",
            "bot_token": "old-token",
            "base_url": "https://old.example",
            "user_id": "old-user",
        }
    )
    adapter._store.set_sync_buf("old-cursor")
    adapter._store.set_context_token("peer-1", "old-context")
    return adapter


async def test_reset_qr_login_keeps_session_until_confirmed(tmp_path, monkeypatch):
    adapter = _logged_in(tmp_path, monkeypatch)
    _stub_api(
        adapter,
        monkeypatch,
        {"qrcode": "qr-2", "qrcode_img_content": "scan-2"},
        {"status": "wait"},
    )

    result = await adapter.reset_qr_login()

    assert result["scan_data"] == "scan-2"
    assert adapter.status()["account_id"] == "old-bot"
    assert adapter.status()["login_required"] is False
    assert adapter._store.sync_buf() == "old-cursor"
    assert adapter._store.context_token("peer-1") == "old-context"


async def test_expired_rescan_leaves_original_session(tmp_path, monkeypatch):
    adapter = _logged_in(tmp_path, monkeypatch)
    _stub_api(
        adapter,
        monkeypatch,
        {"qrcode": "qr-2", "qrcode_img_content": "scan-2"},
        {"status": "expired"},
    )
    await adapter.reset_qr_login()

    assert (await adapter.check_qr_login())["status"] == "expired"
    assert adapter._store.credentials()["bot_token"] == "old-token"
    assert adapter._store.sync_buf() == "old-cursor"
    assert adapter._store.context_token("peer-1") == "old-context"


async def test_rescan_to_new_account_clears_stale_account_state(tmp_path, monkeypatch):
    adapter = _logged_in(tmp_path, monkeypatch)
    _stub_api(
        adapter,
        monkeypatch,
        {"qrcode": "qr-2", "qrcode_img_content": "scan-2"},
        {
            "status": "confirmed",
            "ilink_bot_id": "new-bot",
            "bot_token": "new-token",
            "baseurl": "https://new.example",
            "ilink_user_id": "new-user",
        },
    )
    await adapter.reset_qr_login()

    assert (await adapter.check_qr_login())["account_id"] == "new-bot"
    assert adapter._store.credentials()["bot_token"] == "new-token"
    assert adapter._store.sync_buf() == ""
    assert adapter._store.context_token("peer-1") is None


async def test_rescan_same_account_preserves_cursor(tmp_path, monkeypatch):
    adapter = _logged_in(tmp_path, monkeypatch)
    _stub_api(
        adapter,
        monkeypatch,
        {"qrcode": "qr-2", "qrcode_img_content": "scan-2"},
        {
            "status": "confirmed",
            "ilink_bot_id": "old-bot",
            "bot_token": "refreshed-token",
            "baseurl": "https://old.example",
            "ilink_user_id": "old-user",
        },
    )
    await adapter.reset_qr_login()

    assert (await adapter.check_qr_login())["account_id"] == "old-bot"
    assert adapter._store.credentials()["bot_token"] == "refreshed-token"
    assert adapter._store.sync_buf() == "old-cursor"
    assert adapter._store.context_token("peer-1") == "old-context"


async def test_first_time_confirm_is_unaffected_by_replacing_flag(tmp_path, monkeypatch):
    adapter = _adapter(tmp_path, monkeypatch)
    _stub_api(
        adapter,
        monkeypatch,
        {"qrcode": "qr-1", "qrcode_img_content": "scan-1"},
        {
            "status": "confirmed",
            "ilink_bot_id": "bot-1",
            "bot_token": "token-1",
            "baseurl": "https://one.example",
            "ilink_user_id": "user-1",
        },
    )
    await adapter.begin_qr_login()

    assert (await adapter.check_qr_login())["account_id"] == "bot-1"
    assert adapter._store.credentials()["bot_token"] == "token-1"
