# FSAR 公共文档

> 语言：中文 | [English](README.en.md)

这里是 FSAR 面向用户的正式文档。仓库根目录的 README 提供快速上手，本目录提供完整、深入的说明。

> 仓库里另有一个 `docs/` 目录，那是**内部开发计划/设计文档**，不随产品发布；面向读者的内容都在这里的 `docs-public/`。

## 目录

| 文档 | 内容 |
|---|---|
| [项目总览](overview.md) | FSAR 是什么、四大支柱、能力清单、技术栈、架构鸟瞰、一条消息的端到端流程、数据布局 |
| [模块介绍](modules/README.md) | 后端 `src/` 各模块（server / core / memory / tools / security / sandbox / skills / social / providers / mcp / utils / scheduler）、前端 `frontend/`、以及 `data/` 与 `config/` 的职责与关键文件 |
| [配置详解](configuration.md) | `fsar.yaml` 每一段的含义、默认值与取值范围（含完整的安全子项） |
| [编译 · 测试 · 开发教程](development.md) | 环境准备、安装、启动、前端开发、测试与 CI、代码规范、数据目录、提交协作 |

## 仓库里的其它文档

| 文档 | 内容 |
|---|---|
| [`README.md`](../README.md) | 快速上手（另有[简体中文](../README.zh-Hans.md) / [繁體中文](../README.zh-Hant.md) / [日本語](../README.ja.md) / [Deutsch](../README.de.md) / [Français](../README.fr.md)） |
| [`CONTRIBUTING.md`](../CONTRIBUTING.md) | 如何参与贡献（英文） |
| [`SECURITY.md`](../SECURITY.md) | 安全机制全景与漏洞私密报告流程（英文） |
| [`CHANGELOG.md`](../CHANGELOG.md) | 变更日志 |
| [`THIRD_PARTY_LICENSES/`](../THIRD_PARTY_LICENSES/) | 第三方依赖许可 |

## 许可

FSAR 以 [MIT License](../LICENSE) 发布。
