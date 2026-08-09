from src.social.adapters.telegram import TelegramAdapter


def test_status_initially_paused():
    adapter = TelegramAdapter("placeholder")
    assert adapter.status()["state"] == "paused"
    assert adapter.name == "telegram"
