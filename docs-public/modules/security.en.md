# security — the security layer

> Language: [中文](security.md) | English · Back to [module index](README.en.md)

Pre-execution risk scoring, permission persistence, user confirmation, append-only audit, plus WS auth, a post-execution result reviewer, content screening with quarantine, and the credential and rate-limiting stack that fronts the LAN room surface.

| File | Description |
|---|---|
| `risk.py` | `RiskEngine.evaluate(tool, args) → RiskVerdict`, levels SAFE→CRITICAL; runs before `Tool.execute()`. |
| `permissions.py` | `PermissionState` + read/write of `permissions.yaml`; session trust, per-MCP-server trust, permanent denies, `no_trust_mode`. |
| `confirmation.py` | The CLI confirmation prompt (GUI equivalent: `server/risk_bridge.py`); default-deny. |
| `audit.py` | Append-only JSON-lines audit log, one line per tool decision. |
| `small_agent_review.py` | Small-LLM security classifier that reviews a *completed* tool call's result (`safe` / `unsafe: <reason>`). |
| `ws_auth.py` | HMAC-signed WS tokens + Origin/Host allowlist + rate limiting. |
| `content_screen.py` | Model-based prompt-injection screening for persisted content — judges "normal roleplay" against "an instruction aimed at the model". Runs on a background thread, so conversation is never blocked. |
| `content_guard.py` | Quarantine and whitelist bookkeeping for screening: a flagged item leaves its store, and restoring it allowlists its hash so it is skipped from then on. |
| `visitor_screen.py` | Judging what an external visitor says in a room. |
| `member_auth.py` | The single place that decides whether a room credential may be used — expiry, first-use address binding, scope. |
| `rate_budget.py` | Token buckets with a bounded key table, so the LAN surface cannot be flooded. |
| `lan_tls.py` | Self-signed TLS material for the LAN room listener, with host SANs. |

The stores behind the LAN surface live under `src/memory/`: `agent_members.py` (room membership), `member_tokens.py` (hashed credentials), `lan_blocklist.py` (global address blocklist), and `auth_audit.py` (append-only identity audit).
