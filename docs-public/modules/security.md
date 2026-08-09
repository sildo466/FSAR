# security — 安全层

> 语言：中文 | [English](security.en.md) · 返回 [模块索引](README.md)

执行前风险评分、权限持久化、用户确认、只追加审计，外加 WS 鉴权与执行后结果复核。

| 文件 | 说明 |
|---|---|
| `risk.py` | `RiskEngine.evaluate(tool, args) → RiskVerdict`，等级 SAFE→CRITICAL；在 `Tool.execute()` 之前运行。 |
| `permissions.py` | `PermissionState` + 读写 `permissions.yaml`；会话信任、按 MCP 服务器信任、永久拒绝、`no_trust_mode`。 |
| `confirmation.py` | CLI 确认提示（GUI 对应 `server/risk_bridge.py`）；默认拒绝。 |
| `audit.py` | 只追加 JSON-lines 审计日志，每条工具决策一行。 |
| `small_agent_review.py` | 小模型安全分类器，复核**已完成**工具调用的结果（`safe` / `unsafe: <reason>`）。 |
| `ws_auth.py` | HMAC 签名的 WS 令牌 + Origin/Host 白名单 + 限流。 |
