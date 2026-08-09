# providers — LLM / ASR / TTS 适配器

> 语言：中文 | [English](providers.en.md) · 返回 [模块索引](README.md)

三种模态统一的"适配器 + 分发"结构；预设随 `data/presets/` 发布。

| 目录 | 说明 |
|---|---|
| `llm/` | `presets.py`、`deepseek.py`、`google.py`（Gemini 原生 REST）、`thinking.py`（思考强度映射）。通用 OpenAI 兼容走 `utils/llm_factory.py`。 |
| `asr/` | `dispatch.py` + `adapters/`（faster_whisper、openai_compat、volcengine）。 |
| `tts/` | `dispatch.py`（选择/缓存/重试）+ `cache.py`（`tts_cache.db`）+ `adapters/`（azure、dashscope、edge、elevenlabs、minimax、openai_compat、volcengine）。 |
| `pricing.py` | 模型定价表与成本估算（供 Usage 页）。 |
