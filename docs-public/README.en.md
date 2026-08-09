# FSAR Documentation

> Language: [中文](README.md) | English

This is FSAR's official user documentation. The repository-root README gives a quick start; this directory provides the full, in-depth reference.

> The repository also has a `docs/` directory, but that holds **internal development plans / design docs** and is not shipped. Reader-facing content lives here in `docs-public/`.

## Contents

| Document | What it covers |
|---|---|
| [Project overview](overview.en.md) | What FSAR is, the four pillars, capabilities, tech stack, architecture at a glance, an end-to-end message flow, and the data layout |
| [Module reference](modules/README.en.md) | The responsibility and key files of every backend module under `src/` (server / core / memory / tools / security / sandbox / skills / social / providers / mcp / utils / scheduler), plus the frontend and `data/` & `config/` |
| [Configuration guide](configuration.en.md) | Every section of `fsar.yaml` — meaning, defaults, and accepted values (including all security sub-options) |
| [Build · Test · Develop](development.en.md) | Environment setup, install, launch, frontend development, testing & CI, code conventions, data directories, and the contribution workflow |

## Other documentation in the repository

| Document | What it covers |
|---|---|
| [`README.md`](../README.md) | Quick start (also in [简体中文](../README.zh-Hans.md) / [繁體中文](../README.zh-Hant.md) / [日本語](../README.ja.md) / [Deutsch](../README.de.md) / [Français](../README.fr.md)) |
| [`CONTRIBUTING.md`](../CONTRIBUTING.md) | How to contribute |
| [`SECURITY.md`](../SECURITY.md) | The security model and the private vulnerability-reporting process |
| [`CHANGELOG.md`](../CHANGELOG.md) | Changelog |
| [`THIRD_PARTY_LICENSES/`](../THIRD_PARTY_LICENSES/) | Third-party dependency licenses |

## License

FSAR is released under the [MIT License](../LICENSE).
