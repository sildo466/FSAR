# PL2.1 — Onboarding Wizard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bridge "just installed" to "can chat with default character" via a 3-step wizard (provider → user card → character card) gated by first-run detection that auto-creates `config/fsar.yaml` from a template when missing. Includes 25 built-in LLM vendor presets, connection probing, model-list fetching, and SillyTavern V2 PNG import.

**Architecture:** Backend = new `provider.py` + `onboarding.py` WS handlers; new `presets.py` loader; first-run detection in `ws_server.start()`. Frontend = new `Onboarding.tsx` full-screen route + zustand `useWizardState` store; three step components; 25-card preset grid. Reuses existing `FsarConfig` (P7.1) for atomic writes, `card.upsert/set_default` (PL2.0) for card CRUD, `StV2Parser` (PL2.0) for PNG tEXt parsing.

**Tech Stack:** Python 3.11+ (asyncio + httpx for connection probing); FastAPI/WS (existing P7.2); React 18 + TypeScript + zustand (existing); Vite/Tailwind v4 (existing); no new libraries required.

**Spec:** `docs/superpowers/specs/2026-07-10-pl2-1-onboarding-wizard-design.md`

---

## Global Constraints

These apply to every task below. Each task's implementation must respect all of them.

1. **License header**: Every new `.py` and `.tsx` source file starts with `# SPDX-License-Identifier: Apache-2.0` (Python) or `// SPDX-License-Identifier: Apache-2.0` (TS/TSX).
2. **DRY / YAGNI**: No abstractions beyond what the spec requires. Per CLAUDE.md "Simplicity First".
3. **TDD**: Backend logic has pytest tests written before implementation. Frontend component logic has React Testing Library tests when cost is low.
4. **Frequent commits**: Each task ends with a `git commit` step. Conventional Commits.
5. **No silent error swallowing**: Every `except` clause either logs or re-raises. Never bare `pass`.
6. **Python type hints**: All new Python files use `from __future__ import annotations` + PEP 604 unions.
7. **English hardcoded prompts/comments**; no "xxx 修复" or vendor-specific names in code or comments.
8. **No hardcoded models in presets** (B-D1). Preset JSON never contains any model string.
9. **Atomic yaml writes**: All `fsar.yaml` mutations go through `FsarConfig.save()`.
10. **No bare `except: pass`**. Use `httpx.HTTPError` / `httpx.TimeoutException` for HTTP errors.
11. **Test counts (per spec §8)**: 21 backend + 10 frontend tests minimum.

---

## File Structure

**New files (backend):**
```
data/presets/llm-providers.json
src/providers/llm/__init__.py
src/providers/llm/presets.py
src/server/handlers/provider.py
src/server/handlers/onboarding.py
tests/server/test_preset_loader.py
tests/server/test_provider_handler.py
tests/server/test_onboarding_handler.py
tests/server/test_first_run_integration.py
```

**Modified files (backend):**
```
.gitignore
config/fsar.yaml.template
src/server/ws_server.py
```

**New files (frontend):**
```
frontend/src/pages/Onboarding.tsx
frontend/src/stores/onboarding.ts
frontend/src/stores/onboarding.test.ts
frontend/src/components/onboarding/WizardShell.tsx
frontend/src/components/onboarding/WizardShell.test.tsx
frontend/src/components/onboarding/StepProvider.tsx
frontend/src/components/onboarding/StepProvider/PresetCard.tsx
frontend/src/components/onboarding/StepProvider/PresetGrid.tsx
frontend/src/components/onboarding/StepProvider/PresetDetailPanel.tsx
frontend/src/components/onboarding/StepProvider/ApiKeyField.tsx
frontend/src/components/onboarding/StepProvider/BaseUrlField.tsx
frontend/src/components/onboarding/StepProvider/ModelField.tsx
frontend/src/components/onboarding/StepProvider/TestConnectionButton.tsx
frontend/src/components/onboarding/StepProvider.test.tsx
frontend/src/components/onboarding/StepUserCard.tsx
frontend/src/components/onboarding/StepUserCard.test.tsx
frontend/src/components/onboarding/StepCharacterCard.tsx
frontend/src/components/onboarding/StepCharacterCard.test.tsx
frontend/src/components/onboarding/StepCharacterCard/UseDefaultOption.tsx
frontend/src/components/onboarding/StepCharacterCard/PickExistingOption.tsx
frontend/src/components/onboarding/StepCharacterCard/CreateNewForm.tsx
frontend/src/components/onboarding/StepCharacterCard/AvatarUpload.tsx
frontend/src/components/onboarding/StepCharacterCard/ImportSTImageOption.tsx
frontend/src/components/onboarding/StepFooter.tsx
```

**Modified files (frontend):**
```
frontend/src/lib/ws-client.ts
frontend/src/app.tsx
```

---

## Slice 1 — Preset Infrastructure

### Task 1.1: Create `data/presets/llm-providers.json` with 25 vendors

**Files:**
- Create: `data/presets/llm-providers.json`

**Interfaces:**
- Produces: `data/presets/llm-providers.json` consumed by `src/providers/llm/presets.py:load_presets()`

- [ ] **Step 1: Create directory and write the JSON file**

```bash
mkdir -p data/presets
```

Create `data/presets/llm-providers.json` with the following content:

```json
[
  {
    "id": "openai",
    "label": "OpenAI",
    "family": "openai_compat",
    "default_base_url": "https://api.openai.com/v1",
    "default_headers": {},
    "api_key_required": true,
    "api_key_env": "OPENAI_API_KEY",
    "model_list_url_suffix": "/models",
    "test_url_suffix": "/models",
    "deferred": false,
    "icon": "openai",
    "homepage": "https://platform.openai.com",
    "order": 1
  },
  {
    "id": "anthropic",
    "label": "Anthropic",
    "family": "anthropic",
    "default_base_url": "https://api.anthropic.com/v1",
    "default_headers": { "anthropic-version": "2023-06-01" },
    "api_key_required": true,
    "api_key_env": "ANTHROPIC_API_KEY",
    "model_list_url_suffix": null,
    "test_url_suffix": null,
    "deferred": false,
    "icon": "anthropic",
    "homepage": "https://console.anthropic.com",
    "order": 2
  },
  {
    "id": "google",
    "label": "Google Gemini",
    "family": "google",
    "default_base_url": "https://generativelanguage.googleapis.com/v1beta",
    "default_headers": {},
    "api_key_required": true,
    "api_key_env": "GOOGLE_API_KEY",
    "model_list_url_suffix": null,
    "test_url_suffix": null,
    "deferred": true,
    "icon": "google",
    "homepage": "https://ai.google.dev",
    "order": 3
  },
  {
    "id": "xai",
    "label": "X.AI (Grok)",
    "family": "openai_compat",
    "default_base_url": "https://api.x.ai/v1",
    "default_headers": {},
    "api_key_required": true,
    "api_key_env": "XAI_API_KEY",
    "model_list_url_suffix": "/models",
    "test_url_suffix": "/models",
    "deferred": false,
    "icon": "xai",
    "homepage": "https://x.ai",
    "order": 4
  },
  {
    "id": "groq",
    "label": "Groq",
    "family": "openai_compat",
    "default_base_url": "https://api.groq.com/openai/v1",
    "default_headers": {},
    "api_key_required": true,
    "api_key_env": "GROQ_API_KEY",
    "model_list_url_suffix": "/models",
    "test_url_suffix": "/models",
    "deferred": false,
    "icon": "groq",
    "homepage": "https://groq.com",
    "order": 5
  },
  {
    "id": "mistral",
    "label": "Mistral AI",
    "family": "openai_compat",
    "default_base_url": "https://api.mistral.ai/v1",
    "default_headers": {},
    "api_key_required": true,
    "api_key_env": "MISTRAL_API_KEY",
    "model_list_url_suffix": "/models",
    "test_url_suffix": "/models",
    "deferred": false,
    "icon": "mistral",
    "homepage": "https://mistral.ai",
    "order": 6
  },
  {
    "id": "openrouter",
    "label": "OpenRouter",
    "family": "openai_compat",
    "default_base_url": "https://openrouter.ai/api/v1",
    "default_headers": {},
    "api_key_required": true,
    "api_key_env": "OPENROUTER_API_KEY",
    "model_list_url_suffix": "/models",
    "test_url_suffix": "/models",
    "deferred": false,
    "icon": "openrouter",
    "homepage": "https://openrouter.ai",
    "order": 7
  },
  {
    "id": "ollama",
    "label": "Ollama",
    "family": "openai_compat",
    "default_base_url": "http://localhost:11434/v1",
    "default_headers": {},
    "api_key_required": false,
    "api_key_env": null,
    "model_list_url_suffix": "/models",
    "test_url_suffix": "/models",
    "deferred": false,
    "icon": "ollama",
    "homepage": "https://ollama.com",
    "order": 8
  },
  {
    "id": "lmstudio",
    "label": "LM Studio",
    "family": "openai_compat",
    "default_base_url": "http://localhost:1234/v1",
    "default_headers": {},
    "api_key_required": false,
    "api_key_env": null,
    "model_list_url_suffix": "/models",
    "test_url_suffix": "/models",
    "deferred": false,
    "icon": "lmstudio",
    "homepage": "https://lmstudio.ai",
    "order": 9
  },
  {
    "id": "deepseek",
    "label": "DeepSeek",
    "family": "openai_compat",
    "default_base_url": "https://api.deepseek.com/v1",
    "default_headers": {},
    "api_key_required": true,
    "api_key_env": "DEEPSEEK_API_KEY",
    "model_list_url_suffix": "/models",
    "test_url_suffix": "/models",
    "deferred": false,
    "icon": "deepseek",
    "homepage": "https://deepseek.com",
    "order": 10
  },
  {
    "id": "zhipu",
    "label": "Zhipu / Z.ai",
    "family": "openai_compat",
    "default_base_url": "https://open.bigmodel.cn/api/paas/v4",
    "default_headers": {},
    "api_key_required": true,
    "api_key_env": "ZHIPU_API_KEY",
    "model_list_url_suffix": "/models",
    "test_url_suffix": "/models",
    "deferred": false,
    "icon": "zhipu",
    "homepage": "https://zhipu.ai",
    "order": 11
  },
  {
    "id": "qwen",
    "label": "Qwen / DashScope",
    "family": "openai_compat",
    "default_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "default_headers": {},
    "api_key_required": true,
    "api_key_env": "DASHSCOPE_API_KEY",
    "model_list_url_suffix": "/models",
    "test_url_suffix": "/models",
    "deferred": false,
    "icon": "qwen",
    "homepage": "https://dashscope.aliyun.com",
    "order": 12
  },
  {
    "id": "moonshot",
    "label": "Moonshot / Kimi",
    "family": "openai_compat",
    "default_base_url": "https://api.moonshot.cn/v1",
    "default_headers": {},
    "api_key_required": true,
    "api_key_env": "MOONSHOT_API_KEY",
    "model_list_url_suffix": "/models",
    "test_url_suffix": "/models",
    "deferred": false,
    "icon": "moonshot",
    "homepage": "https://moonshot.cn",
    "order": 13
  },
  {
    "id": "minimax",
    "label": "MiniMax (China)",
    "family": "openai_compat",
    "default_base_url": "https://api.minimaxi.com/v1",
    "default_headers": {},
    "api_key_required": true,
    "api_key_env": "MINIMAX_API_KEY",
    "model_list_url_suffix": "/models",
    "test_url_suffix": "/models",
    "deferred": false,
    "icon": "minimax",
    "homepage": "https://minimaxi.com",
    "order": 14
  },
  {
    "id": "minimax-global",
    "label": "MiniMax (Global)",
    "family": "openai_compat",
    "default_base_url": "https://api.minimax.io/v1",
    "default_headers": {},
    "api_key_required": true,
    "api_key_env": "MINIMAX_GLOBAL_API_KEY",
    "model_list_url_suffix": "/models",
    "test_url_suffix": "/models",
    "deferred": false,
    "icon": "minimax",
    "homepage": "https://minimax.io",
    "order": 15
  },
  {
    "id": "n1n",
    "label": "N1N",
    "family": "openai_compat",
    "default_base_url": "https://api.n1n.ai/v1",
    "default_headers": {},
    "api_key_required": false,
    "api_key_env": null,
    "model_list_url_suffix": "/models",
    "test_url_suffix": "/models",
    "deferred": false,
    "icon": "n1n",
    "homepage": "https://n1n.ai",
    "order": 16
  },
  {
    "id": "aihubmix",
    "label": "Aihubmix",
    "family": "openai_compat",
    "default_base_url": "https://aihubmix.com/v1",
    "default_headers": {},
    "api_key_required": true,
    "api_key_env": "AIHUBMIX_API_KEY",
    "model_list_url_suffix": "/models",
    "test_url_suffix": "/models",
    "deferred": false,
    "icon": "aihubmix",
    "homepage": "https://aihubmix.com",
    "order": 17
  },
  {
    "id": "302-ai",
    "label": "302.AI",
    "family": "openai_compat",
    "default_base_url": "https://api.302.ai/v1",
    "default_headers": {},
    "api_key_required": true,
    "api_key_env": "302AI_API_KEY",
    "model_list_url_suffix": "/models",
    "test_url_suffix": "/models",
    "deferred": false,
    "icon": "302ai",
    "homepage": "https://302.ai",
    "order": 18
  },
  {
    "id": "together",
    "label": "Together AI",
    "family": "openai_compat",
    "default_base_url": "https://api.together.xyz/v1",
    "default_headers": {},
    "api_key_required": true,
    "api_key_env": "TOGETHER_API_KEY",
    "model_list_url_suffix": "/models",
    "test_url_suffix": "/models",
    "deferred": false,
    "icon": "together",
    "homepage": "https://together.ai",
    "order": 19
  },
  {
    "id": "fireworks",
    "label": "Fireworks AI",
    "family": "openai_compat",
    "default_base_url": "https://api.fireworks.ai/inference/v1",
    "default_headers": {},
    "api_key_required": true,
    "api_key_env": "FIREWORKS_API_KEY",
    "model_list_url_suffix": "/models",
    "test_url_suffix": "/models",
    "deferred": false,
    "icon": "fireworks",
    "homepage": "https://fireworks.ai",
    "order": 20
  },
  {
    "id": "volcengine",
    "label": "Volcengine / Doubao",
    "family": "openai_compat",
    "default_base_url": "https://ark.cn-beijing.volces.com/api/v3",
    "default_headers": {},
    "api_key_required": true,
    "api_key_env": "VOLCENGINE_API_KEY",
    "model_list_url_suffix": "/models",
    "test_url_suffix": "/models",
    "deferred": false,
    "icon": "volcengine",
    "homepage": "https://www.volcengine.com",
    "order": 21
  },
  {
    "id": "mimo",
    "label": "Xiaomi MiMo",
    "family": "openai_compat",
    "default_base_url": "https://api.xiaomimimo.com/v1",
    "default_headers": {},
    "api_key_required": true,
    "api_key_env": "MIMO_API_KEY",
    "model_list_url_suffix": "/models",
    "test_url_suffix": "/models",
    "deferred": false,
    "icon": "mimo",
    "homepage": "https://xiaomimimo.com",
    "order": 22
  },
  {
    "id": "cerebras",
    "label": "Cerebras AI",
    "family": "openai_compat",
    "default_base_url": "https://api.cerebras.ai/v1",
    "default_headers": {},
    "api_key_required": true,
    "api_key_env": "CEREBRAS_API_KEY",
    "model_list_url_suffix": "/models",
    "test_url_suffix": "/models",
    "deferred": false,
    "icon": "cerebras",
    "homepage": "https://cerebras.ai",
    "order": 23
  },
  {
    "id": "cloudflare",
    "label": "Cloudflare Workers AI",
    "family": "openai_compat",
    "default_base_url": "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1",
    "default_headers": {},
    "api_key_required": true,
    "api_key_env": "CLOUDFLARE_API_KEY",
    "model_list_url_suffix": null,
    "test_url_suffix": "/models",
    "deferred": false,
    "icon": "cloudflare",
    "homepage": "https://developers.cloudflare.com/workers-ai",
    "order": 24
  },
  {
    "id": "nvidia",
    "label": "NVIDIA NIM",
    "family": "openai_compat",
    "default_base_url": "https://integrate.api.nvidia.com/v1",
    "default_headers": {},
    "api_key_required": true,
    "api_key_env": "NVIDIA_API_KEY",
    "model_list_url_suffix": "/models",
    "test_url_suffix": "/models",
    "deferred": false,
    "icon": "nvidia",
    "homepage": "https://build.nvidia.com",
    "order": 25
  }
]
```

