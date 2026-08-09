from src.server.handlers.settings import _validated_social_patch
from src.utils.fsar_config import FsarConfig


def _config(tmp_path):
    return FsarConfig(tmp_path / "fsar.yaml")


def test_validate_social_passes_when_disabled(tmp_path):
    patch = {"social.telegram.enabled": False}
    _, error = _validated_social_patch(patch, _config(tmp_path))
    assert error is None


def test_validate_social_rejects_enabled_telegram_without_token(tmp_path):
    patch = {"social.telegram.enabled": True}
    _, error = _validated_social_patch(patch, _config(tmp_path))
    assert error == "social.telegram.bot_token is required when enabled"


def test_validate_social_passes_enabled_feishu_with_webhook_credentials(tmp_path):
    patch = {
        "social.feishu.enabled": True,
        "social.feishu.app_id": "cli_x",
        "social.feishu.app_secret": "secret",
        "social.feishu.verification_token": "verify",
    }
    _, error = _validated_social_patch(patch, _config(tmp_path))
    assert error is None


def test_validate_social_allows_wechat_to_enter_qr_login(tmp_path):
    patch = {"social.wechat.enabled": True}
    _, error = _validated_social_patch(patch, _config(tmp_path))
    assert error is None
