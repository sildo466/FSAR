# providers — LLM / ASR / TTS adapters

> Language: [中文](providers.md) | English · Back to [module index](README.en.md)

A uniform adapter-plus-dispatch structure for three modalities; presets ship in `data/presets/`.

| Dir | Description |
|---|---|
| `llm/` | `presets.py`, `deepseek.py`, `google.py` (Gemini native REST), `thinking.py` (thinking-effort mapping). Generic OpenAI-compatible goes through `utils/llm_factory.py`. |
| `asr/` | `dispatch.py` + `adapters/` (faster_whisper, openai_compat, volcengine). |
| `tts/` | `dispatch.py` (selection/caching/retry) + `cache.py` (`tts_cache.db`) + `adapters/` (azure, dashscope, edge, elevenlabs, minimax, openai_compat, volcengine). |
| `pricing.py` | Model pricing tables and cost estimation (feeds the Usage page). |
