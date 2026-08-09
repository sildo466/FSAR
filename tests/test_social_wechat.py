from src.social.adapters.wechat import WeChatAdapter, _extract_text


def test_status_initially_paused(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "src.social.adapters.wechat._TOKEN_PATH",
        tmp_path / "wechat.json",
    )
    adapter = WeChatAdapter()
    assert adapter.status()["state"] == "paused"
    assert adapter.status()["login_required"] is True
    assert adapter.name == "wechat"


def test_extracts_only_text_items():
    message = {
        "item_list": [
            {"type": 2, "image_item": {}},
            {"type": 1, "text_item": {"text": "hello"}},
        ]
    }
    assert _extract_text(message) == "hello"
