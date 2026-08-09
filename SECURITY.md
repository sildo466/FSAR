# Security Policy

FSAR is a local-first AI companion that executes real tools — shell commands,
file operations, and (optionally) desktop computer-use — on the user's own
machine, driven by an LLM. Because an LLM can be wrong or be manipulated, FSAR
treats every model-driven action as untrusted input and wraps it in layered,
fail-closed guards. This document explains how to report a vulnerability and
describes the security model so contributors know what they are protecting.

## Reporting a vulnerability

**Do not report security vulnerabilities through public GitHub Issues or Pull
Requests.** Public disclosure before a fix puts every user at risk.

Report privately through **GitHub Security Advisories** (preferred):

> <https://github.com/sildo466/FSAR/security/advisories/new>

This opens a private channel visible only to you and the maintainers.

If you prefer email, or cannot use the advisory form, you can also reach the
maintainer directly at **sildo466@outlook.com** — please use a clear subject
such as "[FSAR Security]" so it is not mistaken for spam.

Use either channel for any finding that could let an LLM, a tool, an MCP server,
a skill, or a remote peer bypass the guards below, read data outside the active
workspace, exfiltrate secrets, or execute destructive commands.

### What to include

A good report lets us reproduce and triage quickly. Please provide:

- **Summary** — one or two sentences on the vulnerability.
- **Affected version** — git commit hash or release tag (and how you installed).
- **Vulnerability type** — e.g. sandbox escape, path traversal, hardline-guard
  bypass, secret exfiltration, auth bypass, SSRF, command injection.
- **Steps to reproduce** — the exact prompt / tool call / input sequence, the
  character/user card state if relevant, and the platform (Windows / macOS /
  Linux) and shell (PowerShell / cmd / bash).
- **Observed vs. expected behaviour** — what the guard did vs. what it should
  have done (deny / confirm / proceed).
- **Impact** — what an attacker or a hallucinating model could achieve, and any
  preconditions (e.g. "requires a malicious MCP server to be installed").
- **Proof of concept** — a minimal script, transcript, or the offending command
  string. Attach files to the advisory rather than pasting secrets publicly.
- **Suggested fix** *(optional)* — if you have one.
- **Public disclosure plans** — whether you intend to publish, and any embargo
  date / CVE you have in mind.

Please redact any real API keys or credentials from your proof of concept.

### What happens next

1. We acknowledge receipt, usually within **72 hours**.
2. We triage and confirm the finding, keeping you in the loop.
3. We develop a fix, release it, and credit you in the advisory (or
   anonymise / omit credit if you prefer).
4. If warranted we request a CVE. We prefer coordinated disclosure and will
   agree on a timeline with you before anything goes public.

### Scope

In scope: anything in this repository — the Python backend (`src/`), the
frontend (`frontend/`), shipped presets/config, and the built-in tools, MCP
integration, skill runtime, and social adapters. Out of scope: attacks that
require the user to have already granted the OS-level Computer Use
(Accessibility) permission and then confirmed every prompt, social engineering
of the user, and vulnerabilities in upstream dependencies (report those to the
upstream project, and let us know if they affect FSAR).

## The FSAR security model (defense in depth)

Every tool invocation passes through these layers **before** it executes. They
are ordered from the unconditional floor upward; a deny at any layer stops the
action. The design principle throughout is **fail closed**: on error or timeout
the action is denied, never allowed.

### 1. Hardline guard — the unconditional floor
`src/sandbox/hardline.py`

A hardcoded, regex-based blocklist that runs before any other check and cannot
be relaxed by the model or by session trust. It covers nine command classes:

| Class | What it blocks |
|---|---|
| A | Disk destruction (`rm -rf /`, `mkfs`, `format c:`, `diskpart clean`, shadow-copy deletion) |
| B | System lifecycle (`shutdown`, `reboot`, `Stop-Computer`, `systemctl poweroff`) |
| C | Persistence / autostart (`reg add …\Run`, `schtasks`, `crontab -e`, `bcdedit`) |
| D | Privilege escalation (`net user … /add`, `usermod -aG sudo`, `New-LocalUser`) |
| E | Resource exhaustion (fork bombs, `while true; do`) |
| F | Service / daemon control (`Stop-Service`, `systemctl stop`, killing `lsass`/`init`) |
| G | Network security config (`netsh advfirewall … off`, `iptables -F`, `ufw disable`) |
| H | Fetch-and-execute (`curl … | sh`, `iwr … | iex`, `msiexec /i https://`) |
| I | Filesystem integrity (`takeown /r` on Windows dirs, `chmod -R 777 /`, `icacls … Everyone:F`) |

To defeat obfuscation, the command is **NFKC-normalised** and stripped of
zero-width characters before matching, and rules are shell-aware (they only fire
for the shells where the syntax is valid: `powershell`, `cmd`, `bash`).

### 2. Risk engine — per-call verdict
`src/security/risk.py`, `src/security/permissions.py`

`RiskEngine.evaluate(tool, args)` returns a verdict — `proceed`, `confirm`, or
`deny` — before `Tool.execute()` runs. Decision order (first match wins):

1. Session or permanent deny → **deny**
2. `blocked_patterns` hit in any string argument → **deny**
3. `path_rules` match → **deny**
4. Effective risk `SAFE` → **proceed**
5. yaml / session / server trust mode → **proceed** (unless session mode is `strict`)
6. yaml mode `ask` → **confirm** (unless session mode is `trust`)
7. Tool absent from yaml → threshold check of its declared risk against the
   session mode (`strict` asks at LOW+, `normal` at HIGH+, `trust` at CRITICAL)

