# security — the security layer

> Language: [中文](security.md) | English · Back to [module index](README.en.md)

Pre-execution risk scoring, permission persistence, user confirmation, append-only audit, plus WS auth and a post-execution result reviewer.

| File | Description |
|---|---|
| `risk.py` | `RiskEngine.evaluate(tool, args) → RiskVerdict`, levels SAFE→CRITICAL; runs before `Tool.execute()`. |
| `permissions.py` | `PermissionState` + read/write of `permissions.yaml`; session trust, per-MCP-server trust, permanent denies, `no_trust_mode`. |
| `confirmation.py` | The CLI confirmation prompt (GUI equivalent: `server/risk_bridge.py`); default-deny. |
| `audit.py` | Append-only JSON-lines audit log, one line per tool decision. |
| `small_agent_review.py` | Small-LLM security classifier that reviews a *completed* tool call's result (`safe` / `unsafe: <reason>`). |
| `ws_auth.py` | HMAC-signed WS tokens + Origin/Host allowlist + rate limiting. |