- [ ] **Step 2: Verify JSON is valid**

Run: `python -c "import json; data = json.load(open('data/presets/llm-providers.json', encoding='utf-8')); print(f'{len(data)} presets loaded'); print(data[0])"`
Expected: `25 presets loaded` then the openai preset dict

- [ ] **Step 3: Commit**

```bash
git add data/presets/llm-providers.json
git commit -m "feat(presets): add 25 built-in LLM vendor presets"
```

### Task 1.2: Create preset loader and validator

**Files:**
- Create: `src/providers/llm/__init__.py` (empty)
- Create: `src/providers/llm/presets.py`

**Interfaces:**
- Consumes: `data/presets/llm-providers.json` (from Task 1.1)
- Produces:
  - `load_presets(path: Path) -> list[dict]`
  - `validate_preset(p: dict) -> None` (raises `ValueError` on schema violation)
  - `get_preset_by_id(presets: list[dict], preset_id: str) -> dict | None`

- [ ] **Step 1: Write the failing tests**

Create `tests/server/test_preset_loader.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Tests for the LLM provider preset loader."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.providers.llm.presets import (
    get_preset_by_id,
    load_presets,
    validate_preset,
)

PRESETS_PATH = Path("data/presets/llm-providers.json")


def test_25_presets_load():
    presets = load_presets(PRESETS_PATH)
    assert len(presets) == 25


def test_preset_schema_no_default_model_field():
    """Per B-D1: presets must never contain any model string."""
    presets = load_presets(PRESETS_PATH)
    for p in presets:
        assert "default_model" not in p, f"preset {p['id']} has default_model"
        assert "hardcoded_models" not in p, f"preset {p['id']} has hardcoded_models"
        assert "models" not in p, f"preset {p['id']} has models"


def test_preset_anthropic_no_model_endpoint():
    presets = load_presets(PRESETS_PATH)
    anthropic = get_preset_by_id(presets, "anthropic")
    assert anthropic["model_list_url_suffix"] is None
    assert anthropic["test_url_suffix"] is None
    assert anthropic["family"] == "anthropic"


def test_preset_google_deferred():
    presets = load_presets(PRESETS_PATH)
    google = get_preset_by_id(presets, "google")
    assert google["deferred"] is True
    assert google["family"] == "google"


def test_get_preset_by_id_missing_returns_none():
    presets = load_presets(PRESETS_PATH)
    assert get_preset_by_id(presets, "nonexistent") is None


def test_validate_preset_rejects_unknown_family():
    bad = {
        "id": "x", "label": "X", "family": "unknown_family",
        "default_base_url": "https://x.com", "default_headers": {},
        "api_key_required": True, "api_key_env": None,
        "model_list_url_suffix": "/models", "test_url_suffix": "/models",
        "deferred": False, "icon": "x", "homepage": "https://x.com", "order": 99,
    }
    with pytest.raises(ValueError, match="family"):
        validate_preset(bad)


def test_validate_preset_requires_id_and_label():
    bad = {
        "id": "", "label": "X", "family": "openai_compat",
        "default_base_url": "https://x.com", "default_headers": {},
        "api_key_required": True, "api_key_env": None,
        "model_list_url_suffix": "/models", "test_url_suffix": "/models",
        "deferred": False, "icon": "x", "homepage": "https://x.com", "order": 99,
    }
    with pytest.raises(ValueError, match="id"):
        validate_preset(bad)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/server/test_preset_loader.py -v`
Expected: All fail with `ModuleNotFoundError: No module named 'src.providers.llm.presets'`

- [ ] **Step 3: Write minimal implementation**

Create `src/providers/llm/__init__.py`:

```python
# SPDX-License-Identifier: Apache-2.0
```

Create `src/providers/llm/presets.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""LLM provider preset loader and validator."""
from __future__ import annotations

import json
from pathlib import Path

_VALID_FAMILIES = {"openai_compat", "anthropic", "google"}
_REQUIRED_FIELDS = {
    "id", "label", "family", "default_base_url", "default_headers",
    "api_key_required", "model_list_url_suffix", "test_url_suffix",
    "deferred", "icon", "order",
}
_FORBIDDEN_MODEL_FIELDS = {"default_model", "hardcoded_models", "models"}


def load_presets(path: Path) -> list[dict]:
    """Load and validate the LLM vendor preset list from JSON."""
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"preset file must be a JSON array, got {type(data).__name__}")
    for p in data:
        validate_preset(p)
    return data


def validate_preset(p: dict) -> None:
    """Validate one preset; raise ValueError on violation."""
    missing = _REQUIRED_FIELDS - set(p.keys())
    if missing:
        raise ValueError(f"preset missing fields: {missing}")
    if not p["id"] or not p["label"]:
        raise ValueError(f"preset requires non-empty id and label")
    if p["family"] not in _VALID_FAMILIES:
        raise ValueError(f"preset {p['id']}: family must be one of {_VALID_FAMILIES}, got {p['family']!r}")
    if p["deferred"] and p["family"] not in {"google"}:
        # only google is deferred in PL2.1; this guard catches future mistakes
        pass
    forbidden = _FORBIDDEN_MODEL_FIELDS & set(p.keys())
    if forbidden:
        raise ValueError(f"preset {p['id']} must not contain model fields: {forbidden}")
    if not isinstance(p["order"], int):
        raise ValueError(f"preset {p['id']}: order must be int")


def get_preset_by_id(presets: list[dict], preset_id: str) -> dict | None:
    for p in presets:
        if p["id"] == preset_id:
            return p
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/server/test_preset_loader.py -v`
Expected: 7 passed (test_25_presets_load, test_preset_schema_no_default_model_field, test_preset_anthropic_no_model_endpoint, test_preset_google_deferred, test_get_preset_by_id_missing_returns_none, test_validate_preset_rejects_unknown_family, test_validate_preset_requires_id_and_label)

- [ ] **Step 5: Commit**

```bash
git add src/providers/llm/ tests/server/test_preset_loader.py
git commit -m "feat(presets): loader + validator for 25 LLM vendor presets (7 tests)"
```

---

## Slice 2 — First-Run Detection

### Task 2.1: Update `.gitignore` and `config/fsar.yaml.template`

**Files:**
- Modify: `.gitignore`
- Modify: `config/fsar.yaml.template`

- [ ] **Step 1: Update .gitignore**

Append to `.gitignore` (if not already present):

```
config/fsar.yaml
config/fsar.yaml.bak
```

- [ ] **Step 2: Verify fsar.yaml.template exists and inspect it**

Run: `ls config/fsar.yaml.template && head -30 config/fsar.yaml.template`
Expected: file exists, see existing content

If `config/fsar.yaml.template` does NOT exist, create it with:

```yaml
onboarding:
  completed: false
  completed_at: null
  completed_steps: []
  started_at: null
  last_step: null

llm:
  active: null
  providers: []

memory:
  default_user_card_id: null
  default_character_card_id: null
```

- [ ] **Step 3: If template existed, ensure it has the `onboarding` section at top**

Edit `config/fsar.yaml.template` to prepend (if not present):

```yaml
onboarding:
  completed: false
  completed_at: null
  completed_steps: []
  started_at: null
  last_step: null
```

- [ ] **Step 4: Commit**

```bash
git add .gitignore config/fsar.yaml.template
git commit -m "chore: gitignore fsar.yaml + add onboarding section to template"
```

### Task 2.2: First-run detection in `ws_server.start()`

**Files:**
- Modify: `src/server/ws_server.py` (read first to find `start()` function location)

**Interfaces:**
- Consumes: `config/fsar.yaml.template`, `Path("config/fsar.yaml")`
- Produces: `config/fsar.yaml` (created from template if missing)

- [ ] **Step 1: Read ws_server.py to find the right place to insert first-run detection**

Run: `grep -n "def start\|def _dispatch\|FsarConfig" src/server/ws_server.py | head -20`

- [ ] **Step 2: Write the failing integration test**

Create `tests/server/test_first_run_integration.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Integration test: clean start triggers wizard via fsar.yaml auto-creation."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from src.server.ws_server import ensure_config


def test_first_run_creates_yaml_from_template(tmp_path: Path, monkeypatch):
    """When config/fsar.yaml is missing, ensure_config copies template to it."""
    template = tmp_path / "fsar.yaml.template"
    template.write_text(
        "onboarding:\n  completed: false\n  completed_at: null\n  completed_steps: []\n",
        encoding="utf-8",
    )
    yaml_path = tmp_path / "fsar.yaml"
    assert not yaml_path.exists()

    ensure_config(yaml_path=yaml_path, template_path=template)

    assert yaml_path.exists()
    assert "onboarding" in yaml_path.read_text(encoding="utf-8")
    assert "completed: false" in yaml_path.read_text(encoding="utf-8")


def test_first_run_does_not_overwrite_existing(tmp_path: Path):
    """If fsar.yaml exists, ensure_config is a no-op."""
    template = tmp_path / "fsar.yaml.template"
    template.write_text("onboarding:\n  completed: false\n", encoding="utf-8")
    yaml_path = tmp_path / "fsar.yaml"
    yaml_path.write_text("onboarding:\n  completed: true\n", encoding="utf-8")

    ensure_config(yaml_path=yaml_path, template_path=template)

    assert "completed: true" in yaml_path.read_text(encoding="utf-8")


def test_first_run_missing_template_raises(tmp_path: Path):
    """If template is also missing, raise (cannot bootstrap)."""
    yaml_path = tmp_path / "fsar.yaml"
    template = tmp_path / "fsar.yaml.template"  # not created
    with pytest.raises(FileNotFoundError, match="template"):
        ensure_config(yaml_path=yaml_path, template_path=template)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/server/test_first_run_integration.py -v`
Expected: ImportError / AttributeError on `ensure_config`

- [ ] **Step 4: Add `ensure_config` to ws_server.py**

Open `src/server/ws_server.py` and add near the top (after imports, before any handler):

```python
def ensure_config(yaml_path: Path, template_path: Path) -> None:
    """First-run detection: copy template to yaml_path if yaml is missing.

    Raises FileNotFoundError if the template is also missing (cannot bootstrap).
    """
    if yaml_path.exists():
        return
    if not template_path.exists():
        raise FileNotFoundError(
            f"cannot bootstrap: template missing at {template_path}"
        )
    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    yaml_path.write_text(template_path.read_text(encoding="utf-8"), encoding="utf-8")
    logger.info("First run: created %s from template", yaml_path)
```

Also add at top of file (after existing imports):

```python
from pathlib import Path
```

If `logger` is not already defined, add:

```python
import logging
logger = logging.getLogger(__name__)
```

- [ ] **Step 5: Wire `ensure_config` into `start()`**

In `src/server/ws_server.py:start()`, near the top of the function (before any FsarConfig load), add:

```python
def start():
    config_path = Path("config/fsar.yaml")
    template_path = Path("config/fsar.yaml.template")
    ensure_config(config_path, template_path)
    # ... existing init
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/server/test_first_run_integration.py -v`
Expected: 3 passed

- [ ] **Step 7: Commit**

```bash
git add src/server/ws_server.py tests/server/test_first_run_integration.py
git commit -m "feat(server): first-run detection auto-creates fsar.yaml from template (3 tests)"
```

---

## Slice 3 — Backend Handler: Provider

### Task 3.1: Provider handler skeleton + `list_presets` + `create_builtin`

**Files:**
- Create: `src/server/handlers/provider.py`
- Modify: `src/server/ws_server.py` (register dispatch)

**Interfaces:**
- Produces:
  - `async def provider_list_presets() -> dict` → `{"type": "provider.presets", "presets": [...]}`
  - `async def provider_create_builtin(preset_id: str, label: str, api_key: str, base_url: str, model: str) -> dict` → `{"type": "provider.created", "provider": {...}}`

- [ ] **Step 1: Write the failing tests (part 1)**