Risk is ranked `SAFE < LOW < MEDIUM < HIGH < CRITICAL`. Dynamically registered
MCP tools fall back to their declared `risk_level`, never a silent default.

### 3. Workspace gate — filesystem confinement
`src/sandbox/workspace_gate.py`

File operations are confined to the active workspace root. The gate:

- resolves and contains paths to the workspace (`is_inside`), with an
  always-allow list for explicitly permitted external paths;
- enforces a per-workspace `allowed_paths` allowlist and `blocked_patterns`;
- flags **sensitive paths** (see layer 4) and anything outside the workspace as
  a `confirm_escape` — the user must explicitly approve leaving the sandbox,
  with a session-scoped allow cache so approvals do not silently persist forever;
- **blocks writing executable files** (`.exe`, `.dll`, `.com`, `.scr`, `.msi`);
- extracts path tokens out of shell commands (`extract_path_tokens`) and runs
  each through the same gate, so a command cannot smuggle a path past the check;
- runs the hardline guard (layer 1) over every command first.

### 4. Sensitive-path protection
`src/sandbox/sensitive.py`

Independent of the workspace, certain locations always require confirmation, in
four classes:

- **A — Cryptographic identity:** `.ssh`, `.gnupg`, `id_rsa`, `id_ed25519`, `*.ppk`
- **B — Cloud credentials:** `.aws`, `.azure`, `gcloud`, `.kube`, `.netrc`, Docker / `gh` config
- **C — Application secrets:** `.env*`, `*.pem`, `*.key`, `*.p12/pfx`, `*.kdbx`, `wallet.dat`, browser Login Data
- **D — System integrity anchors:** `hosts`, `.bashrc`, `.zshrc`, `.profile`, PowerShell profiles

A separate **read blacklist** (`~/.ssh/*`, `~/.aws/credentials`, `~/.gnupg/*`,
`*.key`, `*.pem`, `id_rsa`) blocks these from being read at all — including via
`cat`/`type`/`Get-Content` embedded in a shell command.

### 5. Subprocess environment scrubber
`src/skills/runtime.py`

When FSAR runs a skill as a subprocess, it builds the child environment from an
allowlist (`PATH`, `HOME`, `LANG`, `TMPDIR`, `SYSTEMROOT`, `USERPROFILE`) and
**strips any variable ending in `_API_KEY` or containing `API_KEY`, `TOKEN`,
`SECRET`, or `AUTH`**, so provider credentials never leak into skill code.

### 6. Confirmation — fail-closed UX
`src/security/confirmation.py`

When a verdict is `confirm`, the user is prompted (`approve once / deny / trust
this tool for this session / trust MCP server / permanently deny`). The prompt
is **default-deny**: plain Enter, an unknown answer, or a 120 s timeout all deny.

### 7. WebSocket authentication
`src/security/ws_auth.py`

The local server is protected by a bearer token (`secrets.token_urlsafe(48)`,
compared with `hmac.compare_digest`, stored mode `0600`), an Origin / Host
allowlist (`127.0.0.1:8765`, `localhost:8765`), `Sec-Fetch-Site` / `Referer`
checks, and per-client rate limiting (3 failures / 60 s).

### 8. Audit log
`src/security/audit.py`

Every tool decision is appended as one JSON line to `~/.fsar/data/logs/audit.log`
— tool, args, risk, verdict, user response, outcome, duration. The audit writer
never raises, so an audit failure cannot disrupt (or be used to disrupt) the
guarded path.

## Guidance for contributors working on security code

Security layers must stay **fail-closed** and must never be relaxed to make a
feature work. When changing anything under `src/sandbox/` or `src/security/`:

- **Add regression tests** under `tests/sandbox/` or `tests/security/` covering
  both the allow path and the block path. A guard change without a test will not
  be merged.
- **Do not weaken the hardline guard.** New destructive syntax should be added
  as a new pattern/class, never by removing or broadening existing ones.
- Preserve NFKC normalisation and zero-width stripping in any new command
  matching — obfuscation resistance is mandatory.
- Keep the deny → blocked_patterns → path_rules → risk ordering intact; do not
  introduce a path that can skip an earlier layer.
- New tools must declare an honest `risk_level`; when in doubt, ask for `confirm`.

### Testing and debugging security changes

```bash
# The offline security / sandbox unit gate (also what CI runs)
pytest tests/sandbox tests/security tests/skills tests/utils tests/server -q

# A single area while iterating
pytest tests/sandbox/test_hardline.py -q
pytest tests/security/test_ws_auth.py -q
```

To exercise a specific rule directly:

```python
from src.sandbox import hardline, sensitive
from pathlib import Path

hardline.check("rm -rf /", shell="bash")            # -> (True, "class A - ...")
sensitive.match(Path.home() / ".ssh" / "id_rsa")    # -> (True, "class A - ...")
```

Debugging tips:

- Trace a decision end-to-end via the audit log:
  `tail -f ~/.fsar/data/logs/audit.log` shows the tool, args, risk, verdict, and
  user response for every call.
- To reproduce a model-driven bug without a live LLM, call the tool registry /
  `RiskEngine` directly with the offending args, as the tests do.
- Reset all state with `rm -rf ~/.fsar/` (deletes config, memory, caches, logs).
