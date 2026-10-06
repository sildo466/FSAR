# `data/` and `config/`

> Language: [中文](layout.md) | English · Back to [module index](README.en.md)

**`config/`** (shipped configuration):
- `fsar.yaml.template` — the bootstrap template (see the [configuration guide](../configuration.en.md)).
- `permissions.yaml` — parsed by `security/permissions.py` into `PermissionState`.

**`data/`** (shipped content + runtime databases):
- `presets/` — `llm-providers.json` / `asr-providers.json` / `tts-providers.json` (the options offered by the onboarding wizard).
- `cards/` — character cards `FSAR-en/zh`, `coding-coach-en/zh`, `research-analyst-en/zh`, `default-user.json`, `_meta.json`.
- `emotion_default.json` — default emotion schema and formulas.
- `skins/` — shipped skin presets (`warm`, `night`, `minimal`), each a hand-written `skin.json`.
- `migrations/` — dated Python migrations.
- Runtime artifacts: `memory.db`, `scheduler.db`, `llm_cache.db`, `tts_cache.db`, `chroma/`, `avatars/`, `logs/`, etc. `memory.db` runs in WAL mode, so you will also see `memory.db-wal` and `memory.db-shm` beside it — they are part of the database; leave them alone while FSAR is running.
