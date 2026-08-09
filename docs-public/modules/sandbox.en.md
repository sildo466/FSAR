# sandbox — workspace sandbox policy

> Language: [中文](sandbox.md) | English · Back to [module index](README.en.md)

Each conversation is bound to a workspace directory; this package decides whether paths/commands stay inside it.

| File | Description |
|---|---|
| `workspace_gate.py` | `WorkspaceGate.validate_path()` / `command_verdicts()` → `PathVerdict` (proceed/deny/confirm_escape); `SessionAllowCache` remembers session-scoped escape grants; `extract_path_tokens()` pulls paths out of commands. |
| `hardline.py` | The unconditional command safety floor (never overridable by user permission). |
| `paths.py` | Path normalization and workspace-containment checks. |
| `sensitive.py` | Locations that always require confirmation + the file-read blacklist. |
| `tool_guard.py` | Shared in-tool sandbox guard (a second line behind the engine-level checks). |
