# FSAR

<p align="center">
  <img src="assets/icons/logo-wordmark.svg" alt="FSAR" width="380">
</p>

<p align="center">
  <strong>忠實 · 安全 · 適應 · 反思</strong><br>
  一個本地優先的 AI 夥伴——與你一同成長,而非以你為代價。
</p>

<p align="center">
  <a href="README.md">English</a> ·
  <a href="README.zh-Hans.md">简体中文</a> ·
  <a href="README.ja.md">日本語</a> ·
  <a href="README.de.md">Deutsch</a> ·
  <strong>繁體中文</strong> ·
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

## 什麼是 FSAR?

FSAR 是一個**屬於使用者**的本地優先 AI 夥伴——不屬於任何供應商。你的對話、記憶與決策紀錄全部儲存在你自己機器上 `~/.fsar/` 目錄的 SQLite 資料庫裡。沒有任何東西被上傳。

名字本身就是設計契約:**F**aithful · **S**afe · **A**daptive · **R**eflective。

### 四大支柱

- **忠實** — FSAR 就是你定義的那個角色(角色卡:名稱、性格、情境、情緒狀態),和你描述的那位使用者(使用者卡)在對話。它不會離題變成「通用助手」。
- **安全** — 每個工具呼叫都經過多層檢查:硬編碼的 hardline 守衛在沙箱檢查之前先攔截破壞性 shell 指令(`rm -rf /`、`shutdown`、`mkfs`);風險引擎將每個工具分類為 SAFE/LOW/MEDIUM/HIGH/CRITICAL;workspace gate 限制檔案存取範圍;subprocess 環境清理器在執行 skill 之前先去除 API 金鑰與權杖。
- **適應** — 每次工具呼叫都會被記錄。strategy injector 從決策日誌與使用者模型合成一個 `## Learned Strategies` 區塊,餵給後續的 prompt——「檔案存在時優先使用 `edit` 而非 `file_ops write`」這種經驗,要等模型親身試錯過才進入系統提示。experience store 持久化程序性知識,本次工作階段安裝的 MCP 伺服器下次可直接回想。
- **反思** — 三種反思模式(per-task、on-failure、idle-batch)重新閱讀對話紀錄並更新使用者模型:明確偏好(如「使用 VSCode」)、推論畫像(「經常晚上寫程式」)、重複行為模式。下次工作階段開啟時,這些上下文已經在系統提示中了。

### 能做什麼

