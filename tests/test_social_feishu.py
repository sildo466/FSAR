import json

from src.social.adapters.feishu import FeishuAdapter


def test_status_initially_paused():
    adapter = FeishuAdapter("cli_xxx", "secret", "verify-token")
    assert adapter.status()["state"] == "paused"
    assert adapter.name == "feishu"


def test_webhook_url_verification():
    adapter = FeishuAdapter("cli_xxx", "secret", "verify-token")
    body = json.dumps(
        {
            "type": "url_verification",
            "token": "verify-token",
            "challenge": "challenge-value",
        }
    ).encode()

    response = adapter.handle_webhook(body, {}, "/api/social/feishu/webhook")

    assert response.status_code == 200
    assert json.loads(response.content) == {"challenge": "challenge-value"}
