# SPDX-License-Identifier: MIT
"""WS dispatcher for Settings + LLM provider selection."""

from __future__ import annotations

from typing import Any

from fastapi import WebSocket

from src.core.agent_tiers import is_valid_tier
from src.providers.llm.thinking import EFFORT_LEVELS
from src.security.permissions import PathRule, save_permissions
from src.utils.fsar_config import FsarConfig

_VALID_PERM_MODES = {"strict", "normal", "trust"}
_VALID_TOOL_MODES = {"ask", "trust", "deny"}
_VALID_RULE_ACTIONS = {"deny", "ask"}

_SPEECH_PATHS = {
    "tts.active",
    "tts.autoplay",
    "tts.default_voice",
    "tts.providers",
    "asr.active",
    "asr.language",
    "asr.providers",
}

_SOCIAL_PATHS = {
    "social.telegram.enabled",
    "social.telegram.bot_token",
    "social.feishu.enabled",
    "social.feishu.app_id",
    "social.feishu.app_secret",
    "social.feishu.verification_token",
    "social.feishu.encrypt_key",
    "social.wechat.enabled",
    "social.wechat.account_id",
    "social.wechat.bot_token",
    "social.wechat.base_url",
    "social.wechat.character_card_id",
    "social.wechat.user_card_id",
}

_LOCALES = {"en", "zh-Hans", "zh-Hant", "ja", "de", "fr"}


