# skills — reviewed local skill execution

> Language: [中文](skills.md) | English · Back to [module index](README.en.md)

A security pipeline for locally installed "skills": static review → LLM judge → signed approval marker → sandboxed subprocess execution.

| File | Description |
|---|---|
| `reviewer.py` | Static scanning (file-type allowlist, magic bytes, size caps, DENY/WARN patterns). |
| `llm_review.py` | LLM security judge (treats all skill material as untrusted data). |
| `safe_marker.py` | Writes/verifies a signed `Safe.txt` marker (content hash bound to path hash; authenticated encryption with AAD). |
| `keys.py` | Generates and persists the signing keys. |
| `gate.py` | Gating API for tools and MCP: `gate_skill()`, `gate_skill_read_path()`, `gate_mcp()`. |
| `runtime.py` | `run_python_skill()`: runs a skill in a scrubbed subprocess env (allowlist + strip API_KEY/TOKEN/SECRET/AUTH). |
| `egress.py` | Network egress policy: detects URLs and curl/wget/Invoke-WebRequest in commands and checks them against config. |
| `redaction.py` | Scrubs secrets (`sk-*`, `AKIA*`, `ghp_*`, long base64) from tool output. |
| `memory_sanitize.py` | Prompt-injection sanitizer for content entering memory. |