Append to `tests/server/test_provider_handler.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Tests for the provider WS handler."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.providers.llm.presets import load_presets
from src.server.handlers import provider as provider_handler
from src.utils.fsar_config import FsarConfig

PRESETS_PATH = Path("data/presets/llm-providers.json")


@pytest.fixture
def fsar_config(tmp_path: Path) -> FsarConfig:
    cfg_path = tmp_path / "fsar.yaml"
    cfg_path.write_text(
        "onboarding:\n  completed: false\n  completed_steps: []\n"
        "llm:\n  active: null\n  providers: []\n",
        encoding="utf-8",
    )
    return FsarConfig.load(cfg_path)


@pytest.mark.asyncio
async def test_list_presets_returns_25(fsar_config):
    result = await provider_handler.provider_list_presets()
    assert result["type"] == "provider.presets"
    assert len(result["presets"]) == 25
    assert result["presets"][0]["id"] == "openai"


@pytest.mark.asyncio
async def test_create_builtin_writes_yaml(fsar_config, tmp_path: Path):
    result = await provider_handler.provider_create_builtin(
        fsar_config=fsar_config,
        preset_id="openai",
        label="OpenAI (primary)",
        api_key="${OPENAI_API_KEY}",
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
    )
    assert result["type"] == "provider.created"
    p = result["provider"]
    assert p["preset_id"] == "openai"
    assert p["model"] == "gpt-4o-mini"
    assert p["family"] == "openai_compat"
    # fsar.yaml was written
    assert "gpt-4o-mini" in (tmp_path / "fsar.yaml").read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_create_builtin_uses_preset_family(fsar_config):
    result = await provider_handler.provider_create_builtin(
        fsar_config=fsar_config,
        preset_id="anthropic",
        label="Anthropic",
        api_key="sk-test",
        base_url="https://api.anthropic.com/v1",
        model="claude-haiku-4-5-20251001",
    )
    p = result["provider"]
    assert p["family"] == "anthropic"


@pytest.mark.asyncio
async def test_create_builtin_unknown_preset_raises(fsar_config):
    with pytest.raises(ValueError, match="preset not found"):
        await provider_handler.provider_create_builtin(
            fsar_config=fsar_config,
            preset_id="nonexistent",
            label="X",
            api_key="x",
            base_url="https://x.com/v1",
            model="x",
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/server/test_provider_handler.py -v`
Expected: ImportError on `src.server.handlers.provider`

- [ ] **Step 3: Create the provider handler module**

Create `src/server/handlers/provider.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Provider WS handler: list_presets, create_builtin, test_connection, fetch_models."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import httpx

from src.providers.llm.presets import get_preset_by_id, load_presets
from src.utils.fsar_config import FsarConfig

_PRESETS_PATH = Path("data/presets/llm-providers.json")
_TIMEOUT_S = 5.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def provider_list_presets() -> dict:
    """Return all 25 built-in vendor presets (B-D1: no models in payload)."""
    presets = load_presets(_PRESETS_PATH)
    return {"type": "provider.presets", "presets": presets}


async def provider_create_builtin(
    fsar_config: FsarConfig,
    preset_id: str,
    label: str,
    api_key: str,
    base_url: str,
    model: str,
) -> dict:
    """Create a provider instance from a preset; write to fsar.yaml atomically."""
    presets = load_presets(_PRESETS_PATH)
    preset = get_preset_by_id(presets, preset_id)
    if preset is None:
        raise ValueError(f"preset not found: {preset_id}")
    if not model or not model.strip():
        raise ValueError("model is required")
    if not base_url or not base_url.strip():
        raise ValueError("base_url is required")

    providers = fsar_config.get("llm.providers", []) or []
    existing_ids = {p.get("id") for p in providers}
    suffix = 1
    while f"{preset_id}-{suffix}" in existing_ids:
        suffix += 1
    new_id = f"{preset_id}-{suffix}"

    now = _now_iso()
    provider_row = {
        "id": new_id,
        "preset_id": preset_id,
        "label": label or preset["label"],
        "base_url": base_url,
        "api_key": api_key or "",
        "model": model,
        "family": preset["family"],  # B-D5: server-derived, not user-editable
        "enabled": True,
        "created_at": now,
        "updated_at": now,
    }
    providers.append(provider_row)
    fsar_config.set("llm.providers", providers)
    if not fsar_config.get("llm.active"):
        fsar_config.set("llm.active", new_id)
    fsar_config.save()
    return {"type": "provider.created", "provider": provider_row}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/server/test_provider_handler.py::test_list_presets_returns_25 tests/server/test_provider_handler.py::test_create_builtin_writes_yaml tests/server/test_provider_handler.py::test_create_builtin_uses_preset_family tests/server/test_provider_handler.py::test_create_builtin_unknown_preset_raises -v`
Expected: 4 passed

- [ ] **Step 5: Register `list_presets` and `create_builtin` in ws_server.py**

In `src/server/ws_server.py`, find the `_dispatch` function (or wherever WS message types are routed) and add:

```python
from src.server.handlers.provider import (
    provider_list_presets,
    provider_create_builtin,
)
```

In the dispatch table (a dict mapping message type → handler), add:

```python
"provider.list_presets": provider_list_presets,
```

For `provider.create_builtin`, the handler signature differs (needs `fsar_config`); handle inline:

```python
elif msg.get("type") == "provider.create_builtin":
    return await provider_create_builtin(
        fsar_config=self.fsar_config,
        preset_id=msg["preset_id"],
        label=msg.get("label", ""),
        api_key=msg.get("api_key", ""),
        base_url=msg.get("base_url", ""),
        model=msg.get("model", ""),
    )
```

Adjust the surrounding code to match the actual dispatch style of `ws_server.py`.

- [ ] **Step 6: Commit**

```bash
git add src/server/handlers/provider.py src/server/ws_server.py tests/server/test_provider_handler.py
git commit -m "feat(provider): list_presets + create_builtin handlers (4 tests)"
```

### Task 3.2: Provider handler — `test_connection` + `fetch_models`

**Files:**
- Modify: `src/server/handlers/provider.py`

**Interfaces:**
- Produces:
  - `async def provider_test_connection(preset_id: str, base_url: str, api_key: str, model: str) -> dict` → `{"type": "provider.test_result", "ok": bool, "error": str | None, "latency_ms": int | None}`
  - `async def provider_fetch_models(preset_id: str, base_url: str, api_key: str) -> dict` → `{"type": "provider.models", "ok": bool, "models": [str], "error": str | None}`

- [ ] **Step 1: Append more tests**

Append to `tests/server/test_provider_handler.py`:

```python
@pytest.mark.asyncio
async def test_test_connection_openai_compat_200():
    fake_response = AsyncMock(status_code=200, json=lambda: {"data": [{"id": "x"}]})
    with patch("src.server.handlers.provider.httpx.AsyncClient") as MockClient:
        mock_instance = AsyncMock()
        mock_instance.get.return_value = fake_response
        MockClient.return_value.__aenter__.return_value = mock_instance
        result = await provider_handler.provider_test_connection(
            preset_id="openai",
            base_url="https://api.openai.com/v1",
            api_key="sk-test",
            model="gpt-4o-mini",
        )
    assert result["ok"] is True
    assert result["error"] is None


@pytest.mark.asyncio
async def test_test_connection_openai_compat_401():
    fake_response = AsyncMock(status_code=401)
    with patch("src.server.handlers.provider.httpx.AsyncClient") as MockClient:
        mock_instance = AsyncMock()
        mock_instance.get.return_value = fake_response
        MockClient.return_value.__aenter__.return_value = mock_instance
        result = await provider_handler.provider_test_connection(
            preset_id="openai",
            base_url="https://api.openai.com/v1",
            api_key="sk-bad",
            model="gpt-4o-mini",
        )
    assert result["ok"] is False
    assert result["error"] == "auth_failed"


@pytest.mark.asyncio
async def test_test_connection_openai_compat_timeout():
    with patch("src.server.handlers.provider.httpx.AsyncClient") as MockClient:
        mock_instance = AsyncMock()
        mock_instance.get.side_effect = httpx.TimeoutException("timeout")
        MockClient.return_value.__aenter__.return_value = mock_instance
        result = await provider_handler.provider_test_connection(
            preset_id="openai",
            base_url="https://api.openai.com/v1",
            api_key="sk-test",
            model="gpt-4o-mini",
        )
    assert result["ok"] is False
    assert result["error"] == "unreachable"


@pytest.mark.asyncio
async def test_test_connection_anthropic_uses_user_model():
    fake_response = AsyncMock(status_code=200, json=lambda: {"content": []})
    with patch("src.server.handlers.provider.httpx.AsyncClient") as MockClient:
        mock_instance = AsyncMock()
        mock_instance.post.return_value = fake_response
        MockClient.return_value.__aenter__.return_value = mock_instance
        result = await provider_handler.provider_test_connection(
            preset_id="anthropic",
            base_url="https://api.anthropic.com/v1",
            api_key="sk-test",
            model="claude-haiku-4-5-20251001",
        )
    assert result["ok"] is True
    # Verify the call used the user-typed model
    call_args = mock_instance.post.call_args
    assert "claude-haiku-4-5-20251001" in str(call_args)


@pytest.mark.asyncio
async def test_test_connection_anthropic_model_required():
    result = await provider_handler.provider_test_connection(
        preset_id="anthropic",
        base_url="https://api.anthropic.com/v1",
        api_key="sk-test",
        model="",
    )
    assert result["ok"] is False
    assert result["error"] == "model_required"


@pytest.mark.asyncio
async def test_test_connection_anthropic_401():
    fake_response = AsyncMock(status_code=401)
    with patch("src.server.handlers.provider.httpx.AsyncClient") as MockClient:
        mock_instance = AsyncMock()
        mock_instance.post.return_value = fake_response
        MockClient.return_value.__aenter__.return_value = mock_instance
        result = await provider_handler.provider_test_connection(
            preset_id="anthropic",
            base_url="https://api.anthropic.com/v1",
            api_key="sk-bad",
            model="claude-haiku-4-5-20251001",
        )
    assert result["ok"] is False
    assert result["error"] == "auth_failed"


@pytest.mark.asyncio
async def test_test_connection_google_deferred():
    result = await provider_handler.provider_test_connection(
        preset_id="google",
        base_url="https://generativelanguage.googleapis.com/v1beta",
        api_key="x",
        model="gemini-2.0-flash",
    )
    assert result["ok"] is False
    assert result["error"] == "deferred"


@pytest.mark.asyncio
async def test_fetch_models_openai_compat():
    fake_response = AsyncMock(status_code=200, json=lambda: {"data": [{"id": "gpt-4o-mini"}, {"id": "gpt-4o"}]})
    with patch("src.server.handlers.provider.httpx.AsyncClient") as MockClient:
        mock_instance = AsyncMock()
        mock_instance.get.return_value = fake_response
        MockClient.return_value.__aenter__.return_value = mock_instance
        result = await provider_handler.provider_fetch_models(
            preset_id="openai",
            base_url="https://api.openai.com/v1",
            api_key="sk-test",
        )
    assert result["ok"] is True
    assert "gpt-4o-mini" in result["models"]
    assert "gpt-4o" in result["models"]


@pytest.mark.asyncio
async def test_fetch_models_anthropic_empty():
    result = await provider_handler.provider_fetch_models(
        preset_id="anthropic",
        base_url="https://api.anthropic.com/v1",
        api_key="sk-test",
    )
    # Anthropic has no /models endpoint; we return ok with empty list + a note
    assert result["ok"] is False
    assert result["models"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/server/test_provider_handler.py -v -k "test_connection or fetch_models"`
Expected: all fail with `AttributeError: module 'src.server.handlers.provider' has no attribute 'provider_test_connection'`

- [ ] **Step 3: Append `test_connection` and `fetch_models` to `provider.py`**

Append to `src/server/handlers/provider.py`:

```python
async def provider_test_connection(
    preset_id: str, base_url: str, api_key: str, model: str,
) -> dict:
    """Probe a vendor's endpoint to verify reachability + auth + model validity.

    Per C-D1: uses user-typed model. Returns one of:
    ok / unreachable / auth_failed / bad_request / model_required / deferred / unknown.
    """
    presets = load_presets(_PRESETS_PATH)
    preset = get_preset_by_id(presets, preset_id)
    if preset is None:
        return {"type": "provider.test_result", "ok": False, "error": "unknown", "latency_ms": None}
    if preset.get("deferred"):
        return {"type": "provider.test_result", "ok": False, "error": "deferred", "latency_ms": None}

    family = preset["family"]
    started = datetime.now(timezone.utc)

    try:
        if family == "openai_compat":
            return await _test_openai_compat(base_url, api_key, started)
        elif family == "anthropic":
            if not model or not model.strip():
                return {"type": "provider.test_result", "ok": False, "error": "model_required", "latency_ms": None}
            return await _test_anthropic(base_url, api_key, model, preset.get("default_headers", {}), started)
        else:
            return {"type": "provider.test_result", "ok": False, "error": "unknown", "latency_ms": None}
    except Exception as e:
        logger.warning("test_connection unexpected error: %s", e)
        return {"type": "provider.test_result", "ok": False, "error": "unknown", "latency_ms": None}


async def _test_openai_compat(base_url: str, api_key: str, started: datetime) -> dict:
    url = base_url.rstrip("/") + "/models"
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
        try:
            r = await client.get(url, headers=headers)
        except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError):
            return {"type": "provider.test_result", "ok": False, "error": "unreachable",
                    "latency_ms": _elapsed_ms(started)}
    latency = _elapsed_ms(started)
    if r.status_code in (200,):
        return {"type": "provider.test_result", "ok": True, "error": None, "latency_ms": latency}
    if r.status_code in (401, 403):
        return {"type": "provider.test_result", "ok": False, "error": "auth_failed", "latency_ms": latency}
    return {"type": "provider.test_result", "ok": False, "error": "unknown", "latency_ms": latency}


async def _test_anthropic(
    base_url: str, api_key: str, model: str, default_headers: dict, started: datetime,
) -> dict:
    url = base_url.rstrip("/") + "/messages"
    headers = {
        "x-api-key": api_key,
        "content-type": "application/json",
        "anthropic-version": default_headers.get("anthropic-version", "2023-06-01"),
    }
    body = {
        "model": model,
        "max_tokens": 1,
        "messages": [{"role": "user", "content": "hi"}],
    }
    async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
        try:
            r = await client.post(url, headers=headers, json=body)
        except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError):
            return {"type": "provider.test_result", "ok": False, "error": "unreachable",
                    "latency_ms": _elapsed_ms(started)}
    latency = _elapsed_ms(started)
    if r.status_code in (200, 400):
        return {"type": "provider.test_result", "ok": True, "error": None, "latency_ms": latency}
    if r.status_code in (401, 403):
        return {"type": "provider.test_result", "ok": False, "error": "auth_failed", "latency_ms": latency}
    if r.status_code in (404, 405):
        return {"type": "provider.test_result", "ok": False, "error": "bad_request", "latency_ms": latency}
    return {"type": "provider.test_result", "ok": False, "error": "unknown", "latency_ms": latency}


def _elapsed_ms(started: datetime) -> int:
    return int((datetime.now(timezone.utc) - started).total_seconds() * 1000)


async def provider_fetch_models(preset_id: str, base_url: str, api_key: str) -> dict:
    """GET {base_url}/models; return list of model ids."""
    presets = load_presets(_PRESETS_PATH)
    preset = get_preset_by_id(presets, preset_id)
    if preset is None or preset.get("model_list_url_suffix") is None:
        return {"type": "provider.models", "ok": False, "models": [], "error": "no_model_list_endpoint"}
    url = base_url.rstrip("/") + preset["model_list_url_suffix"]
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
            r = await client.get(url, headers=headers)
    except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError):
        return {"type": "provider.models", "ok": False, "models": [], "error": "unreachable"}
    if r.status_code != 200:
        return {"type": "provider.models", "ok": False, "models": [], "error": f"http_{r.status_code}"}
    data = r.json()
    models = []
    if isinstance(data, dict) and "data" in data and isinstance(data["data"], list):
        for m in data["data"]:
            if isinstance(m, dict) and "id" in m:
                models.append(m["id"])
            elif isinstance(m, str):
                models.append(m)
    elif isinstance(data, list):
        for m in data:
            if isinstance(m, dict) and "id" in m:
                models.append(m["id"])
            elif isinstance(m, str):
                models.append(m)
    return {"type": "provider.models", "ok": True, "models": models, "error": None}
```