async def dispatch(ws: WebSocket, msg: dict[str, Any], config: FsarConfig, engine: Any = None) -> bool:
    t = msg.get("type")
    if t == "settings.get":
        await ws.send_json({"type": "snapshot", "config": config._settings})
        return True
    if t == "settings.patch":
        raw_patch = msg.get("patch") or {}
        if not isinstance(raw_patch, dict):
            await ws.send_json({"type": "error", "code": "bad_patch", "recoverable": True})
            return True
        patch, speech_error = _validated_speech_patch(raw_patch, config)
        if speech_error:
            await ws.send_json({
                "type": "error",
                "code": "bad_speech_setting",
                "message": speech_error,
                "recoverable": True,
            })
            return True
        patch, social_error = _validated_social_patch(patch, config)
        if social_error:
            await ws.send_json({
                "type": "error",
                "code": "bad_social_setting",
                "message": social_error,
                "recoverable": True,
            })
            return True
        if "agent.tier" in patch and not is_valid_tier(patch["agent.tier"]):
            await ws.send_json({
                "type": "error",
                "code": "bad_agent_tier",
                "message": str(patch["agent.tier"]),
                "recoverable": True,
            })
            return True
        if "agent.tier" in patch:
            patch["agent.tier"] = str(patch["agent.tier"]).strip().lower()
        if "llm.model_thinking_effort" in patch:
            effort_value = patch["llm.model_thinking_effort"]
            if (
                not isinstance(effort_value, str)
                or effort_value.strip().lower() not in EFFORT_LEVELS
            ):
                await ws.send_json({
                    "type": "error",
                    "code": "bad_model_thinking_effort",
                    "message": str(effort_value),
                    "recoverable": True,
                })
                return True
            patch["llm.model_thinking_effort"] = effort_value.strip().lower()
        for key, value in patch.items():
            if not isinstance(key, str) or not key:
                continue
            config.patch(key, value)
        try:
            config.save()
        except Exception:
            pass
        await ws.send_json({"type": "settings.changed", "patch": patch, "by": "user"})
        return True
    if t == "style.patch":
        patch = msg.get("patch") or {}
        if not isinstance(patch, dict):
            await ws.send_json({"type": "error", "code": "bad_patch", "recoverable": True})
            return True
        for key, value in patch.items():
            if not isinstance(key, str) or not key:
                continue
            full = f"style.{key}" if not key.startswith("style.") else key
            config.patch(full, value)
        try:
            config.save()
        except Exception:
            pass
        style = config.get("style", {})
        await ws.send_json({"type": "style.changed", "style": style})
        return True
    if t == "style.set_theme":
        theme = msg.get("theme", "")
        if theme not in {"light", "dark", "system"}:
            await ws.send_json({"type": "error", "code": "bad_theme", "message": theme, "recoverable": True})
            return True
        config.patch("style.theme", theme)
        try:
            config.save()
        except Exception:
            pass
        style = config.get("style", {})
        await ws.send_json({"type": "style.changed", "style": style, "by": "theme"})
        return True
    if t == "style.set_locale":
        locale = msg.get("locale", "")
        if locale not in _LOCALES:
            await ws.send_json({
                "type": "error",
                "code": "bad_locale",
                "message": str(locale),
                "recoverable": True,
            })
            return True
        config.patch("style.locale", locale)
        try:
            config.save()
        except Exception:
            pass
        style = config.get("style", {})
        await ws.send_json({"type": "style.changed", "style": style, "by": "locale"})
        return True
    if t == "permissions.patch":
        patch = msg.get("patch") or {}
        if not isinstance(patch, dict):
            await ws.send_json({"type": "error", "code": "bad_patch", "recoverable": True})
            return True
        perm_error = _sync_permissions_to_engine(patch, engine)
        if perm_error:
            await ws.send_json({
                "type": "error",
                "code": "bad_permission",
                "message": perm_error,
                "recoverable": True,
            })
            return True
        for key, value in patch.items():
            if not isinstance(key, str) or not key:
                continue
            config.patch(key, value)
        try:
            config.save()
        except Exception:
            pass
        await ws.send_json({"type": "settings.changed", "patch": patch, "by": "permissions"})
        return True
    if t == "llm.set_active":
        provider_id = msg.get("provider_id", "")
        if not provider_id:
            await ws.send_json({"type": "error", "code": "no_provider_id", "recoverable": True})
            return True
        config.set_active_provider(provider_id)
        try:
            config.save()
        except Exception:
            pass
        active = config.get_active_provider()
        await ws.send_json({
            "type": "llm.provider_changed",
            "provider_id": provider_id,
            "model": active.get("model", ""),
        })
        try:
            from src.utils.llm_factory import reset_clients
            reset_clients()
        except Exception:
            pass
        return True
    if t == "llm.get_vision":
        vm = config.get_vision_model()
        await ws.send_json({"type": "llm.vision_config", "vision_model": vm})
        return True
    if t == "llm.set_vision":
        cfg = {
            "base_url": str(msg.get("base_url", "") or ""),
            "api_key": str(msg.get("api_key", "") or ""),
            "model": str(msg.get("model", "") or ""),
        }
        config.set_vision_model(cfg)
        try:
            config.save()
        except Exception:
            pass
        await ws.send_json({"type": "llm.vision_changed", "vision_model": config.get_vision_model()})
        return True
    return False


def _sync_permissions_to_engine(patch: dict[str, Any], engine: Any) -> str | None:
    """Mirror permissions.* patch keys into the live PermissionState that the
    RiskEngine evaluates against, then persist it to permissions.yaml.

    The config copy keeps feeding the UI round-trip; the engine copy is what
    tool-call evaluation actually reads. Returns an error string on invalid
    values, None on success (including a no-op when no engine is attached).
    """
    if engine is None or not hasattr(engine, "permissions"):
        return None
    state = engine.permissions
    touched = False
    for key, value in patch.items():
        if not isinstance(key, str):
            continue
        if key == "permissions.mode":
            if value not in _VALID_PERM_MODES:
                return f"invalid permission mode: {value}"
            state.mode = value
            touched = True
        elif key.startswith("permissions.tools.") and key.endswith(".mode"):
            tool_name = key[len("permissions.tools."):-len(".mode")]
            if not tool_name or value not in _VALID_TOOL_MODES:
                return f"invalid tool mode: {value}"
            tool_cfg = state.tools.setdefault(tool_name, {"risk": "MEDIUM"})
            tool_cfg["mode"] = value
            touched = True
        elif key == "permissions.path_rules":
            if not isinstance(value, list):
                return "path_rules must be a list"
            rules: list[PathRule] = []
            for item in value:
                pattern = item.get("pattern") if isinstance(item, dict) else None
                if not isinstance(pattern, str) or not pattern:
                    return "path rule pattern must be a non-empty string"
                action = item.get("mode") or item.get("action") or "ask"
                if action not in _VALID_RULE_ACTIONS:
                    return f"invalid path rule action: {action}"
                try:
                    rules.append(PathRule(pattern=pattern, action=str(action)))
                except Exception:
                    return f"invalid path rule pattern: {pattern}"
            state.path_rules = rules
            touched = True
    if touched:
        try:
            save_permissions(state)
        except Exception:
            pass
    return None


