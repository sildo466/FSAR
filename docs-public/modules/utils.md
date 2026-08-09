# utils — 横切基础设施

> 语言：中文 | [English](utils.en.md) · 返回 [模块索引](README.md)

| 文件 | 说明 |
|---|---|
| `fsar_config.py` | `FsarConfig`：统一配置加载与原子写入（`fsar.yaml` 唯一访问器）。 |
| `config.py` | 已弃用的薄壳，转发到 `FsarConfig`。 |
| `fsar_home.py` | `get_fsar_home()`：`$FSAR_HOME` 或 `~/.fsar`。 |
| `llm_factory.py` | 共享 LLM 客户端工厂 + 缓存拦截 + 提供商 prompt-cache 标记。 |
| `llm_cache.py` | 两级 LLM 响应缓存（`llm_cache.db`）。 |
| `anthropic_cache.py` / `gemini_cache.py` | Anthropic prompt-cache / Gemini `cachedContents` provider 侧缓存。 |
| `responses_compat.py` | OpenAI Chat 与 Responses API 形状互转。 |
| `render.py` | CLI 的 Rich 终端渲染。 |
| `migrate.py` + `migrations/` | 把仓库内 config/data 迁入 FSAR home；带日期的 schema 迁移。 |