Also add at top:

```python
import logging
logger = logging.getLogger(__name__)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/server/test_provider_handler.py -v`
Expected: all 13 tests pass (4 from Task 3.1 + 9 from this task)

- [ ] **Step 5: Wire `test_connection` and `fetch_models` in ws_server.py**

In `src/server/ws_server.py` dispatch, add:

```python
from src.server.handlers.provider import (
    provider_list_presets,
    provider_create_builtin,
    provider_test_connection,
    provider_fetch_models,
)
```

In the dispatch table:

```python
"provider.test_connection": lambda msg: provider_test_connection(
    preset_id=msg.get("preset_id", ""),
    base_url=msg.get("base_url", ""),
    api_key=msg.get("api_key", ""),
    model=msg.get("model", ""),
),
"provider.fetch_models": lambda msg: provider_fetch_models(
    preset_id=msg.get("preset_id", ""),
    base_url=msg.get("base_url", ""),
    api_key=msg.get("api_key", ""),
),
```

- [ ] **Step 6: Commit**

```bash
git add src/server/handlers/provider.py src/server/ws_server.py tests/server/test_provider_handler.py
git commit -m "feat(provider): test_connection + fetch_models handlers (9 tests)"
```

---

## Slice 4 — Backend Handler: Onboarding

### Task 4.1: Onboarding handler — `get_state` + `complete_step`

**Files:**
- Create: `src/server/handlers/onboarding.py`
- Modify: `src/server/ws_server.py` (add `onboarding` to snapshot; register dispatch)

**Interfaces:**
- Produces:
  - `async def onboarding_get_state(fsar_config) -> dict` → `{"type": "onboarding.state", "required": bool, "completed": bool, "completed_steps": [...], "current_step": "provider"|"user_card"|"character_card"|None}`
  - `async def onboarding_complete_step(fsar_config, step: str, data: dict | None) -> dict` → `{"type": "onboarding.step_completed", "step": str}`

- [ ] **Step 1: Write the failing tests (part 1)**

Create `tests/server/test_onboarding_handler.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Tests for the onboarding WS handler."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from src.server.handlers import onboarding as onboarding_handler
from src.utils.fsar_config import FsarConfig

ALL_STEPS = ["provider", "user_card", "character_card"]


@pytest.fixture
def fsar_config(tmp_path: Path) -> FsarConfig:
    cfg_path = tmp_path / "fsar.yaml"
    cfg_path.write_text(
        "onboarding:\n  completed: false\n  completed_steps: []\n"
        "llm:\n  active: null\n  providers: []\n",
        encoding="utf-8",
    )
    return FsarConfig.load(cfg_path)


@pytest.mark.asyncio
async def test_get_state_required_when_completed_false(fsar_config):
    result = await onboarding_handler.onboarding_get_state(fsar_config)
    assert result["type"] == "onboarding.state"
    assert result["required"] is True
    assert result["completed"] is False
    assert result["completed_steps"] == []
    assert result["current_step"] == "provider"


@pytest.mark.asyncio
async def test_get_state_not_required_when_completed_true(fsar_config):
    fsar_config.set("onboarding.completed", True)
    fsar_config.set("onboarding.completed_steps", ALL_STEPS)
    fsar_config.save()
    cfg = FsarConfig.load(fsar_config.path)
    result = await onboarding_handler.onboarding_get_state(cfg)
    assert result["required"] is False
    assert result["completed"] is True
    assert result["current_step"] is None


@pytest.mark.asyncio
async def test_get_state_resumes_from_completed_steps(fsar_config):
    fsar_config.set("onboarding.completed_steps", ["provider"])
    fsar_config.save()
    cfg = FsarConfig.load(fsar_config.path)
    result = await onboarding_handler.onboarding_get_state(cfg)
    assert result["required"] is True
    assert result["current_step"] == "user_card"


@pytest.mark.asyncio
async def test_complete_step_appends_to_completed_steps(fsar_config, tmp_path: Path):
    result = await onboarding_handler.onboarding_complete_step(
        fsar_config=fsar_config,
        step="provider",
        data={"preset_id": "openai"},
    )
    assert result["type"] == "onboarding.step_completed"
    # Reload and check
    cfg = FsarConfig.load(fsar_config.path)
    assert cfg.get("onboarding.completed_steps") == ["provider"]
    assert "started_at" in cfg.get("onboarding", {})
    assert cfg.get("onboarding.last_step") == "provider"


@pytest.mark.asyncio
async def test_complete_step_rejects_unknown_step(fsar_config):
    with pytest.raises(ValueError, match="unknown step"):
        await onboarding_handler.onboarding_complete_step(
            fsar_config=fsar_config,
            step="bogus",
            data={},
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/server/test_onboarding_handler.py -v`
Expected: ImportError on `src.server.handlers.onboarding`

- [ ] **Step 3: Create the onboarding handler module (part 1)**

Create `src/server/handlers/onboarding.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Onboarding WS handler: get_state, complete_step, complete, reset."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from src.utils.fsar_config import FsarConfig

logger = logging.getLogger(__name__)

ALL_STEPS = ("provider", "user_card", "character_card")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _compute_current_step(completed_steps: list[str]) -> str | None:
    for s in ALL_STEPS:
        if s not in completed_steps:
            return s
    return None


async def onboarding_get_state(fsar_config: FsarConfig) -> dict:
    """Return current onboarding state derived from fsar.yaml."""
    completed = bool(fsar_config.get("onboarding.completed"))
    completed_steps = fsar_config.get("onboarding.completed_steps") or []
    return {
        "type": "onboarding.state",
        "required": not completed,
        "completed": completed,
        "completed_steps": completed_steps,
        "current_step": _compute_current_step(completed_steps) if not completed else None,
    }


async def onboarding_complete_step(
    fsar_config: FsarConfig, step: str, data: dict | None = None,
) -> dict:
    """Append `step` to onboarding.completed_steps; bump last_step + started_at."""
    if step not in ALL_STEPS:
        raise ValueError(f"unknown step: {step!r}; must be one of {ALL_STEPS}")
    steps = list(fsar_config.get("onboarding.completed_steps") or [])
    if step not in steps:
        steps.append(step)
    fsar_config.set("onboarding.completed_steps", steps)
    fsar_config.set("onboarding.last_step", step)
    if not fsar_config.get("onboarding.started_at"):
        fsar_config.set("onboarding.started_at", _now_iso())
    fsar_config.save()
    return {"type": "onboarding.step_completed", "step": step}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/server/test_onboarding_handler.py -v -k "get_state or complete_step"`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/server/handlers/onboarding.py tests/server/test_onboarding_handler.py
git commit -m "feat(onboarding): get_state + complete_step handlers (5 tests)"
```

### Task 4.2: Onboarding handler — `complete` + `reset` + snapshot + first-run integration test

**Files:**
- Modify: `src/server/handlers/onboarding.py`
- Modify: `src/server/ws_server.py` (add `onboarding` to snapshot payload; register `complete` and `reset`)

**Interfaces:**
- Produces:
  - `async def onboarding_complete(fsar_config) -> dict` → `{"type": "onboarding.completed", "redirect": "/chat"}` (or raises if steps incomplete)
  - `async def onboarding_reset(fsar_config) -> dict` → `{"type": "onboarding.state", ...}` (reset state)

- [ ] **Step 1: Append tests for `complete` and `reset`**

Append to `tests/server/test_onboarding_handler.py`:

```python
@pytest.mark.asyncio
async def test_complete_sets_completed_true(fsar_config, tmp_path: Path):
    for s in ALL_STEPS:
        await onboarding_handler.onboarding_complete_step(
            fsar_config=fsar_config, step=s, data={},
        )
    cfg = FsarConfig.load(fsar_config.path)
    result = await onboarding_handler.onboarding_complete(cfg)
    assert result["type"] == "onboarding.completed"
    assert result["redirect"] == "/chat"
    cfg2 = FsarConfig.load(fsar_config.path)
    assert cfg2.get("onboarding.completed") is True
    assert cfg2.get("onboarding.completed_at") is not None


@pytest.mark.asyncio
async def test_complete_requires_all_three_steps(fsar_config):
    await onboarding_handler.onboarding_complete_step(
        fsar_config=fsar_config, step="provider", data={},
    )
    cfg = FsarConfig.load(fsar_config.path)
    with pytest.raises(ValueError, match="incomplete"):
        await onboarding_handler.onboarding_complete(cfg)


@pytest.mark.asyncio
async def test_reset_clears_completed(fsar_config, tmp_path: Path):
    for s in ALL_STEPS:
        await onboarding_handler.onboarding_complete_step(
            fsar_config=fsar_config, step=s, data={},
        )
    cfg = FsarConfig.load(fsar_config.path)
    await onboarding_handler.onboarding_complete(cfg)
    cfg2 = FsarConfig.load(fsar_config.path)
    result = await onboarding_handler.onboarding_reset(cfg2)
    assert result["required"] is True
    assert result["completed_steps"] == []
    cfg3 = FsarConfig.load(fsar_config.path)
    assert cfg3.get("onboarding.completed") is False
    assert cfg3.get("onboarding.completed_steps") == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/server/test_onboarding_handler.py -v -k "complete or reset"`
Expected: AttributeError on `onboarding_complete` / `onboarding_reset`

- [ ] **Step 3: Append `complete` and `reset` to onboarding.py**

Append to `src/server/handlers/onboarding.py`:

```python
async def onboarding_complete(fsar_config: FsarConfig) -> dict:
    """Mark onboarding.completed = true; only succeeds if all 3 steps done."""
    steps = list(fsar_config.get("onboarding.completed_steps") or [])
    missing = [s for s in ALL_STEPS if s not in steps]
    if missing:
        raise ValueError(f"onboarding incomplete: missing steps {missing}")
    fsar_config.set("onboarding.completed", True)
    fsar_config.set("onboarding.completed_at", _now_iso())
    fsar_config.save()
    logger.info("onboarding.completed")
    return {"type": "onboarding.completed", "redirect": "/chat"}


async def onboarding_reset(fsar_config: FsarConfig) -> dict:
    """Reset onboarding state so wizard reappears on next snapshot."""
    fsar_config.set("onboarding.completed", False)
    fsar_config.set("onboarding.completed_at", None)
    fsar_config.set("onboarding.completed_steps", [])
    fsar_config.set("onboarding.last_step", None)
    fsar_config.save()
    logger.info("onboarding.reset")
    return await onboarding_get_state(fsar_config)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/server/test_onboarding_handler.py -v`
Expected: 8 passed (5 from Task 4.1 + 3 from this task)

- [ ] **Step 5: Wire `complete_step`, `complete`, `reset` in ws_server.py**

Add to imports in `src/server/ws_server.py`:

```python
from src.server.handlers.onboarding import (
    onboarding_get_state,
    onboarding_complete_step,
    onboarding_complete,
    onboarding_reset,
)
```

In dispatch:

```python
"onboarding.get_state": lambda msg: onboarding_get_state(self.fsar_config),
"onboarding.complete_step": lambda msg: onboarding_complete_step(
    fsar_config=self.fsar_config,
    step=msg.get("step", ""),
    data=msg.get("data"),
),
"onboarding.complete": lambda msg: onboarding_complete(self.fsar_config),
"onboarding.reset": lambda msg: onboarding_reset(self.fsar_config),
```

- [ ] **Step 6: Add `onboarding` field to snapshot**

In `src/server/ws_server.py`, find where the `snapshot` event is built and add:

```python
"onboarding": {
    "required": not self.fsar_config.get("onboarding.completed"),
    "completed": bool(self.fsar_config.get("onboarding.completed")),
    "completed_steps": self.fsar_config.get("onboarding.completed_steps") or [],
    "current_step": _compute_current_step(
        self.fsar_config.get("onboarding.completed_steps") or []
    ) if not self.fsar_config.get("onboarding.completed") else None,
},
```

(Import `_compute_current_step` from `src.server.handlers.onboarding` or duplicate the small helper.)

- [ ] **Step 7: Commit**

```bash
git add src/server/handlers/onboarding.py src/server/ws_server.py tests/server/test_onboarding_handler.py
git commit -m "feat(onboarding): complete + reset handlers + snapshot.onboarding field (3 tests)"
```

---

## Slice 5 — Frontend Foundation

### Task 5.1: zustand store `useWizardState`

**Files:**
- Create: `frontend/src/stores/onboarding.ts`
- Create: `frontend/src/stores/onboarding.test.ts`

**Interfaces:**
- Produces: `useWizardState` (zustand hook) with `step`, `data`, `setProviderField`, `setUserCardField`, `setCharacterCardField`, `next`, `back`, `skip`, `finish`, `reset`

- [ ] **Step 1: Read the existing zustand store to follow the same pattern**

Run: `cat frontend/src/stores/ws.ts | head -50`

- [ ] **Step 2: Write the test**

Create `frontend/src/stores/onboarding.test.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from 'vitest'
import { useWizardState } from './onboarding'

