"""FSAR 日志配置"""

import sys
from loguru import logger

# 移除默认 handler
logger.remove()

# 控制台输出 — 带颜色
logger.add(
    sys.stderr,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan> - {message}",
    level="INFO",
    colorize=True,
)

# 文件输出 — 滚动日志
logger.add(
    "data/logs/fsar_{time:YYYY-MM-DD}.log",
    rotation="00:00",
    retention="30 days",
    level="DEBUG",
    encoding="utf-8",
)

__all__ = ["logger"]
