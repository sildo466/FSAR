# Third-Party Licenses

FSAR is built on open-source software. This directory contains the license
texts of the **Python runtime dependencies** declared in
[`requirements.txt`](../requirements.txt) / [`pyproject.toml`](../pyproject.toml).

Each `<package>.txt` file reproduces the license shipped with the installed
package (copied verbatim from its `*.dist-info` LICENSE file), so the text here
matches exactly what was distributed. Versions are the ones pinned at the time
of writing; your install may differ — run `pip show <package>` to check.

| Package | Version | License | File |
|---|---|---|---|
| [anthropic](https://pypi.org/project/anthropic/) | 0.71.0 | MIT | [anthropic.txt](anthropic.txt) |
| [chromadb](https://pypi.org/project/chromadb/) | 1.5.9 | Apache-2.0 | [chromadb.txt](chromadb.txt) |
| [cryptography](https://pypi.org/project/cryptography/) | 46.0.3 | Apache-2.0 **OR** BSD-3-Clause | [cryptography.txt](cryptography.txt) |
| [cua](https://pypi.org/project/cua/) | 0.1.6 | MIT | [cua.txt](cua.txt) |
| [edge-tts](https://pypi.org/project/edge-tts/) | 7.2.8 | LGPL-3.0 (one file MIT) | [edge-tts.txt](edge-tts.txt) |
| [faster-whisper](https://pypi.org/project/faster-whisper/) | 1.2.1 | MIT | [faster-whisper.txt](faster-whisper.txt) |
| [fastapi](https://pypi.org/project/fastapi/) | 0.120.0 | MIT | [fastapi.txt](fastapi.txt) |
| [google-genai](https://pypi.org/project/google-genai/) | 1.49.0 | Apache-2.0 | [google-genai.txt](google-genai.txt) |
| [httpx](https://pypi.org/project/httpx/) | 0.28.1 | BSD-3-Clause | [httpx.txt](httpx.txt) |
| [lark-oapi](https://pypi.org/project/lark-oapi/) | 1.7.1 | MIT | [lark-oapi.txt](lark-oapi.txt) |
| [loguru](https://pypi.org/project/loguru/) | 0.7.3 | MIT | [loguru.txt](loguru.txt) |
| [mcp](https://pypi.org/project/mcp/) | 1.27.2 | MIT | [mcp.txt](mcp.txt) |
| [openai](https://pypi.org/project/openai/) | 2.45.0 | Apache-2.0 | [openai.txt](openai.txt) |
| [Pillow](https://pypi.org/project/Pillow/) | 12.0.0 | HPND (MIT-CMU) | [Pillow.txt](Pillow.txt) |
| [PyPDF2](https://pypi.org/project/PyPDF2/) | 3.0.1 | BSD-3-Clause | [PyPDF2.txt](PyPDF2.txt) |
| [python-dotenv](https://pypi.org/project/python-dotenv/) | 1.1.1 | BSD-3-Clause | [python-dotenv.txt](python-dotenv.txt) |
| [python-telegram-bot](https://pypi.org/project/python-telegram-bot/) | 22.8 | LGPL-3.0-only | [python-telegram-bot.txt](python-telegram-bot.txt) |
| [PyYAML](https://pypi.org/project/PyYAML/) | 6.0.3 | MIT | [PyYAML.txt](PyYAML.txt) |
| [rich](https://pypi.org/project/rich/) | 14.2.0 | MIT | [rich.txt](rich.txt) |
| [uvicorn](https://pypi.org/project/uvicorn/) | 0.38.0 | BSD-3-Clause | [uvicorn.txt](uvicorn.txt) |
| [websockets](https://pypi.org/project/websockets/) | 15.0.1 | BSD-3-Clause | [websockets.txt](websockets.txt) |

## Code derived from upstream MIT projects

Two FSAR subsystems draw on MIT-licensed upstream projects (not runtime
dependencies — their texts are reproduced here in full to satisfy the MIT
"retain the copyright notice" condition):

| Upstream | How FSAR uses it | License | File |
|---|---|---|---|
| [OpenClaw](https://github.com/openclaw/openclaw) | LLM prompt-cache architecture ported into `src/utils/` (expiring map cache, cache-ttl log, prompt-cache markers) | MIT | [openclaw.txt](openclaw.txt) |
| [Hermes Agent](https://github.com/NousResearch/hermes-agent) | SKILL.md shape referenced for the experience-layer importer | MIT | [hermes.txt](hermes.txt) |

## Notes

- **`cryptography`** is dual-licensed; you may use it under either the Apache
  License 2.0 or the BSD 3-Clause License. Both full texts are included.
- **`Pillow`** uses the Historical Permission Notice and Disclaimer (HPND,
  a.k.a. MIT-CMU). Its license file also lists the licenses of the bundled
  imaging libraries it ships.
- **`edge-tts`** is LGPL-3.0, except `src/edge_tts/srt_composer.py` which is MIT
  (noted at the top of its license file).
- **`loguru`** does not ship a LICENSE file in its wheel; the MIT text here is
  reproduced from the upstream project.

## Frontend dependencies

The web UI (`frontend/`) has its own JavaScript dependency tree, pinned in
[`frontend/package-lock.json`](../frontend/package-lock.json). Each npm package
carries its own license in its `node_modules/<package>/LICENSE` file after
`npm install`; generate a consolidated report with `npx license-checker --summary`.

## FSAR itself

FSAR is released under the [MIT License](../LICENSE).
