# skills — 受审阅的本地技能执行

> 语言：中文 | [English](skills.en.md) · 返回 [模块索引](README.md)

本地"技能"的安全流水线：静态审阅 → LLM 评判 → 签名批准标记 → 沙盒子进程执行。

| 文件 | 说明 |
|---|---|
| `reviewer.py` | 静态扫描（文件类型白名单、magic bytes、大小上限、DENY/WARN 模式）。 |
| `llm_review.py` | LLM 安全评判器（把技能材料一律视为不可信数据）。 |
| `safe_marker.py` | 写入/校验签名的 `Safe.txt` 标记（内容哈希绑定路径哈希，带 AAD 的认证加密）。 |
| `keys.py` | 生成并持久化签名密钥。 |
| `gate.py` | 工具与 MCP 使用的门禁 API：`gate_skill()`、`gate_skill_read_path()`、`gate_mcp()`。 |
| `runtime.py` | `run_python_skill()`：在剥离子进程环境中执行（白名单 + 剥离 API_KEY/TOKEN/SECRET/AUTH）。 |
| `egress.py` | 网络出口策略：检测命令中的 URL 与 curl/wget/Invoke-WebRequest 并按配置放行。 |
| `redaction.py` | 从工具输出中擦除密钥（`sk-*`、`AKIA*`、`ghp_*`、长 base64）。 |
| `memory_sanitize.py` | 进入记忆前的提示注入净化。 |