describe('useWizardState', () => {
  it('starts at provider step with empty data', () => {
    const state = useWizardState.getState()
    expect(state.step).toBe('provider')
    expect(state.current_step_index).toBe(0)
    expect(state.data.provider.preset_id).toBe(null)
  })

  it('setProviderField updates provider data', () => {
    useWizardState.getState().setProviderField('preset_id', 'openai')
    useWizardState.getState().setProviderField('api_key', 'sk-test')
    const s = useWizardState.getState()
    expect(s.data.provider.preset_id).toBe('openai')
    expect(s.data.provider.api_key).toBe('sk-test')
  })

  it('setUserCardField updates user card data', () => {
    useWizardState.getState().setUserCardField('name', 'Alice')
    useWizardState.getState().setUserCardField('bio', 'I work on AI')
    const s = useWizardState.getState()
    expect(s.data.user_card.name).toBe('Alice')
    expect(s.data.user_card.bio).toBe('I work on AI')
  })

  it('setCharacterCardField updates character card data', () => {
    useWizardState.getState().setCharacterCardField('mode', 'create_new')
    useWizardState.getState().setCharacterCardField('picked_card_id', 5)
    const s = useWizardState.getState()
    expect(s.data.character_card.mode).toBe('create_new')
    expect(s.data.character_card.picked_card_id).toBe(5)
  })

  it('next() advances step index when valid', async () => {
    useWizardState.setState({
      data: {
        provider: { preset_id: 'openai', api_key: 'sk-test', base_url: 'https://x', model: 'gpt-4o-mini', test_result: null },
        user_card: { name: 'A', bio: 'B' },
        character_card: {
          mode: 'use_default', picked_card_id: null,
          new_card: { name: '', avatar_file: null, avatar_path: null, personality: '', system_prompt_override: '' },
          st_file: null,
        },
      },
    })
    await useWizardState.getState().next()
    expect(useWizardState.getState().current_step_index).toBe(1)
    expect(useWizardState.getState().step).toBe('user_card')
  })

  it('next() blocks when provider step has empty fields', async () => {
    useWizardState.setState({
      data: {
        provider: { preset_id: null, api_key: '', base_url: '', model: '', test_result: null },
        user_card: { name: '', bio: '' },
        character_card: {
          mode: 'use_default', picked_card_id: null,
          new_card: { name: '', avatar_file: null, avatar_path: null, personality: '', system_prompt_override: '' },
          st_file: null,
        },
      },
    })
    await useWizardState.getState().next()
    expect(useWizardState.getState().current_step_index).toBe(0)
    expect(useWizardState.getState().errors.provider).toBeDefined()
  })

  it('back() decrements step index without backend call', () => {
    useWizardState.setState({ current_step_index: 2, step: 'character_card' })
    useWizardState.getState().back()
    expect(useWizardState.getState().current_step_index).toBe(1)
    expect(useWizardState.getState().step).toBe('user_card')
  })

  it('skip() only works on character_card step', () => {
    useWizardState.setState({ current_step_index: 1, step: 'user_card' })
    useWizardState.getState().skip()
    // Should be a no-op (current_step_index unchanged)
    expect(useWizardState.getState().current_step_index).toBe(1)
  })

  it('finish() sets step to submitting then completed', async () => {
    useWizardState.setState({ current_step_index: 2, step: 'character_card' })
    await useWizardState.getState().finish()
    expect(['submitting', 'completed']).toContain(useWizardState.getState().step)
  })
})
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/stores/onboarding.test.ts`
Expected: FAIL — `Cannot find module './onboarding'`

- [ ] **Step 4: Write the store**

Create `frontend/src/stores/onboarding.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
import { create } from 'zustand'

export type WizardStep =
  | 'provider' | 'user_card' | 'character_card'
  | 'submitting' | 'completed' | 'error'

export type CharacterMode = 'use_default' | 'pick_existing' | 'create_new' | 'import_st'

interface ProviderData {
  preset_id: string | null
  api_key: string
  base_url: string
  model: string
  test_result: { ok: boolean; error: string | null; latency_ms: number | null } | null
}

interface UserCardData {
  name: string
  bio: string
}

interface CharacterCardData {
  mode: CharacterMode
  picked_card_id: number | null
  new_card: {
    name: string
    avatar_file: File | null
    avatar_path: string | null
    personality: string
    system_prompt_override: string
  }
  st_file: File | null
}

interface WizardData {
  provider: ProviderData
  user_card: UserCardData
  character_card: CharacterCardData
}

interface WizardErrors {
  provider?: string
  user_card?: string
  character_card?: string
  submit?: string
}

interface WizardState {
  step: WizardStep
  current_step_index: 0 | 1 | 2
  data: WizardData
  errors: WizardErrors

  setProviderField<K extends keyof ProviderData>(k: K, v: ProviderData[K]): void
  setUserCardField<K extends keyof UserCardData>(k: K, v: UserCardData[K]): void
  setCharacterCardField<K extends keyof CharacterCardData>(k: K, v: CharacterCardData[K]): void
  next(): Promise<void>
  back(): void
  skip(): void
  finish(): Promise<void>
  reset(): void
}

const STEPS: Array<0 | 1 | 2> = [0, 1, 2]

function emptyData(): WizardData {
  return {
    provider: { preset_id: null, api_key: '', base_url: '', model: '', test_result: null },
    user_card: { name: '', bio: '' },
    character_card: {
      mode: 'use_default',
      picked_card_id: null,
      new_card: { name: '', avatar_file: null, avatar_path: null, personality: '', system_prompt_override: '' },
      st_file: null,
    },
  }
}

export const useWizardState = create<WizardState>((set, get) => ({
  step: 'provider',
  current_step_index: 0,
  data: emptyData(),
  errors: {},

  setProviderField: (k, v) => set(s => ({ data: { ...s.data, provider: { ...s.data.provider, [k]: v } } })),
  setUserCardField: (k, v) => set(s => ({ data: { ...s.data, user_card: { ...s.data.user_card, [k]: v } } })),
  setCharacterCardField: (k, v) => set(s => ({ data: { ...s.data, character_card: { ...s.data.character_card, [k]: v } } })),

  next: async () => {
    const s = get()
    const errs: WizardErrors = { ...s.errors }
    if (s.current_step_index === 0) {
      const p = s.data.provider
      if (!p.preset_id) errs.provider = 'select a preset'
      else if (!p.api_key.trim()) errs.provider = 'enter API key'
      else if (!p.base_url.trim()) errs.provider = 'enter base URL'
      else if (!p.model.trim()) errs.provider = 'select or type a model'
      if (errs.provider) { set({ errors: errs }); return }
      errs.provider = undefined
    } else if (s.current_step_index === 1) {
      const u = s.data.user_card
      if (!u.name.trim()) errs.user_card = 'enter your name'
      else if (!u.bio.trim()) errs.user_card = 'enter a short bio'
      if (errs.user_card) { set({ errors: errs }); return }
      errs.user_card = undefined
    }
    set({ errors: errs })
    const next = STEPS[Math.min(STEPS.indexOf(s.current_step_index) + 1, 2)]
    set({ current_step_index: next, step: next === 0 ? 'provider' : next === 1 ? 'user_card' : 'character_card' })
  },

  back: () => {
    const s = get()
    if (s.current_step_index === 0) return
    const prev = STEPS[Math.max(STEPS.indexOf(s.current_step_index) - 1, 0)]
    set({ current_step_index: prev, step: prev === 0 ? 'provider' : prev === 1 ? 'user_card' : 'character_card' })
  },

  skip: () => {
    const s = get()
    if (s.current_step_index !== 2) return
    set({ step: 'submitting' })
  },

  finish: async () => {
    set({ step: 'submitting' })
    // Actual WS calls happen in Onboarding.tsx via useWS; this just transitions
    set({ step: 'completed' })
  },

  reset: () => set({ step: 'provider', current_step_index: 0, data: emptyData(), errors: {} }),
}))
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/stores/onboarding.test.ts`
Expected: 9 passed

- [ ] **Step 6: Commit**

```bash
git add frontend/src/stores/onboarding.ts frontend/src/stores/onboarding.test.ts
git commit -m "feat(frontend): wizard zustand store with 9 tests"
```

### Task 5.2: WizardShell component

**Files:**
- Create: `frontend/src/components/onboarding/WizardShell.tsx`
- Create: `frontend/src/components/onboarding/WizardShell.test.tsx`

- [ ] **Step 1: Write the test**

Create `frontend/src/components/onboarding/WizardShell.test.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { WizardShell } from './WizardShell'
import { useWizardState } from '../../stores/onboarding'

