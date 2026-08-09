# FSAR

<p align="center">
  <img src="assets/icons/logo-wordmark.svg" alt="FSAR" width="380">
</p>

<p align="center">
  <strong>忠实 · 安全 · 适应 · 反思</strong><br>
  一个本地优先的 AI 伴侣——和你一起成长,而不是以你为代价。
</p>

<p align="center">
  <a href="README.md">English</a> ·
  <strong>简体中文</strong> ·
  <a href="README.ja.md">日本語</a> ·
  <a href="README.de.md">Deutsch</a> ·
  <a href="README.zh-Hant.md">繁體中文</a> ·
  <a href="README.fr.md">Français</a>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License"></a>
  <img src="https://img.shields.io/badge/python-3.11+-3776AB.svg" alt="Python">
  <img src="https://img.shields.io/badge/Platform-linux%20%7C%20macOS%20%7C%20windows-lightgrey.svg" alt="Platform">
  <img src="https://img.shields.io/badge/LANG-Simplified%20Chinese-red.svg" alt="Simplified Chinese">
  <img src="https://img.shields.io/badge/LANG-Japanese-ff69b4.svg" alt="Japanese">
  <img src="https://img.shields.io/badge/LANG-English-lightgrey.svg" alt="English">
  <img src="https://img.shields.io/badge/LANG-German-ffd700.svg" alt="German">
  <img src="https://img.shields.io/badge/LANG-Traditional%20Chinese-orange.svg" alt="Traditional Chinese">
  <img src="https://img.shields.io/badge/LANG-French-0055A4.svg" alt="French">
</p>

## 什么是 FSAR?

FSAR 是一个**属于你**的本地优先 AI 伴侣——不挂在任何服务商名下。对话、记忆、决策记录全都存在你自己机器上的 `~/.fsar/` SQLite 数据库里。不联网、不上传、不共享。

名字本身就是设计契约:**F**aithful · **S**afe · **A**daptive · **R**eflective。

### 四个支柱

- **Faithful · 忠实** —— 你写过一张角色卡(名字、性格、场景、情绪状态),FSAR 就是你定义的那个角色,在跟你写的那张用户卡上描述的对象对话。它不会跑题成"万能助手"。
- **Safe · 安全** —— 工具调用要过五道关:硬编码的 hardline 守卫在沙箱检查之前先拦掉破坏性 shell 命令(`rm -rf /`、`shutdown`、`mkfs`);风险引擎把每个工具划成 SAFE / LOW / MEDIUM / HIGH / CRITICAL;workspace gate 圈定文件访问范围;subprocess 环境清理器跑 skill 前先剥掉 API key 和 token;egress 开关管对外网访问。
- **Adaptive · 适应** —— 每次工具调用都进决策日志。strategy injector 看数据合成 `## Learned Strategies` 块喂给下次会话——"文件存在时优先用 `edit` 而不是 `file_ops write`"这种经验,要等模型自己试错过才进系统提示。experience store 还会把程序性知识(比如某次装的 MCP server)沉淀下来,下次会话直接 recall。
- **Reflective · 反思** —— 三种模式(per-task / on-failure / idle-batch)定时回看对话,更新用户模型:明确偏好("用 VSCode")、推断画像("经常晚上写代码")、重复模式("常用 file_ops 整理下载")。下次会话打开时,这些上下文已经在系统提示里了。

### 能做什么

