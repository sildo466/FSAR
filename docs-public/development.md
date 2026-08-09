# 编译 · 测试 · 开发教程

> 语言：中文 | [English](development.en.md)

面向想要本地运行、修改或贡献 FSAR 的开发者。

## 1. 环境准备

| 依赖 | 版本 | 说明 |
|---|---|---|
| Python | 3.12+ | 项目声明最低 3.11，但 Computer Use 依赖 `cua` 要求 `>=3.12,<3.14`，所以实际请用 **3.12 或 3.13** |
| Node.js | 18+ | 构建前端 UI |

按平台用包管理器安装即可：

```bash
# macOS (Homebrew)
brew install python@3.12 node
# Debian / Ubuntu
sudo apt install python3.12 python3.12-venv nodejs
# Windows: 从 python.org / nodejs.org 下载安装器
```

## 2. 获取代码并安装依赖

```bash
git clone https://github.com/sildo466/FSAR.git
cd FSAR
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

> 后端（Python）与前端（Tauri/React）是两个独立产物，**没有单一的 "build" 步骤**。

## 3. 启动

| 平台 | 命令 |
|---|---|
| Windows | `start.bat` |
| Linux / macOS | `./start.sh`（或 `make dev`） |

启动脚本会：

1. 首次运行自动 `npm install` 并 `npm run build` 构建前端（之后跳过安装、秒级重建）；
2. 启动后端（`src.server.ws_server`），监听 `http://127.0.0.1:8765`；
3. 打开浏览器；若未自动打开，手动访问上面的地址。

`make` 常用目标（见 `Makefile`）：

| 目标 | 作用 |
|---|---|
| `make dev` | 运行 `start.sh`（完整启动器） |
| `make build` | 仅构建前端 |
| `make stop` | 停止运行中的后端 |
| `make test` | 运行 `pytest tests/ -x -q` |
| `make clean` | 清理构建产物与缓存 |

### 终端 CLI（无浏览器）

```bash
python main.py    # 或 fsar 控制台脚本（需 `pip install -e .`）
```

在终端运行 FSAR：同一个 `~/.fsar/` 数据、内置工具与安全闸门；循环本身比 WebUI 简单（固定工具轮数，无能力档位、子代理、对抗式校验、微反思与上下文压缩）。交互会话支持全部斜杠命令（输入 `/help` 查看；如 `/memory clear` 清空全部长期记忆，带二次确认）。

### 停止

| 平台 | 命令 |
|---|---|
| Windows | `taskkill /FI "WINDOWTITLE eq FSAR Backend*" /T /F` |
| Linux / macOS | `pkill -f "src.server.ws_server"` |

### macOS 额外步骤（仅 Computer Use 需要）

打开 **系统设置 → 隐私与安全性 → 辅助功能**，授权你的终端与 Python。仅在使用桌面操作工具（`cu_screenshot`/`cu_click`/`cu_type`/`cu_keypress`）时需要。

## 4. 前端开发

前端是 **Tauri 2 + React + TypeScript**，位于 `frontend/`。

```bash
cd frontend
npm install
npm run build        # 产物供后端静态托管
```

- `frontend/src/` — React 界面：`components/chat`（聊天）、`components/onboarding`（首次使用向导）、`clients/`（WebSocket 与 HTTP 客户端）。
- `frontend/src-tauri/` — Tauri 桌面壳（Rust）；纯 Web 使用可不构建它。
- 组件测试用 Vitest/Testing Library（`*.test.tsx`）。

只有修改 TS/React 代码时才需要重新构建前端。

## 5. 测试

测试套件设计为**离线运行**：不联网、不连真实 MCP 服务器、不调真实 LLM。`tests/server/conftest.py` 通过桩替换引擎副作用，强制服务端测试离线。

```bash
# 完整套件（含 live-MCP / e2e 用例）
pytest tests/ -q

# CI 使用的离线单元门（也是改动安全代码后最该跑的子集）
pytest tests/sandbox tests/security tests/skills tests/utils tests/server -q

# 单个文件 / 单个用例
pytest tests/sandbox/test_hardline.py -q
pytest tests/sandbox/test_paths.py::test_normalize_nfkc -q
```

测试目录组织：

```
tests/
  sandbox/    hardline、路径归一化、敏感路径、工作区门禁
  security/   WebSocket 鉴权
  skills/     技能运行时、出口控制、密钥、审阅门禁
  utils/      LLM 工厂出口
  server/     HTTP/WS 端点（离线桩）
```

约定：

- 新功能 / 修复 bug 要附带测试。
- 任何改动 `src/sandbox/` 或 `src/security/` 的 PR，必须在 `tests/sandbox/` 或 `tests/security/` 同时覆盖"放行"与"拦截"两条路径。
- 新测试保持离线；确需真实服务的用例要加守卫，确保离线门常绿。

## 6. 持续集成

`.github/workflows/ci.yml` 在 push / PR 时：

1. ubuntu-latest + Python **3.12**（`cua` 要求 `>=3.12,<3.14`）；
2. `pip install -r requirements.txt`；
3. 运行离线单元门 `pytest tests/sandbox tests/security tests/skills tests/utils tests/server -q`。

> 依赖范围里有上限约束（如 `mcp>=1.0,<2`、`google-genai>=0.3,<2`），避免 CI 拉到与代码不兼容的新大版本。升级依赖时请同步更新这些上限并跑一遍测试。

## 7. 代码规范

- **Python 3.12+**，跟随上下文的类型标注。
- **注释与标识符用英文**；注释要少，只解释非显而易见的意图。
- **不要写 "fix bug"、"xxx 修改" 之类的注释**——历史属于 git 与 CHANGELOG。
- 没有强制格式化工具；与相邻代码保持一致即是规则。
- 改动要外科手术式：只动该动的，不在同一提交里重构/重排无关代码。
- 运行时配置走 `fsar.yaml`（见[配置详解](configuration.md)），不要硬编码用户路径或密钥。

## 8. 数据与运行目录

一切关于用户的记忆都在 `~/.fsar/`：

```
~/.fsar/config/        yaml 配置
~/.fsar/data/
  memory.db            对话、决策、用户画像、经验
  chroma/              语义嵌入
  llm_cache.db         L1/L2 响应缓存
  tts_cache.db         TTS 音频缓存
  logs/                滚动日志 + audit.log（审计）
```

删除 `~/.fsar/` 即彻底重置。

## 9. 提交与协作

- 使用 Conventional Commits：`feat(social): ...`、`fix(security): ...`、`docs: ...`。
- 主题大的改动先开 issue 讨论方向；小修复可直接 PR。
- PR 保持单一关注点，说明"改了什么 / 为什么"，并关联 issue。
- 报告安全漏洞**不要**用公开 issue/PR，请走 [`SECURITY.md`](../SECURITY.md) 的私密流程。

## 延伸阅读

- [项目总览](overview.md) · [模块介绍](modules/README.md) · [配置详解](configuration.md)
- [`CONTRIBUTING.md`](../CONTRIBUTING.md) · [`SECURITY.md`](../SECURITY.md)