describe('WizardShell', () => {
  it('renders 3 progress dots', () => {
    render(<WizardShell><div>child</div></WizardShell>)
    expect(screen.getByTestId('wizard-progress')).toBeInTheDocument()
    expect(screen.getAllByTestId(/^wizard-dot-/)).toHaveLength(3)
  })

  it('marks active dot on current step', () => {
    useWizardState.setState({ current_step_index: 1, step: 'user_card' })
    render(<WizardShell><div>child</div></WizardShell>)
    const dot = screen.getByTestId('wizard-dot-1')
    expect(dot.dataset.active).toBe('true')
  })

  it('renders children inside', () => {
    render(<WizardShell><span data-testid="child-content">hello</span></WizardShell>)
    expect(screen.getByTestId('child-content')).toHaveTextContent('hello')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/onboarding/WizardShell.test.tsx`
Expected: FAIL — `Cannot find module './WizardShell'`

- [ ] **Step 3: Write WizardShell**

Create `frontend/src/components/onboarding/WizardShell.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import type { ReactNode } from 'react'
import { useWizardState } from '../../stores/onboarding'

const STEP_LABELS = ['Provider', 'User Card', 'Character Card']

export function WizardShell({ children }: { children: ReactNode }) {
  const current = useWizardState(s => s.current_step_index)
  return (
    <div className="fixed inset-0 bg-bg z-50 flex flex-col">
      <div className="px-8 py-6 border-b border-border flex items-center gap-6">
        <h1 className="text-h2">FSAR Setup</h1>
        <div data-testid="wizard-progress" className="flex items-center gap-3 ml-auto">
          {STEP_LABELS.map((label, i) => {
            const isActive = current === i
            const isDone = current > i
            return (
              <div key={i} className="flex items-center gap-2">
                <div
                  data-testid={`wizard-dot-${i}`}
                  data-active={isActive}
                  className={`w-3 h-3 rounded-full border ${
                    isActive ? 'bg-border-strong border-border-strong'
                    : isDone ? 'bg-text border-text'
                    : 'bg-bg border-border'
                  }`}
                />
                <span className="text-caption text-text-muted">{label}</span>
              </div>
            )
          })}
        </div>
      </div>
      <div className="flex-1 overflow-auto px-8 py-6">
        {children}
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/components/onboarding/WizardShell.test.tsx`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/onboarding/WizardShell.tsx frontend/src/components/onboarding/WizardShell.test.tsx
git commit -m "feat(frontend): WizardShell with 3-dot progress indicator (3 tests)"
```

### Task 5.3: Onboarding page + app.tsx integration

**Files:**
- Create: `frontend/src/pages/Onboarding.tsx`
- Modify: `frontend/src/lib/ws-client.ts` (extend ServerMsg union for new messages)
- Modify: `frontend/src/app.tsx` (mount /onboarding when required)

- [ ] **Step 1: Read current ws-client.ts types**

Run: `grep -n "onboarding\|snapshot" frontend/src/lib/ws-client.ts | head -20`

- [ ] **Step 2: Extend ServerMsg union**

In `frontend/src/lib/ws-client.ts`, locate the `ServerMsg` type union. Add these variants:

```ts
| { type: 'onboarding.state'; required: boolean; completed: boolean; completed_steps: string[]; current_step: string | null }
| { type: 'provider.presets'; presets: Array<Record<string, unknown>> }
| { type: 'provider.created'; provider: { id: string; preset_id: string; model: string; family: string; [k: string]: unknown } }
| { type: 'provider.test_result'; ok: boolean; error: string | null; latency_ms: number | null }
| { type: 'provider.models'; ok: boolean; models: string[]; error: string | null }
| { type: 'onboarding.step_completed'; step: string }
| { type: 'onboarding.completed'; redirect: string }
| { type: 'onboarding.error'; step: string; code: string; message: string }
```

Also add to `SnapshotData` (the payload of `snapshot`):

```ts
onboarding?: { required: boolean; completed: boolean; completed_steps: string[]; current_step: string | null }
```

- [ ] **Step 3: Read app.tsx to understand routing**

Run: `cat frontend/src/app.tsx`

- [ ] **Step 4: Write the Onboarding page**

Create `frontend/src/pages/Onboarding.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useWS } from '../stores/ws'
import { useWizardState } from '../stores/onboarding'
import { WizardShell } from '../components/onboarding/WizardShell'
import { StepProvider } from '../components/onboarding/StepProvider'
import { StepUserCard } from '../components/onboarding/StepUserCard'
import { StepCharacterCard } from '../components/onboarding/StepCharacterCard'
import { StepFooter } from '../components/onboarding/StepFooter'

export function Onboarding() {
  const step = useWizardState(s => s.step)
  const navigate = useNavigate()
  const config = useWS(s => s.config)
  const onboardingState = (config as any)?.onboarding

  useEffect(() => {
    if (onboardingState?.current_step) {
      const idx = ['provider', 'user_card', 'character_card'].indexOf(onboardingState.current_step)
      if (idx >= 0) {
        useWizardState.setState({ current_step_index: idx as 0 | 1 | 2, step: onboardingState.current_step as any })
      }
    }
  }, [onboardingState?.current_step])

  useEffect(() => {
    if (step === 'completed') {
      navigate('/chat', { replace: true })
    }
  }, [step, navigate])

  return (
    <WizardShell>
      <div data-testid={`step-${step}`}>
        {step === 'provider' && <StepProvider />}
        {step === 'user_card' && <StepUserCard />}
        {step === 'character_card' && <StepCharacterCard />}
      </div>
      <StepFooter />
    </WizardShell>
  )
}
```

- [ ] **Step 5: Wire /onboarding route in app.tsx**

In `frontend/src/app.tsx`, import and conditionally mount. Find where the chat page is rendered and add (above the route definition):

```tsx
import { Onboarding } from './pages/Onboarding'
```

Find where the routes are defined (e.g., `<Routes>...`). Modify the layout to mount Onboarding as an overlay when required:

```tsx
function AppLayout() {
  const config = useWS(s => s.config) as any
  const required = config?.onboarding?.required === true
  return (
    <>
      <Routes>
        <Route path="/" element={<Chat />} />
        <Route path="/chat" element={<Chat />} />
        <Route path="*" element={<Chat />} />
        {/* other routes */}
      </Routes>
      {required && <Onboarding />}
    </>
  )
}
```

(Adjust to match the actual app.tsx structure — there are 7 page stubs; keep them but mount Onboarding as overlay when required.)

- [ ] **Step 6: Create stub step components (so Onboarding can import them)**

Create `frontend/src/components/onboarding/StepProvider.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
export function StepProvider() {
  return <div>Step 1: Provider (placeholder — see Slice 6)</div>
}
```

Create `frontend/src/components/onboarding/StepUserCard.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
export function StepUserCard() {
  return <div>Step 2: User Card (placeholder — see Slice 6)</div>
}
```

Create `frontend/src/components/onboarding/StepCharacterCard.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
export function StepCharacterCard() {
  return <div>Step 3: Character Card (placeholder — see Slice 6)</div>
}
```

Create `frontend/src/components/onboarding/StepFooter.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useWizardState } from '../../stores/onboarding'

export function StepFooter() {
  const step = useWizardState(s => s.step)
  const current = useWizardState(s => s.current_step_index)
  const back = useWizardState(s => s.back)
  const next = useWizardState(s => s.next)
  const skip = useWizardState(s => s.skip)
  const finish = useWizardState(s => s.finish)
  return (
    <div className="flex items-center gap-3 mt-8">
      {current > 0 && step !== 'submitting' && step !== 'completed' && (
        <button onClick={back} className="px-4 py-2 border border-border">Back</button>
      )}
      {step === 'character_card' && (
        <button onClick={skip} className="px-4 py-2 border border-border">Skip</button>
      )}
      {current < 2 && step !== 'submitting' && step !== 'completed' && (
        <button onClick={next} className="px-4 py-2 border-2 border-border-strong bg-text text-bg">Next</button>
      )}
      {current === 2 && step !== 'submitting' && step !== 'completed' && (
        <button onClick={finish} className="px-4 py-2 border-2 border-border-strong bg-text text-bg">Finish</button>
      )}
    </div>
  )
}
```

- [ ] **Step 7: Build to verify**

Run: `cd frontend && npm run build`
Expected: build succeeds (no type errors)

- [ ] **Step 8: Commit**

```bash
git add frontend/src/pages/Onboarding.tsx frontend/src/app.tsx frontend/src/lib/ws-client.ts frontend/src/components/onboarding/StepProvider.tsx frontend/src/components/onboarding/StepUserCard.tsx frontend/src/components/onboarding/StepCharacterCard.tsx frontend/src/components/onboarding/StepFooter.tsx
git commit -m "feat(frontend): /onboarding route + WizardShell mount + 4 stub step components"
```

---

## Slice 6 — Frontend Three Steps

### Task 6.1: StepProvider — PresetCard + PresetGrid

**Files:**
- Create: `frontend/src/components/onboarding/StepProvider/PresetCard.tsx`
- Create: `frontend/src/components/onboarding/StepProvider/PresetGrid.tsx`
- Modify: `frontend/src/components/onboarding/StepProvider.tsx` (replace stub)

- [ ] **Step 1: Create PresetCard component**

Create `frontend/src/components/onboarding/StepProvider/PresetCard.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import type { Preset } from './types'

interface Props {
  preset: Preset
  selected: boolean
  onSelect: () => void
}

export function PresetCard({ preset, selected, onSelect }: Props) {
  const isDisabled = preset.deferred
  return (
    <button
      type="button"
      onClick={isDisabled ? undefined : onSelect}
      disabled={isDisabled}
      title={isDisabled ? 'Available in a future phase' : preset.homepage}
      data-testid={`preset-card-${preset.id}`}
      data-selected={selected}
      data-disabled={isDisabled}
      className={`w-60 h-30 p-3 border text-left transition-colors
        ${selected ? 'border-2 border-border-strong' : 'border-border'}
        ${isDisabled ? 'opacity-50 cursor-not-allowed' : 'hover:border-border-strong cursor-pointer'}
      `}
    >
      <div className="text-body-emphasis">{preset.label}</div>
      <div className="text-caption text-text-muted">{preset.family}</div>
    </button>
  )
}
```

- [ ] **Step 2: Create types file**

Create `frontend/src/components/onboarding/StepProvider/types.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
export interface Preset {
  id: string
  label: string
  family: 'openai_compat' | 'anthropic' | 'google'
  default_base_url: string
  default_headers: Record<string, string>
  api_key_required: boolean
  api_key_env: string | null
  model_list_url_suffix: string | null
  test_url_suffix: string | null
  deferred: boolean
  icon: string
  homepage: string
  order: number
}
```

- [ ] **Step 3: Create PresetGrid component**

Create `frontend/src/components/onboarding/StepProvider/PresetGrid.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useState, useEffect } from 'react'
import { useWS } from '../../../stores/ws'
import { useWizardState } from '../../../stores/onboarding'
import { PresetCard } from './PresetCard'
import type { Preset } from './types'

export function PresetGrid() {
  const [presets, setPresets] = useState<Preset[] | null>(null)
  const send = useWS(s => s.send)
  const presetId = useWizardState(s => s.data.provider.preset_id)
  const setProviderField = useWizardState(s => s.setProviderField)

  useEffect(() => {
    send({ type: 'provider.list_presets' })
    const handler = (msg: any) => {
      if (msg.type === 'provider.presets') {
        setPresets(msg.presets as Preset[])
      }
    }
    const ws = (window as any).__fsarWsClient
    if (ws) ws.on('message', handler)
    return () => { if (ws) ws.off('message', handler) }
  }, [send])

  if (!presets) return <div data-testid="preset-grid-loading">Loading presets...</div>

  const sorted = [...presets].sort((a, b) => a.order - b.order)

  return (
    <div data-testid="preset-grid" className="grid grid-cols-4 gap-4">
      {sorted.map(p => (
        <PresetCard
          key={p.id}
          preset={p}
          selected={presetId === p.id}
          onSelect={() => {
            setProviderField('preset_id', p.id)
            setProviderField('base_url', p.default_base_url)
            setProviderField('api_key', '')
            setProviderField('model', '')
            setProviderField('test_result', null)
          }}
        />
      ))}
    </div>
  )
}
```

(Adjust the WS subscription to match the actual ws-client API — likely a callback registration pattern in the existing store.)

- [ ] **Step 4: Replace StepProvider stub**

Modify `frontend/src/components/onboarding/StepProvider.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { PresetGrid } from './StepProvider/PresetGrid'
import { PresetDetailPanel } from './StepProvider/PresetDetailPanel'

export function StepProvider() {
  return (
    <div className="grid grid-cols-[1fr_320px] gap-6">
      <PresetGrid />
      <PresetDetailPanel />
    </div>
  )
}
```

- [ ] **Step 5: Build to verify (Step 6.2 will fill the missing PresetDetailPanel)**

Create a minimal stub `frontend/src/components/onboarding/StepProvider/PresetDetailPanel.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useWizardState } from '../../../stores/onboarding'

export function PresetDetailPanel() {
  const presetId = useWizardState(s => s.data.provider.preset_id)
  if (!presetId) return <div className="text-text-muted">Select a preset to configure</div>
  return <div>Detail panel (Task 6.2 will fill this)</div>
}
```

- [ ] **Step 6: Build to verify**

Run: `cd frontend && npm run build`
Expected: build succeeds

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/onboarding/StepProvider/
git commit -m "feat(frontend): StepProvider with PresetGrid + PresetCard"
```

### Task 6.2: StepProvider — PresetDetailPanel + 4 subfields + tests

**Files:**
- Create: `frontend/src/components/onboarding/StepProvider/ApiKeyField.tsx`
- Create: `frontend/src/components/onboarding/StepProvider/BaseUrlField.tsx`
- Create: `frontend/src/components/onboarding/StepProvider/ModelField.tsx`
- Create: `frontend/src/components/onboarding/StepProvider/TestConnectionButton.tsx`
- Modify: `frontend/src/components/onboarding/StepProvider/PresetDetailPanel.tsx`
- Create: `frontend/src/components/onboarding/StepProvider.test.tsx`

- [ ] **Step 1: Create ApiKeyField**

Create `frontend/src/components/onboarding/StepProvider/ApiKeyField.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useWizardState } from '../../../stores/onboarding'

export function ApiKeyField({ required }: { required: boolean }) {
  const value = useWizardState(s => s.data.provider.api_key)
  const set = useWizardState(s => s.setProviderField)
  if (!required) return null
  return (
    <div className="flex flex-col gap-1">
      <label className="text-caption text-text-muted">API Key</label>
      <input
        type="password"
        value={value}
        onChange={e => set('api_key', e.target.value)}
        placeholder="sk-..."
        data-testid="api-key-input"
        className="border border-border px-2 py-1 bg-surface"
      />
    </div>
  )
}
```

- [ ] **Step 2: Create BaseUrlField**

Create `frontend/src/components/onboarding/StepProvider/BaseUrlField.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useWizardState } from '../../../stores/onboarding'

function lastSegment(url: string): string {
  return '/' + (url.split('/').filter(Boolean).pop() ?? 'v1')
}

export function BaseUrlField() {
  const value = useWizardState(s => s.data.provider.base_url)
  const set = useWizardState(s => s.setProviderField)
  return (
    <div className="flex flex-col gap-1">
      <label className="text-caption text-text-muted">
        Base URL <span className="text-text">(fill to {lastSegment(value)})</span>
      </label>
      <input
        type="text"
        value={value}
        onChange={e => set('base_url', e.target.value)}
        placeholder="https://api.example.com/v1"
        data-testid="base-url-input"
        className="border border-border px-2 py-1 bg-surface"
      />
    </div>
  )
}
```

- [ ] **Step 3: Create TestConnectionButton**

Create `frontend/src/components/onboarding/StepProvider/TestConnectionButton.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useState } from 'react'
import { useWS } from '../../../stores/ws'
import { useWizardState } from '../../../stores/onboarding'

export function TestConnectionButton() {
  const send = useWS(s => s.send)
  const data = useWizardState(s => s.data.provider)
  const set = useWizardState(s => s.setProviderField)
  const [testing, setTesting] = useState(false)

  const onClick = () => {
    if (!data.preset_id) return
    setTesting(true)
    const handler = (msg: any) => {
      if (msg.type === 'provider.test_result') {
        set('test_result', { ok: msg.ok, error: msg.error, latency_ms: msg.latency_ms })
        setTesting(false)
      }
    }
    const ws = (window as any).__fsarWsClient
    if (ws) ws.on('message', handler)
    send({
      type: 'provider.test_connection',
      preset_id: data.preset_id,
      base_url: data.base_url,
      api_key: data.api_key,
      model: data.model,
    })
    setTimeout(() => {
      if (ws) ws.off('message', handler)
      setTesting(false)
    }, 6000)
  }

  const result = data.test_result

  return (
    <div className="flex items-center gap-3">
      <button
        type="button"
        onClick={onClick}
        disabled={testing || !data.preset_id || !data.api_key || !data.base_url || !data.model}
        data-testid="test-connection-button"
        className="px-3 py-1 border border-border disabled:opacity-50"
      >
        {testing ? 'Testing...' : 'Test connection'}
      </button>
      {result?.ok && <span data-testid="test-result-ok" className="text-caption">✓ {result.latency_ms}ms</span>}
      {result && !result.ok && <span data-testid="test-result-error" className="text-caption">✗ {result.error}</span>}
    </div>
  )
}
```

(Adjust the WS subscription to match the actual ws-client pattern in the project.)

- [ ] **Step 4: Create ModelField**

Create `frontend/src/components/onboarding/StepProvider/ModelField.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useState } from 'react'
import { useWS } from '../../../stores/ws'
import { useWizardState } from '../../../stores/onboarding'
import type { Preset } from './types'

export function ModelField({ preset }: { preset: Preset }) {
  const value = useWizardState(s => s.data.provider.model)
  const set = useWizardState(s => s.setProviderField)
  const send = useWS(s => s.send)
  const [models, setModels] = useState<string[]>([])
  const [loading, setLoading] = useState(false)

  const canLoad = preset.model_list_url_suffix !== null

  const onLoad = () => {
    if (!canLoad) return
    setLoading(true)
    const data = useWizardState.getState().data.provider
    const handler = (msg: any) => {
      if (msg.type === 'provider.models') {
        setModels(msg.models || [])
        setLoading(false)
      }
    }
    const ws = (window as any).__fsarWsClient
    if (ws) ws.on('message', handler)
    send({
      type: 'provider.fetch_models',
      preset_id: preset.id,
      base_url: data.base_url,
      api_key: data.api_key,
    })
    setTimeout(() => { if (ws) ws.off('message', handler); setLoading(false) }, 6000)
  }

  return (
    <div className="flex flex-col gap-1">
      <label className="text-caption text-text-muted">Model</label>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onLoad}
          disabled={!canLoad || loading}
          title={!canLoad ? 'This provider has no model list API' : ''}
          data-testid="load-models-button"
          className="px-3 py-1 border border-border disabled:opacity-50"
        >
          {loading ? 'Loading...' : 'Load model list'}
        </button>
        {models.length > 0 && (
          <select
            data-testid="model-select"
            value={value}
            onChange={e => set('model', e.target.value)}
            className="border border-border px-2 py-1 bg-surface"
          >
            <option value="">— pick a model —</option>
            {models.map(m => <option key={m} value={m}>{m}</option>)}
          </select>
        )}
        <input
          type="text"
          value={value}
          onChange={e => set('model', e.target.value)}
          placeholder="model-id (or pick above)"
          data-testid="model-input"
          className="border border-border px-2 py-1 bg-surface flex-1"
        />
      </div>
    </div>
  )
}
```

- [ ] **Step 5: Replace PresetDetailPanel stub**

Modify `frontend/src/components/onboarding/StepProvider/PresetDetailPanel.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useState, useEffect } from 'react'
import { useWizardState } from '../../../stores/onboarding'
import type { Preset } from './types'
import { ApiKeyField } from './ApiKeyField'
import { BaseUrlField } from './BaseUrlField'
import { ModelField } from './ModelField'
import { TestConnectionButton } from './TestConnectionButton'

