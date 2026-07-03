"""FSAR 配置管理"""

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

# 项目根目录
ROOT_DIR = Path(__file__).parent.parent.parent
CONFIG_DIR = ROOT_DIR / "config"
DATA_DIR = ROOT_DIR / "data"


class Config:
    """FSAR 配置管理器"""

    def __init__(self, config_path: str | Path | None = None):
        self._config_path = Path(config_path) if config_path else CONFIG_DIR / "settings.yaml"
        self._permissions_path = CONFIG_DIR / "permissions.yaml"
        self._settings: dict = {}
        self._permissions: dict = {}
        self._load()

    def _load(self):
        """加载配置文件"""
        # 加载 settings.yaml
        if self._config_path.exists():
            with open(self._config_path, "r", encoding="utf-8") as f:
                self._settings = yaml.safe_load(f) or {}
        else:
            self._settings = {}

        # 加载 permissions.yaml
        if self._permissions_path.exists():
            with open(self._permissions_path, "r", encoding="utf-8") as f:
                self._permissions = yaml.safe_load(f) or {}
        else:
            self._permissions = {}

        # 解析环境变量
        self._resolve_env_vars(self._settings)

    def _resolve_env_vars(self, obj: Any) -> Any:
        """递归解析 ${ENV_VAR} 格式的环境变量"""
        if isinstance(obj, dict):
            for key, value in obj.items():
                obj[key] = self._resolve_env_vars(value)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                obj[i] = self._resolve_env_vars(item)
        elif isinstance(obj, str) and obj.startswith("${") and obj.endswith("}"):
            env_name = obj[2:-1]
            return os.environ.get(env_name, "")
        return obj

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值，支持点号分隔的路径"""
        keys = key.split(".")
        value = self._settings
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
            if value is None:
                return default
        return value

    def get_permission(self, category: str, operation: str) -> str:
        """获取权限配置，返回 'ask' / 'trust' / 'deny'"""
        cat = self._permissions.get(category, {})
        return cat.get(operation, "ask")

    def get_llm_config(self, model_name: str = "primary") -> dict:
        """获取 LLM 配置"""
        return self.get(f"llm.{model_name}", {})

    @property
    def memory_sqlite_path(self) -> str:
        return self.get("memory.sqlite_path", "data/memory.db")

    @property
    def short_term_window(self) -> int:
        return self.get("memory.short_term_window", 50)

    @property
    def reflection_intensity(self) -> str:
        return self.get("memory.reflection_intensity", "medium")

    @property
    def reflection_interval_hours(self) -> float:
        return float(self.get("memory.reflection_interval_hours", 12))

    @property
    def llm_cache_enabled(self) -> bool:
        return bool(self.get("llm.cache.enabled", True))

    @property
    def llm_cache_db_path(self) -> str:
        return self.get("llm.cache.db_path", "data/llm_cache.db")

    @property
    def llm_cache_l1_max_entries(self) -> int:
        return int(self.get("llm.cache.l1_max_entries", 256))

    @property
    def llm_cache_l1_ttl_seconds(self) -> float:
        return float(self.get("llm.cache.l1_ttl_seconds", 300))

    @property
    def llm_cache_l2_ttl_seconds(self) -> float:
        return float(self.get("llm.cache.l2_ttl_seconds", 86400))

    @property
    def llm_cache_retention(self) -> str:
        return str(self.get("llm.cache.retention", "short"))

    @property
    def llm_cache_skip_vision(self) -> bool:
        return bool(self.get("llm.cache.skip_vision", True))

    @property
    def llm_cache_use_responses_api(self) -> bool:
        return bool(self.get("llm.cache.use_responses_api", True))

    @property
    def llm_cache_session_id(self) -> str:
        return str(self.get("llm.cache.session_id", "")).strip()

    @property
    def gui_host(self) -> str:
        return self.get("gui.host", "127.0.0.1")

    @property
    def gui_port(self) -> int:
        return self.get("gui.port", 8765)

    def reload(self):
        """重新加载配置"""
        self._load()


# 全局配置实例
_config: Config | None = None


def get_config() -> Config:
    """获取全局配置实例"""
    global _config
    if _config is None:
        _config = Config()
    return _config