- 跑 shell 命令(Windows 用 PowerShell,其他平台用 bash),带 hardline 守卫
- 在限定 workspace 里读、写、搜文件
- 用沙箱化的 alias 表打开应用和 URL
- 通过免费的 [Exa MCP](https://mcp.exa.ai) 服务器搜网页、抓网页——无需 API key
- 本地分析图片和 PDF
- 操作桌面(Computer Use / cua):截图、点击、输入、按键——单独的风险等级
- 把新 skill 落库成 SQLite experience 行(P6)
- 通过 Telegram / 飞书 / 微信 社交桥接对话

## 快速开始

需要 **Python 3.11+** 和 **Node.js 18+**。用系统的包管理器装(`brew install python@3.11 node`、`apt install python3.11 python3.11-venv nodejs`,或 Windows 从 python.org / nodejs.org 下 installer)。

### 克隆并安装

```bash
git clone https://github.com/sildo466/FSAR.git
cd FSAR
python3 -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

> venv 的目的:让 FSAR 的依赖(尤其是 chromadb、cua 这一坨)跟系统 Python 隔开。Linux 上 2024 年起的发行版默认拒绝系统级 `pip install`(PEP 668),不建 venv 直接 pip 会报错。macOS Homebrew Python 不强制,但同样推荐。

### 启动

| 平台 | 命令 |
|---|---|
| Windows | `start.bat` |
| Linux / macOS | `./start.sh` |

第一次启动会装前端依赖(`npm install`)并构建 UI(`npm run build`);之后再启动就只重建,几秒就好。

### 终端 CLI

```bash
python main.py
```

直接在终端里跑 FSAR——记忆、内置工具、安全闸门都一样,只是没有浏览器界面。终端循环比 WebUI 简单:固定工具轮数,没有能力档位、子代理、对抗式校验、微反思和上下文压缩。交互会话里可用斜杠命令(输入 `/help` 查看;`/memory clear` 清空全部记忆)。用 `pip install -e .` 安装后还有 `fsar` 命令。

语音(TTS/ASR)和社交平台桥接(Telegram/飞书/微信)只随 WebUI 后端运行;终端会话覆盖聊天、工具、记忆与定时任务。

### 打开

浏览器自动开 <http://127.0.0.1:8765>。没弹就手动访问。

### 仅 macOS:开辅助功能权限

**系统设置 → 隐私与安全性 → 辅助功能**,给你的终端和 Python 开权限。只有用 cua 那几个工具(`cu_screenshot`、`cu_click`、`cu_type`、`cu_keypress`)时才需要。

### 停止

| 平台 | 命令 |
|---|---|
| Windows | `taskkill /FI "WINDOWTITLE eq FSAR Backend*" /T /F` |
| Linux / macOS | `pkill -f "src.server.ws_server"` |

### 更新

```bash
git pull
pip install -r requirements.txt --upgrade
```

然后重启。

## 它跟通用 AI 聊天工具有什么不同

### 本地优先

对话、记忆、决策日志全在 `~/.fsar/` 里——你自己机器上的 SQLite。不会上传到任何 FSAR 服务器。LLM provider 只看到你实际发的消息,跟用任何普通聊天客户端一样。删 `~/.fsar/` 等于让 FSAR 失忆。

### 你自己写的角色

每个会话跑的是你写的角色卡:名字、性格、场景、可选的情绪状态。再配上一张用户卡描述你自己,LLM 拿到的是一个边界清晰的 persona,不会跑题的"helpful AI assistant"。换卡就换角色,代码不用动。

### 跨会话记住你

几次对话之后,FSAR 会攒出一个稳定的画像:明确偏好("用 VSCode")、推断行为("经常晚上写代码")、重复模式("常用 file_ops 整理下载")。下次会话一开,这些上下文已经在系统提示里——你不用每次重新介绍自己。

### 用得越久越懂你

每次工具调用都进决策日志。strategy injector 看数据合成 `## Learned Strategies` 块喂给未来的 prompt。"文件存在时优先用 `edit` 而不是 `file_ops write`" 这种经验,要等模型自己踩过坑才进 prompt。用得越久,FSAR 越懂怎么当*你的*助手。

### LLM 上五道防线

就算模型幻觉出 `rm -rf /` 或 `shutdown -h now`,硬编码的守卫在任何沙箱检查之前就把工具管线切断。再往上:风险分级、workspace gate、subprocess 环境清理器、egress 开关。从 LLM 输出到你的磁盘,隔着五层。

### 自选模型

OpenAI、Anthropic、Google、DeepSeek,或者任何兼容 OpenAI 的自定义端点。本地模型通过 Ollama 或 LM Studio 也行。你直接付 provider——FSAR 不抽成,不做中间层。中途换 provider,FSAR 不丢状态直接换客户端。

### Skill 装一次永远在

装一个 MCP server(GitHub、Postgres、Slack 还有几百个)或 Python skill 一次。FSAR 把流程写成 experience store 里的一行,带 `active → stale → archived` 状态机自动晋升。下次会话 `experience_view` 直接调出来,不用重装。

### 多渠道

同一个引擎也能从 Telegram、飞书、微信接进来。每个平台可以独立覆盖角色卡和用户卡——Telegram 里的 FSAR 和 GUI 里的可以是两个人,不用装两份。

### Computer Use 单独一道门

computer-use 套件(`cua`)让模型在桌面上截图、点击、输入、按键。风险门和普通工具分开,macOS 上还得先开辅助功能权限。

### 体积小

FSAR 很轻——一个 Python 服务加一个精简的 Tauri 前端。源码仅约 6~7 MB,安装前端依赖后约 200 MB(不含 Python 依赖)。没有重型运行时、不依赖云端,普通配置的机器也能跑得很顺。

## 教程

> 📖 本教程只是快速入门。完整文档（项目总览、模块介绍、配置文件详解、编译/测试/开发教程）请前往 [`docs-public/`](docs-public/)。

### 项目结构

```
src/
  server/         FastAPI WebSocket 传输层
  core/           Agent 循环、prompts、injectors
  memory/         短期/长期/语义/用户模型/experience
  tools/builtin/  ~25 个内置工具
  security/       风险引擎、permissions、审计
  sandbox/        hardline 守卫、workspace gate
  skills/         Python skill 运行时
  social/         Telegram / 飞书 / 微信 适配器
  providers/      LLM / TTS / ASR 适配器
  utils/          日志、配置、migrations
frontend/         Tauri 2 / React UI
data/             SQLite + ChromaDB + 日志 + 缓存
config/           自带的 yaml 默认值
```

### 配置

`fsar.yaml` 是运行时配置的唯一来源。

- `config/fsar.yaml.template` —— 自带默认值,只读参考
- `~/.fsar/config/fsar.yaml` —— 你的副本,UI 改或手编都行

第一次运行如果副本不存在就复制模板。section:`llm` / `tts` / `asr` / `memory` / `security` / `social` / `mcp` / `reflection` / `permissions` / `user` / `style`。完整 schema 看 [`config/fsar.yaml.template`](config/fsar.yaml.template)。

### 数据布局

FSAR 关于你的一切都在 `~/.fsar/` 下:

```
~/.fsar/config/        yaml 文件
~/.fsar/data/
  memory.db           对话、决策、用户模型、experience
  chroma/             语义嵌入
  llm_cache.db        L1/L2 响应缓存
  tts_cache.db        TTS 音频缓存
  logs/               滚动日志
```

删 `~/.fsar/` 整个目录,FSAR 回到干净状态。

### 构建与测试

Python 后端和 Tauri 前端是两份产物,没有单一的"build"步骤。

```bash
# 后端
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 前端(只在改 TS/React 时才需要)
cd frontend && npm install && npm run build

# 测试
pytest tests/ -q
```

跨平台测试在 `tests/test_*_cross_platform.py`。

## License

[MIT](LICENSE)