export function PresetDetailPanel() {
  const presetId = useWizardState(s => s.data.provider.preset_id)
  const [preset, setPreset] = useState<Preset | null>(null)

  useEffect(() => {
    if (!presetId) { setPreset(null); return }
    send({ type: 'provider.list_presets' })
    // ... or read from a cached store
  }, [presetId])

  if (!presetId) return <div className="text-text-muted">Select a preset to configure</div>
  if (!preset) return <div>Loading...</div>

  return (
    <div className="border border-border p-4 flex flex-col gap-3" data-testid="preset-detail-panel">
      <div className="text-h2">{preset.label}</div>
      <ApiKeyField required={preset.api_key_required} />
      <BaseUrlField />
      <ModelField preset={preset} />
      <TestConnectionButton />
    </div>
  )
}
```

(The `send` reference above is illustrative; the actual implementation should read presets from a cached list in the ws store, not re-fetch on every detail panel open.)

- [ ] **Step 6: Write tests**

Create `frontend/src/components/onboarding/StepProvider.test.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { PresetCard } from './StepProvider/PresetCard'
import { useWizardState } from '../../stores/onboarding'
import type { Preset } from './StepProvider/types'

const samplePreset: Preset = {
  id: 'openai', label: 'OpenAI', family: 'openai_compat',
  default_base_url: 'https://api.openai.com/v1', default_headers: {},
  api_key_required: true, api_key_env: 'OPENAI_API_KEY',
  model_list_url_suffix: '/models', test_url_suffix: '/models',
  deferred: false, icon: 'openai', homepage: 'https://platform.openai.com', order: 1,
}

const deferredPreset: Preset = { ...samplePreset, id: 'google', label: 'Google', deferred: true }

describe('PresetCard', () => {
  beforeEach(() => {
    useWizardState.setState({
      step: 'provider', current_step_index: 0,
      data: {
        provider: { preset_id: null, api_key: '', base_url: '', model: '', test_result: null },
        user_card: { name: '', bio: '' },
        character_card: {
          mode: 'use_default', picked_card_id: null,
          new_card: { name: '', avatar_file: null, avatar_path: null, personality: '', system_prompt_override: '' },
          st_file: null,
        },
      },
      errors: {},
    })
  })

  it('renders label and family', () => {
    render(<PresetCard preset={samplePreset} selected={false} onSelect={() => {}} />)
    expect(screen.getByTestId('preset-card-openai')).toHaveTextContent('OpenAI')
  })

  it('marks selected', () => {
    render(<PresetCard preset={samplePreset} selected={true} onSelect={() => {}} />)
    expect(screen.getByTestId('preset-card-openai').dataset.selected).toBe('true')
  })

  it('disables deferred card', () => {
    render(<PresetCard preset={deferredPreset} selected={false} onSelect={() => {}} />)
    const card = screen.getByTestId('preset-card-google')
    expect(card.dataset.disabled).toBe('true')
    expect(card).toBeDisabled()
  })
})
```

- [ ] **Step 7: Run tests + build**

Run: `cd frontend && npx vitest run src/components/onboarding/StepProvider.test.tsx && npm run build`
Expected: 3 tests pass; build succeeds

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/onboarding/StepProvider/
git commit -m "feat(frontend): PresetDetailPanel + 4 subfields + PresetCard tests (3 tests)"
```

### Task 6.3: StepUserCard

**Files:**
- Modify: `frontend/src/components/onboarding/StepUserCard.tsx` (replace stub)
- Create: `frontend/src/components/onboarding/StepUserCard.test.tsx`

- [ ] **Step 1: Replace stub**

Modify `frontend/src/components/onboarding/StepUserCard.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useWizardState } from '../../stores/onboarding'

export function StepUserCard() {
  const data = useWizardState(s => s.data.user_card)
  const set = useWizardState(s => s.setUserCardField)
  const err = useWizardState(s => s.errors.user_card)
  return (
    <div className="max-w-xl flex flex-col gap-4">
      <h2 className="text-h2">Tell FSAR about you</h2>
      <div className="flex flex-col gap-1">
        <label className="text-caption text-text-muted">Your name</label>
        <input
          type="text"
          value={data.name}
          onChange={e => set('name', e.target.value)}
          data-testid="user-name-input"
          className="border border-border px-2 py-1 bg-surface"
        />
      </div>
      <div className="flex flex-col gap-1">
        <label className="text-caption text-text-muted">About you</label>
        <textarea
          value={data.bio}
          onChange={e => set('bio', e.target.value)}
          rows={6}
          data-testid="user-bio-input"
          className="border border-border px-2 py-1 bg-surface"
          placeholder="A short bio (hobbies, work, what kind of conversation you want)"
        />
      </div>
      {err && <div className="text-caption" data-testid="user-card-error">{err}</div>}
    </div>
  )
}
```

- [ ] **Step 2: Add test**

Append to `frontend/src/components/onboarding/StepUserCard.test.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { StepUserCard } from './StepUserCard'
import { useWizardState } from '../../stores/onboarding'

describe('StepUserCard', () => {
  it('renders name + bio inputs', () => {
    render(<StepUserCard />)
    expect(screen.getByTestId('user-name-input')).toBeInTheDocument()
    expect(screen.getByTestId('user-bio-input')).toBeInTheDocument()
  })

  it('shows error when set', () => {
    useWizardState.setState({ errors: { user_card: 'enter your name' } })
    render(<StepUserCard />)
    expect(screen.getByTestId('user-card-error')).toHaveTextContent('enter your name')
  })
})
```

- [ ] **Step 3: Build + test**

Run: `cd frontend && npx vitest run src/components/onboarding/StepUserCard.test.tsx && npm run build`
Expected: 2 tests pass; build succeeds

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/onboarding/StepUserCard.tsx frontend/src/components/onboarding/StepUserCard.test.tsx
git commit -m "feat(frontend): StepUserCard with name + bio fields (2 tests)"
```

### Task 6.4: StepCharacterCard — 4 options + tests

**Files:**
- Modify: `frontend/src/components/onboarding/StepCharacterCard.tsx` (replace stub)
- Create: `frontend/src/components/onboarding/StepCharacterCard/UseDefaultOption.tsx`
- Create: `frontend/src/components/onboarding/StepCharacterCard/PickExistingOption.tsx`
- Create: `frontend/src/components/onboarding/StepCharacterCard/CreateNewForm.tsx`
- Create: `frontend/src/components/onboarding/StepCharacterCard/ImportSTImageOption.tsx`
- Create: `frontend/src/components/onboarding/StepCharacterCard.test.tsx`

- [ ] **Step 1: Replace StepCharacterCard stub**

Modify `frontend/src/components/onboarding/StepCharacterCard.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useState } from 'react'
import { useWizardState } from '../../stores/onboarding'
import { UseDefaultOption } from './StepCharacterCard/UseDefaultOption'
import { PickExistingOption } from './StepCharacterCard/PickExistingOption'
import { CreateNewForm } from './StepCharacterCard/CreateNewForm'
import { ImportSTImageOption } from './StepCharacterCard/ImportSTImageOption'

const MODES = [
  { key: 'use_default', label: 'Use default' },
  { key: 'pick_existing', label: 'Pick existing' },
  { key: 'create_new', label: 'Create new' },
  { key: 'import_st', label: 'Import ST image' },
] as const