- 執行 shell 指令(Windows 上為 PowerShell,其他平台為 bash),附帶 hardline 守衛
- 在有範圍限制的 workspace 中讀取、編輯、搜尋檔案
- 透過沙箱化 alias 表開啟應用程式與 URL
- 透過免費的 [Exa MCP](https://mcp.exa.ai) 伺服器搜尋並擷取網頁——無需 API 金鑰
- 本地分析圖片與 PDF
- 操作你的電腦(Computer Use / cua):截圖、點擊、輸入、按鍵——具有獨立的風險層級
- 將新 skill 持久化為 SQLite experience 記錄(P6)——本次工作階段安裝的 MCP 即為下次工作階段的回憶
- 透過 Telegram、Feishu 或 WeChat 社交橋接進行對話

## 快速入門

需要 **Python 3.11+** 與 **Node.js 18+**。請使用系統的套件管理器安裝(`brew install python@3.11 node`、`apt install python3.11 python3.11-venv nodejs`,或在 Windows 上從 python.org / nodejs.org 下載安裝程式)。

### 複製並安裝

```bash
git clone https://github.com/sildo466/FSAR.git
cd FSAR
python3 -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 啟動

| 平台 | 指令 |
|---|---|
| Windows | `start.bat` |
| Linux / macOS | `./start.sh` |

第一次啟動會安裝前端相依套件(`npm install`)並建置 UI(`npm run build`);後續啟動會跳過安裝,重新建置僅需數秒。

### 終端機 CLI

```bash
python main.py
```

直接在終端機執行 FSAR——記憶、內建工具、安全閘門皆相同,僅無瀏覽器介面。終端機迴圈比 WebUI 簡單:固定工具輪數,無能力檔位、子代理、對抗式校驗、微反思與上下文壓縮。互動式工作階段中可使用斜線指令(輸入 `/help` 檢視;`/memory clear` 清除全部記憶)。以 `pip install -e .` 安裝後另有 `fsar` 主控台指令碼可用。

語音(TTS/ASR)與社交平台橋接(Telegram/飛書/微信)僅隨 WebUI 後端執行;終端機工作階段涵蓋聊天、工具、記憶與排程任務。

### 開啟

瀏覽器會自動開啟 <http://127.0.0.1:8765>。若未自動開啟,請手動前往該網址。

### 僅 macOS:授予 Computer Use 權限

開啟 **系統設定 → 隱私權與安全性 → 輔助使用**,並為你的終端機與 Python 授予存取權限。僅在使用 Computer Use 工具(`cu_screenshot`、`cu_click`、`cu_type`、`cu_keypress`)時才需要。

### 停止

| 平台 | 指令 |
|---|---|
| Windows | `taskkill /FI "WINDOWTITLE eq FSAR Backend*" /T /F` |
| Linux / macOS | `pkill -f "src.server.ws_server"` |

### 更新

```bash
git pull
pip install -r requirements.txt --upgrade
```

然後重新啟動。

## 特色

FSAR 與通用 AI 聊天應用程式有何不同。

### 本地優先

你的對話、記憶、決策紀錄全部儲存在 `~/.fsar/`——你自己機器上的 SQLite 資料庫。沒有任何東西會上傳到任何 FSAR 伺服器。LLM provider 只會看到你實際送出的訊息,與任何聊天客戶端無異。刪除 `~/.fsar/`,FSAR 便會遺忘一切。

### 由你定義的角色,不是通用助手

每個工作階段執行的是你撰寫的角色卡:名稱、性格、情境、選用的情緒狀態。再搭配一張描述你自己的使用者卡,LLM 收到的是範圍明確的 persona,而不是會離題的「helpful AI assistant」。換卡即換角,無需更動程式碼。

### 跨工作階段記住你

經過幾次對話後,FSAR 會建構出穩定的畫像:明確偏好(「使用 VSCode」)、推論行為(「經常晚上寫程式」)、重複模式(「通常用 file_ops 整理下載」)。下次工作階段開啟時,這些上下文已在系統提示中。你再也不必重新自我介紹。

### 適應你的風格

每次工具呼叫都會被記錄。strategy injector 觀察資料並合成一個 `## Learned Strategies` 區塊,餵給未來的 prompt——「檔案存在時優先使用 `edit` 而非 `file_ops write`」要等模型親身試錯過才會進 prompt。用得越久,FSAR 越懂得如何當*你的*助手。

### LLM 上的多層防禦

即使模型幻覺出 `rm -rf /` 或 `shutdown -h now`,硬編碼的守衛在任何沙箱檢查之前便截斷整個工具管線。再往上是:風險分類器(SAFE → CRITICAL)、限制檔案存取的 workspace gate、在執行 skill 前去除 API 金鑰的 subprocess 環境清理器。LLM 輸出與你的檔案系統之間相隔五層。

### 自備模型

OpenAI、Anthropic、Google、DeepSeek,或任何 OpenAI 相容的自訂端點。透過 Ollama 或 LM Studio 也能使用本地模型。你直接付費給 provider——FSAR 不抽成,沒有中間資料層。若你在工作階段中途切換 provider,FSAR 會在不遺失狀態的情況下換上新客戶端。

### 持續存在的 Skill

只需安裝一次 MCP 伺服器(GitHub、Postgres、Slack 及其他數百種)或 Python skill。FSAR 會將該程序記錄為 experience store 中的一筆紀錄——`active` → `stale` → `archived` 狀態機會自動晉升。下次工作階段,`experience_view` 會直接回想,無需重新安裝。

### 多管道

同一個引擎會透過 Telegram、Feishu(飛書)與 WeChat 進行對話。每個平台可獨立覆寫角色卡與使用者卡——你的 Telegram FSAR persona 可以與 GUI FSAR persona 不同,不必安裝兩份。

### 獨立管制的 Computer Use

computer-use 層級(`cua`)允許模型在桌面上進行截圖、點擊、輸入、按鍵。風險管制與一般工具分開——而在 macOS 上,作業系統本身會要求明確的輔助使用權限。

### 體積小

FSAR 很輕——一個 Python 服務加一個精簡的 Tauri 前端,clone 下來才 6~7MB,部署好也就約 200MB。沒有重型執行環境、不依賴雲端,一般配置的機器也能順跑。

## 教學

> 📖 本教學只是快速入門。完整文件（專案總覽、模組介紹、設定檔詳解、編譯/測試/開發教學）請前往 [`docs-public/`](docs-public/)。

### 專案結構

```
src/
  server/         FastAPI WebSocket 傳輸層
  core/           Agent 迴圈、prompts、injectors
  memory/         短期、長期、語意、使用者模型、experience
  tools/builtin/  約 25 個內建工具
  security/       風險引擎、permissions、稽核
  sandbox/        Hardline 守衛、workspace gate
  skills/         Python skill 執行環境
  social/         Telegram / Feishu / WeChat 配接器
  providers/      LLM / TTS / ASR 配接器
  utils/          日誌、組態、migrations
frontend/         Tauri 2 / React UI
data/             SQLite + ChromaDB + logs + cache
config/           隨附的 yaml 預設值
```

### 組態設定

`fsar.yaml` 是執行階段組態的唯一真實來源。

- `config/fsar.yaml.template` — 隨附預設值,唯讀參考
- `~/.fsar/config/fsar.yaml` — 你的副本,可透過 UI 或手動編輯

首次啟動時若你的副本不存在,會複製範本。區段:`llm` / `tts` / `asr` / `memory` / `security` / `social` / `mcp` / `reflection` / `permissions` / `user` / `style`。完整結構請見 [`config/fsar.yaml.template`](config/fsar.yaml.template)。

### 資料佈局

FSAR 對你的所有記憶都儲存在 `~/.fsar/` 之下:

```
~/.fsar/config/        yaml 檔案
~/.fsar/data/
  memory.db           對話、決策、使用者模型、experience
  chroma/             語意嵌入向量
  llm_cache.db        L1/L2 回應快取
  tts_cache.db        TTS 音訊快取
  logs/               循環日誌
```

刪除 `~/.fsar/` 即可讓 FSAR 回到全新狀態。

### 建置與測試

Python 後端與 Tauri 前端是分開的產物;沒有單一的「build」步驟。

```bash
# 後端
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 前端(僅在修改 TS/React 程式碼時需要)
cd frontend && npm install && npm run build

# 測試
pytest tests/ -q
```

跨平台測試位於 `tests/test_*_cross_platform.py`。

## License

[MIT](LICENSE)