def _validated_speech_patch(
    patch: dict[str, Any],
    config: FsarConfig,
) -> tuple[dict[str, Any], str | None]:
    filtered = {
        key: value
        for key, value in patch.items()
        if not (
            isinstance(key, str)
            and key.startswith(("tts.", "asr."))
            and key not in _SPEECH_PATHS
        )
    }
    for key in ("tts.providers", "asr.providers"):
        if key not in filtered:
            continue
        providers = filtered[key]
        if not isinstance(providers, list):
            return filtered, f"{key} must be a list"
        ids = [
            item.get("id")
            for item in providers
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        ]
        if len(ids) != len(providers) or any(not provider_id for provider_id in ids):
            return filtered, f"{key} entries require non-empty string ids"
        if len(ids) != len(set(ids)):
            return filtered, f"{key} ids must be unique"
    expected_types = {
        "tts.active": str,
        "tts.autoplay": bool,
        "tts.default_voice": str,
        "asr.active": str,
        "asr.language": str,
    }
    for key, expected in expected_types.items():
        if key in filtered and not isinstance(filtered[key], expected):
            return filtered, f"{key} must be {expected.__name__}"
    for prefix in ("tts", "asr"):
        active_key = f"{prefix}.active"
        if active_key not in filtered or filtered[active_key] == "":
            continue
        providers = filtered.get(
            f"{prefix}.providers", config.get(f"{prefix}.providers", []) or []
        )
        provider_ids = {
            item.get("id") for item in providers if isinstance(item, dict)
        }
        if filtered[active_key] not in provider_ids:
            return filtered, f"{active_key} must reference a configured provider"
    return filtered, None


def _validated_social_patch(
    patch: dict[str, Any],
    config: FsarConfig,
) -> tuple[dict[str, Any], str | None]:
    for key in patch:
        if isinstance(key, str) and key.startswith("social.") and key not in _SOCIAL_PATHS:
            return patch, f"unsupported social setting: {key}"

    for key in _SOCIAL_PATHS:
        if key not in patch:
            continue
        value = patch[key]
        if key.endswith(".enabled"):
            if not isinstance(value, bool):
                return patch, f"{key} must be bool"
        elif key in (
            "social.wechat.character_card_id",
            "social.wechat.user_card_id",
        ):
            if value is not None and not isinstance(value, int):
                return patch, f"{key} must be int or null"
        elif not isinstance(value, str):
            return patch, f"{key} must be str"

    def effective(key: str) -> Any:
        return patch[key] if key in patch else config.get(key)

    if effective("social.telegram.enabled"):
        token = effective("social.telegram.bot_token")
        if not isinstance(token, str) or not token.strip():
            return patch, "social.telegram.bot_token is required when enabled"

    if effective("social.feishu.enabled"):
        required = (
            "social.feishu.app_id",
            "social.feishu.app_secret",
            "social.feishu.verification_token",
        )
        missing = [
            key
            for key in required
            if not isinstance(effective(key), str) or not effective(key).strip()
        ]
        if missing:
            return patch, f"{', '.join(missing)} required when enabled"

    return patch, None