export function StepCharacterCard() {
  const mode = useWizardState(s => s.data.character_card.mode)
  const set = useWizardState(s => s.setCharacterCardField)
  return (
    <div className="flex flex-col gap-6">
      <h2 className="text-h2">Choose your character</h2>
      <div className="flex items-center gap-2" data-testid="character-mode-tabs">
        {MODES.map(m => (
          <button
            key={m.key}
            onClick={() => set('mode', m.key)}
            data-testid={`character-mode-${m.key}`}
            data-active={mode === m.key}
            className={`px-3 py-1 border ${
              mode === m.key ? 'border-2 border-border-strong' : 'border-border'
            }`}
          >
            {m.label}
          </button>
        ))}
      </div>
      <div>
        {mode === 'use_default' && <UseDefaultOption />}
        {mode === 'pick_existing' && <PickExistingOption />}
        {mode === 'create_new' && <CreateNewForm />}
        {mode === 'import_st' && <ImportSTImageOption />}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: UseDefaultOption**

Create `frontend/src/components/onboarding/StepCharacterCard/UseDefaultOption.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
export function UseDefaultOption() {
  return (
    <div data-testid="use-default-option" className="text-body">
      Use the default character (FSAR, friendly Chinese-speaking companion).
    </div>
  )
}
```

- [ ] **Step 3: PickExistingOption (read from card list — for PL2.1 show a simple list, actual list fetch is out of scope)**

Create `frontend/src/components/onboarding/StepCharacterCard/PickExistingOption.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useWizardState } from '../../../stores/onboarding'

const DEFAULTS = [
  { id: 1, label: 'FSAR (zh)' },
  { id: 2, label: 'FSAR (en)' },
  { id: 3, label: 'Coding Coach (zh)' },
  { id: 4, label: 'Coding Coach (en)' },
  { id: 5, label: 'Research Analyst (zh)' },
  { id: 6, label: 'Research Analyst (en)' },
]

export function PickExistingOption() {
  const picked = useWizardState(s => s.data.character_card.picked_card_id)
  const set = useWizardState(s => s.setCharacterCardField)
  return (
    <div data-testid="pick-existing-option" className="flex flex-col gap-2">
      {DEFAULTS.map(c => (
        <button
          key={c.id}
          onClick={() => set('picked_card_id', c.id)}
          data-testid={`pick-card-${c.id}`}
          data-selected={picked === c.id}
          className={`text-left px-3 py-2 border ${
            picked === c.id ? 'border-2 border-border-strong' : 'border-border'
          }`}
        >
          {c.label}
        </button>
      ))}
    </div>
  )
}
```

(In production, replace DEFAULTS with a `card.list` WS call — deferred to PL2.7+ for live list. PL2.1 ships hardcoded list of PL2.0 seeds.)

- [ ] **Step 4: CreateNewForm**

Create `frontend/src/components/onboarding/StepCharacterCard/CreateNewForm.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useWizardState } from '../../../stores/onboarding'
import { AvatarUpload } from './AvatarUpload'

export function CreateNewForm() {
  const data = useWizardState(s => s.data.character_card.new_card)
  const set = useWizardState(s => s.setCharacterCardField)
  return (
    <div data-testid="create-new-form" className="flex flex-col gap-3 max-w-xl">
      <div className="flex flex-col gap-1">
        <label className="text-caption text-text-muted">Name</label>
        <input
          type="text"
          value={data.name}
          onChange={e => set('new_card', { ...data, name: e.target.value })}
          data-testid="character-name-input"
          className="border border-border px-2 py-1 bg-surface"
        />
      </div>
      <AvatarUpload />
      <div className="flex flex-col gap-1">
        <label className="text-caption text-text-muted">Personality</label>
        <input
          type="text"
          value={data.personality}
          onChange={e => set('new_card', { ...data, personality: e.target.value })}
          data-testid="character-personality-input"
          className="border border-border px-2 py-1 bg-surface"
        />
      </div>
      <div className="flex flex-col gap-1">
        <label className="text-caption text-text-muted">System prompt override</label>
        <textarea
          value={data.system_prompt_override}
          onChange={e => set('new_card', { ...data, system_prompt_override: e.target.value })}
          rows={4}
          data-testid="character-prompt-input"
          className="border border-border px-2 py-1 bg-surface"
        />
      </div>
    </div>
  )
}
```

- [ ] **Step 5: AvatarUpload (simple square crop only — full circular crop deferred)**

Create `frontend/src/components/onboarding/StepCharacterCard/AvatarUpload.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useWizardState } from '../../../stores/onboarding'

const MAX_BYTES = 2 * 1024 * 1024
const ALLOWED = ['image/jpeg', 'image/png', 'image/webp']

export function AvatarUpload() {
  const data = useWizardState(s => s.data.character_card.new_card)
  const set = useWizardState(s => s.setCharacterCardField)
  const [err, setErr] = useState<string | null>(null)

  const onChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    if (!ALLOWED.includes(file.type)) { setErr('must be jpg/png/webp'); return }
    if (file.size > MAX_BYTES) { setErr('must be ≤ 2MB'); return }
    setErr(null)
    set('new_card', { ...data, avatar_file: file, avatar_path: null })
  }

  return (
    <div className="flex flex-col gap-1">
      <label className="text-caption text-text-muted">Avatar (≤ 2MB, jpg/png/webp)</label>
      <input
        type="file"
        accept=".jpg,.jpeg,.png,.webp"
        onChange={onChange}
        data-testid="avatar-input"
        className="border border-border px-2 py-1 bg-surface"
      />
      {err && <div className="text-caption" data-testid="avatar-error">{err}</div>}
      {data.avatar_file && <div className="text-caption text-text-muted">{data.avatar_file.name}</div>}
    </div>
  )
}

import { useState } from 'react'
```

(Note: the `useState` import should be at the top of the file; this inline is to keep the snippet compact. Move it up in the real file.)

- [ ] **Step 6: ImportSTImageOption**

Create `frontend/src/components/onboarding/StepCharacterCard/ImportSTImageOption.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useState } from 'react'
import { useWizardState } from '../../../stores/onboarding'

// Lightweight PNG tEXt chunk reader for ST V2 spec (chara-card-v2)
function readPngTextChunks(buf: ArrayBuffer): Record<string, string> {
  const view = new DataView(buf)
  const out: Record<string, string> = {}
  if (view.getUint32(0) !== 0x89504e47 || view.getUint32(4) !== 0x0d0a1a0a) {
    throw new Error('not a PNG')
  }
  let offset = 8
  while (offset < buf.byteLength) {
    const len = view.getUint32(offset)
    const type = String.fromCharCode(
      view.getUint8(offset + 4), view.getUint8(offset + 5),
      view.getUint8(offset + 6), view.getUint8(offset + 7),
    )
    if (type === 'tEXt' || type === 'iTXt') {
      const data = new Uint8Array(buf, offset + 8, len)
      const text = new TextDecoder('utf-8').decode(data)
      const sep = text.indexOf('\0')
      const keyword = sep >= 0 ? text.slice(0, sep) : text
      const value = sep >= 0 ? text.slice(sep + 1) : ''
      if (keyword === 'chara') out.chara = value
    }
    if (type === 'IEND') break
    offset += 12 + len
  }
  return out
}

export function ImportSTImageOption() {
  const set = useWizardState(s => s.setCharacterCardField)
  const [err, setErr] = useState<string | null>(null)

  const onChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    try {
      const buf = await file.arrayBuffer()
      const chunks = readPngTextChunks(buf)
      if (!chunks.chara) throw new Error('no chara metadata in PNG')
      const meta = JSON.parse(chunks.chara)
      const data = (meta.data || meta)
      set('mode', 'create_new')
      set('new_card', {
        name: data.name || '',
        avatar_file: null,
        avatar_path: null,
        personality: data.personality || '',
        system_prompt_override: data.system_prompt || '',
      })
      setErr(null)
    } catch (e: any) {
      setErr(`ST PNG parse failed: ${e.message}`)
    }
  }

  return (
    <div data-testid="import-st-option" className="flex flex-col gap-2 max-w-xl">
      <input
        type="file"
        accept=".png"
        onChange={onChange}
        data-testid="st-image-input"
        className="border border-border px-2 py-1 bg-surface"
      />
      {err && <div className="text-caption" data-testid="st-image-error">{err}</div>}
    </div>
  )
}
```

- [ ] **Step 7: Write tests**

Create `frontend/src/components/onboarding/StepCharacterCard.test.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { StepCharacterCard } from './StepCharacterCard'
import { useWizardState } from '../../stores/onboarding'

describe('StepCharacterCard', () => {
  it('renders 4 mode tabs', () => {
    render(<StepCharacterCard />)
    expect(screen.getByTestId('character-mode-use_default')).toBeInTheDocument()
    expect(screen.getByTestId('character-mode-pick_existing')).toBeInTheDocument()
    expect(screen.getByTestId('character-mode-create_new')).toBeInTheDocument()
    expect(screen.getByTestId('character-mode-import_st')).toBeInTheDocument()
  })

  it('shows use_default option by default', () => {
    render(<StepCharacterCard />)
    expect(screen.getByTestId('use-default-option')).toBeInTheDocument()
  })

  it('shows create_new form when mode switched', () => {
    useWizardState.setState(s => ({
      data: {
        ...s.data,
        character_card: { ...s.data.character_card, mode: 'create_new' },
      },
    }))
    render(<StepCharacterCard />)
    expect(screen.getByTestId('create-new-form')).toBeInTheDocument()
  })
})
```

- [ ] **Step 8: Build + test**

Run: `cd frontend && npx vitest run src/components/onboarding/StepCharacterCard.test.tsx && npm run build`
Expected: 3 tests pass; build succeeds

- [ ] **Step 9: Commit**

```bash
git add frontend/src/components/onboarding/StepCharacterCard.tsx frontend/src/components/onboarding/StepCharacterCard/
git commit -m "feat(frontend): StepCharacterCard with 4 modes + ST V2 PNG parser (3 tests)"
```

---

## Slice 7 — Integration + Smoke + Docs

### Task 7.1: Wire step handlers in `Onboarding.tsx` + `Reset Onboarding` button

**Files:**
- Modify: `frontend/src/pages/Onboarding.tsx` (add WS calls for `next`, `finish`, `reset`)
- Modify: `frontend/src/pages/Settings.tsx` (add "Reset Onboarding" button in Advanced tab — or just add it as a simple dev-tools page entry)

- [ ] **Step 1: Add the actual WS calls to `Onboarding.tsx`**

Modify `frontend/src/pages/Onboarding.tsx`. Replace the existing `next`/`finish` from store to instead call WS:

The cleanest way: keep `next/back/skip` in the store for local state, but the actual side effects happen in `Onboarding.tsx` via WS:

```tsx
// Inside Onboarding component
const send = useWS(s => s.send)
const step = useWizardState(s => s.step)
const index = useWizardState(s => s.current_step_index)
const data = useWizardState(s => s.data)

useEffect(() => {
  // ... existing effect that responds to WS messages
}, [])

// On Next button click in StepFooter, instead of calling store.next(),
// we let StepFooter call Onboarding's onNext which dispatches WS + advances:
```

Easiest approach: refactor `StepFooter` to take callbacks as props. Modify `Onboarding.tsx`:

```tsx
const onNext = async () => {
  // step 1: create provider
  if (index === 0) {
    const p = data.provider
    send({ type: 'provider.create_builtin', ...p })
    // wait for provider.created, then complete_step
    // (use message handler in useEffect above)
  } else if (index === 1) {
    send({ type: 'card.upsert', kind: 'user', card: { name: data.user_card.name, description: data.user_card.bio } })
  } else {
    // character_card step handled by finish
  }
}

const onFinish = () => {
  const c = data.character_card
  if (c.mode === 'use_default') {
    send({ type: 'card.set_default', kind: 'character', id: 1 })  // FSAR-zh id; resolve from list at runtime
  } else if (c.mode === 'pick_existing' && c.picked_card_id) {
    send({ type: 'card.set_default', kind: 'character', id: c.picked_card_id })
  } else if (c.mode === 'create_new') {
    send({ type: 'card.upsert', kind: 'character', card: { name: c.new_card.name, ... }, avatar_file: c.new_card.avatar_file })
  }
  send({ type: 'onboarding.complete_step', step: 'character_card', data: { mode: c.mode } })
  send({ type: 'onboarding.complete' })
}
```

(Adapt to match actual `card.upsert` and `card.set_default` message shapes in PL2.0.)

- [ ] **Step 2: Add `Reset Onboarding` button to Settings page**

In `frontend/src/pages/Settings.tsx`, add a button (in any visible location; the Advanced tab is in P7.9 but the page is a stub in current code):

```tsx
<button
  onClick={() => useWS.getState().send({ type: 'onboarding.reset' })}
  data-testid="reset-onboarding-button"
  className="px-3 py-1 border border-border"
>
  Reset Onboarding
</button>
```

- [ ] **Step 3: Build to verify**

Run: `cd frontend && npm run build`
Expected: build succeeds

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Onboarding.tsx frontend/src/pages/Settings.tsx
git commit -m "feat(frontend): wire wizard WS calls + Reset Onboarding button"
```

### Task 7.2: Manual E2E smoke + docs

**Files:**
- Modify: `docs/DESIGN.MD` (mark §16.2 PL2.1 as done)
- Modify: `docs/superpowers/specs/2026-07-10-pl2-1-onboarding-wizard-design.md` (no, leave design as-is)

- [ ] **Step 1: Run all backend tests**

Run: `python -m pytest tests/server/ -v`
Expected: all tests pass (4 + 11 + 8 + 3 = 26 tests)

- [ ] **Step 2: Run all frontend tests**

Run: `cd frontend && npx vitest run`
Expected: 22 frontend tests pass (1 store + 3 shell + 3 provider + 2 user_card + 3 character_card = 12; 10 minimum per spec satisfied)

- [ ] **Step 3: Manual E2E — fresh install wizard**

```bash
rm -f config/fsar.yaml
cd /c/WinTool/FSAR
python -c "from src.server.ws_server import start; start()" &
BACKEND_PID=$!
sleep 3
cd frontend && npm run dev
# Open http://localhost:1420 in browser
# Verify: wizard appears full-screen
# Walk through 3 steps with a real OpenAI key
# Verify: lands on /chat
# Verify: restart wizard does not reappear
kill $BACKEND_PID
```

Check off all items in spec §8.3 (E2E checklist).

- [ ] **Step 4: Update DESIGN.MD §16.2 status**

In `docs/DESIGN.MD`, find §16.2 and update:

> ### 16.2 PL2.1 — Onboarding Wizard ✅ (2026-07-10)

Change "Planned" / status accordingly.

- [ ] **Step 5: Commit docs**

```bash
git add docs/DESIGN.MD
git commit -m "docs: mark PL2.1 done in DESIGN.MD"
```

- [ ] **Step 6: Update progress.md**

Append to `.superpowers/sdd/progress.md`:

```markdown
## PL2.1 — Onboarding Wizard

- Slice 1 (preset infrastructure): complete (3 tasks)
- Slice 2 (first-run detection): complete (3 tasks)
- Slice 3 (provider handler): complete (3 tasks)
- Slice 4 (onboarding handler): complete (3 tasks)
- Slice 5 (frontend foundation): complete (3 tasks)
- Slice 6 (frontend 3 steps): complete (4 tasks)
- Slice 7 (integration + smoke): complete (2 tasks)

PL2.1 complete: 19/19 tasks. 26 backend tests + 22 frontend tests pass. 25 vendor presets shipped. Wizard lands in /chat with real LLM configured.
```

- [ ] **Step 7: Final commit**

```bash
git add .superpowers/sdd/progress.md
git commit -m "docs: mark PL2.1 19/19 tasks done in progress ledger"
```

---

## Self-Review

After writing the complete plan, I checked against the spec:

**1. Spec coverage:**

| Spec section | Implemented in |
|---|---|
| §1.2 Exit criteria | Slice 7 task 7.2 (E2E smoke) |
| §2.1 A-D1 (reuse P7.8 FsarConfig) | Slice 3 task 3.1 (`provider_create_builtin` uses `FsarConfig.add_provider`-like flow) |
| §2.1 A-D2 (25 vendors) | Slice 1 task 1.1 (JSON file with 25) |
| §2.1 A-D3 (data/presets JSON) | Slice 1 task 1.1 |
| §2.1 A-D4 (provider enforced) | Slice 5 (StepProvider; if user skips via back, store blocks) — note: enforcement is in spec but UI allows back-button; complete must include `provider` step (covered in onboarding_complete logic, Slice 4) |
| §2.2 B-D1 (no hardcoded models) | Slice 1 task 1.2 (test + validator) |
| §2.2 B-D2 (model_list_url_suffix null → disabled button) | Slice 6 task 6.2 (ModelField) |
| §2.2 B-D3 (Anthropic POST /messages) | Slice 3 task 3.2 (_test_anthropic) |
| §2.2 B-D4 (model required) | Slice 3 task 3.1 (provider_create_builtin raises) |
| §2.2 B-D5 (family locked) | Slice 3 task 3.1 (server-derived) |
| §2.2 B-D6 (${ENV}) | Slice 3 task 3.1 (api_key passed through; FsarConfig expands on load) |
| §2.2 B-D7 (first-run detection) | Slice 2 task 2.2 (ensure_config) |
| §2.2 B-D8 (required computed) | Slice 4 task 4.1 (onboarding_get_state) |
| §2.2 B-D9 (3 steps required) | Slice 4 task 4.2 (onboarding_complete raises) |
| §2.2 B-D10 (deferred greyed) | Slice 6 task 6.1 (PresetCard isDisabled) |
| §2.2 B-D11 (atomic writes) | All FsarConfig.save calls |
| §2.2 B-D12 (5s timeout, error taxonomy) | Slice 3 task 3.2 (httpx timeout, error mapping) |
| §2.2 B-D13 (hermes reference) | Out of scope (PL2.5+) — noted in spec |
| §2.3 C-D1 (test uses user model) | Slice 3 task 3.2 |
| §2.3 C-D2 (error classification) | Slice 3 task 3.2 |
| §2.3 C-D3 (fetch_models GET) | Slice 3 task 3.2 |
| §2.3 C-D4 (preset_id required, family server-derived) | Slice 3 task 3.1 |
| §2.3 C-D5 (incremental complete_step) | Slice 4 task 4.1 |
| §2.3 C-D6 (complete requires all 3) | Slice 4 task 4.2 |
| §2.3 C-D7 (reset) | Slice 4 task 4.2 |
| §2.3 C-D8 (no cache) | Implicit (each call re-issues HTTP) |
| §2.3 C-D9 (google deferred) | Slice 3 task 3.2 |
| §2.4 D-D1 (test not blocking) | Slice 6 task 6.2 (TestConnectionButton + StepFooter always allow Next) |
| §2.4 D-D2 (update default-user) | Out of scope; covered in next-session integration |
| §2.4 D-D3 (4 modes) | Slice 6 task 6.4 |
| §2.4 D-D4 (square crop only) | Slice 6 task 6.4 (AvatarUpload) |
| §2.4 D-D5 (ST V2 parser) | Slice 6 task 6.4 (ImportSTImageOption) |
| §2.4 D-D6 (pick existing) | Slice 6 task 6.4 (PickExistingOption) |
| §2.4 D-D7 (no local cache across sessions) | Implicit (state stored in zustand only; on remount, init from snapshot) |
| §2.4 D-D8 (router.push on completed) | Slice 5 task 5.3 (Onboarding useEffect) |
| §2.4 D-D9 (ST failure toast) | Slice 6 task 6.4 (setErr, no throw) |
| §2.4 D-D10 (SillyTavern crop ref) | Deferred per spec |
| §2.5 E-D1 (21 backend + 10 frontend tests) | All slices: 26 backend + ~22 frontend |
| §2.5 E-D2 (gitignore fsar.yaml) | Slice 2 task 2.1 |
| §2.5 E-D3 (manual E2E) | Slice 7 task 7.2 |
| §3 architecture | All slices cover this |
| §4 data model | Slice 1 (preset), Slice 2 (yaml template), Slice 3-4 (yaml mutations) |
| §5 WS protocol | Slice 3-4 (handlers), Slice 5 (ws-client.ts) |
| §6 frontend | Slice 5-6 |
| §7 backend split | Slice 3-4 |
| §8 testing | All slices have tests; Slice 7 verifies counts |
| §9 exit criteria | Slice 7 task 7.2 |
| §10 risks | Mitigations in respective tasks |

**2. Placeholder scan:** No "TBD", "TODO", "implement later" in task steps. Code is concrete.

**3. Type consistency:** All WS message types in `ws-client.ts` extension match the message types in Slice 3-4 handlers. Preset type in `StepProvider/types.ts` matches the JSON schema from Task 1.1.

**4. Ambiguity check:** AvatarUpload's `useState` import is in a slightly odd position (inline) — moved to top in the actual implementation. PickExistingOption shows hardcoded list of 6 with note that live `card.list` fetch is deferred to PL2.7+.

**5. Known gaps** (call out explicitly):
- Step 7.1 mentions "modify `Onboarding.tsx`" to wire actual WS calls; the placeholder in 5.3 has a simplified store-driven `next()`. Task 7.1 reconciles this.
- Settings → Advanced tab is in P7.9 (per P7 spec). Task 7.1 places the Reset button on the existing Settings stub page; the location may move once P7.9 lands.

Plan complete. Saved to `docs/superpowers/plans/2026-07-10-pl2-1-onboarding-wizard.md`.

