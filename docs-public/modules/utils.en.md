# utils — cross-cutting infrastructure

> Language: [中文](utils.md) | English · Back to [module index](README.en.md)

| File | Description |
|---|---|
| `fsar_config.py` | `FsarConfig`: unified config loader and atomic writer (the single accessor for `fsar.yaml`). |
| `config.py` | Deprecated thin shim forwarding to `FsarConfig`. |
| `fsar_home.py` | `get_fsar_home()`: `$FSAR_HOME` or `~/.fsar`. |
| `llm_factory.py` | Shared LLM client factory: client construction, connect/read timeouts, provider prompt-cache markers, and usage normalization. |
| `anthropic_cache.py` / `gemini_cache.py` | Anthropic prompt-cache / Gemini `cachedContents` provider-side caches. `llm_cache.db` holds their bookkeeping — there is no local response cache. |
| `responses_compat.py` | Conversions between OpenAI Chat and Responses API shapes. |
| `render.py` | Rich-based terminal rendering for the CLI. |
| `migrate.py` + `migrations/` | Relocates repo-local config/data into FSAR home; dated schema migrations. |
| `version.py` | Resolves the app version from the git tag at HEAD, falling back to `pyproject.toml`; parses the channel and compares tags. |
