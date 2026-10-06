# security — 安全层

> 语言：中文 | [English](security.en.md) · 返回 [模块索引](README.md)

执行前风险评分、权限持久化、用户确认、只追加审计，外加 WS 鉴权、执行后结果复核、带隔离的内容筛查，以及挡在局域网房间面前的那套凭证与限流设施。

| 文件 | 说明 |
|---|---|
| `risk.py` | `RiskEngine.evaluate(tool, args) → RiskVerdict`，等级 SAFE→CRITICAL；在 `Tool.execute()` 之前运行。 |
| `permissions.py` | `PermissionState` + 读写 `permissions.yaml`；会话信任、按 MCP 服务器信任、永久拒绝、`no_trust_mode`。 |
| `confirmation.py` | CLI 确认提示（GUI 对应 `server/risk_bridge.py`）；默认拒绝。 |
| `audit.py` | 只追加 JSON-lines 审计日志，每条工具决策一行。 |
| `small_agent_review.py` | 小模型安全分类器，复核**已完成**工具调用的结果（`safe` / `unsafe: <reason>`）。 |
| `ws_auth.py` | HMAC 签名的 WS 令牌 + Origin/Host 白名单 + 限流。 |
| `content_screen.py` | 对已存内容做模型级提示词注入筛查——判"正常角色扮演"与"针对模型的指令"之别。跑在后台线程，因此对话永远不会被卡住。 |
| `content_guard.py` | 筛查的隔离与白名单记账：被标记的条目离开原存储，恢复它会给其哈希加白名单，此后跳过。 |
| `visitor_screen.py` | 判断房间里外部访客说了什么。 |
| `member_auth.py` | 判断某项房间凭证是否可用的唯一位置——有效期、首次使用的地址绑定、权限范围。 |
| `rate_budget.py` | 带有限键表的令牌桶，让局域网面不会被刷爆。 |
| `lan_tls.py` | 给局域网房间监听用的自签名 TLS 材料，带 host SAN。 |

局域网面背后的存储位于 `src/memory/`：`agent_members.py`（房间成员）、`member_tokens.py`（哈希后的凭证）、`lan_blocklist.py`（全局地址黑名单）、`auth_audit.py`（只追加身份审计）。
