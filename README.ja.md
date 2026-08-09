# FSAR

<p align="center">
  <img src="assets/icons/logo-wordmark.svg" alt="FSAR" width="380">
</p>

<p align="center">
  <strong>忠実 · 安全 · 適応 · 内省</strong><br>
  あなたと共に育つ、ローカルファーストの AI コンパニオン。
</p>

<p align="center">
  <a href="README.md">English</a> ·
  <a href="README.zh-Hans.md">简体中文</a> ·
  <strong>日本語</strong> ·
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

## FSAR とは?

FSAR はベンダーではなく**ユーザーに属する**ローカルファーストの AI コンパニオンです。会話、記憶、判断履歴はすべてあなたのマシン上の `~/.fsar/` ディレクトリにある SQLite データベースに保存されます。アップロードされるものは何もありません。

名前そのものが設計契約です:**F**aithful · **S**afe · **A**daptive · **R**eflective。

### 4 つの柱

- **忠実 (Faithful)** — FSAR はあなたが定義したキャラクター(名前・性格・シナリオ・感情状態を持つキャラクターカード)と、あなたが記述したユーザー(ユーザーカード)に応じた存在です。一般的な「AI アシスタント」に脱線しません。
- **安全 (Safe)** — ツール呼び出しはすべて多層チェックを経ます:サンドボックス検査より前にハードコードされた hardline ガードが破壊的なシェルコマンド(`rm -rf /`、`shutdown`、`mkfs`)を遮断。リスクエンジンがツールを SAFE/LOW/MEDIUM/HIGH/CRITICAL に分類。workspace gate がファイルアクセスを制限。subprocess 環境スクランバーが skill 実行前に API キーを剥離。
- **適応 (Adaptive)** — ツール呼び出しはすべてログ化されます。strategy injector が決定ログとユーザーモデルから `## Learned Strategies` ブロックを合成し、後のプロンプトに注入——「ファイルが存在する場合は `file_ops write` ではなく `edit` を優先する」のような教訓は、モデル自身が一度失敗してからでないとシステムプロンプトには現れません。experience store が手続き的知識を永続化し、あるセッションでインストールした MCP サーバーを次回想起できます。
- **内省 (Reflective)** — 3 つの内省モード(per-task / on-failure / idle-batch)が会話を再読し、ユーザーモデルを更新:明示的な好み(例「VSCode を使う」)、推論されたプロフィール(例「夕方にコードを書くことが多い」)、繰り返し現れる行動パターン。次回セッション開始時にそのコンテキストはすでにシステムプロンプトに入っています。

### できること

- シェルコマンド実行(Windows は PowerShell、他は bash)+ hardline ガード
- スコープされた workspace でのファイル読み書き・検索
- サンドボックス化されたエイリアス経由のアプリと URL 起動
- 無料の [Exa MCP](https://mcp.exa.ai) サーバー経由で Web を検索・取得——API キー不要
- 画像と PDF のローカル解析
- コンピュータの操作(Computer Use / cua):スクリーンショット・クリック・入力・キーストローク——独立したリスクゲート
- 新規 skill の SQLite experience 行への永続化(P6)——あるセッションの MCP インストールが次回セッションの記憶になる
- Telegram / Feishu / WeChat のソーシャルブリッジ経由の対話

## クイックスタート

**Python 3.11+** と **Node.js 18+** が必要です。お使いのプラットフォームのパッケージマネージャーでインストールしてください(`brew install python@3.11 node`、`apt install python3.11 python3.11-venv nodejs`、または Windows では python.org / nodejs.org のインストーラーで)。

### クローンとインストール

```bash
git clone https://github.com/sildo466/FSAR.git
cd FSAR
python3 -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 起動

| プラットフォーム | コマンド |
|---|---|
| Windows | `start.bat` |
| Linux / macOS | `./start.sh` |

初回起動時にフロントエンドの依存関係をインストールし(`npm install`)、UI をビルドします(`npm run build`)。2回目以降はインストールをスキップし、数秒でリビルドします。

### ターミナル CLI

```bash
python main.py
```

ブラウザ UI なしで FSAR をターミナルで実行します——メモリ・組み込みツール・安全ゲートはすべて同一です。ターミナルのループは WebUI よりシンプルで、固定のツールターン数、能力ティア・サブエージェント・敵対的検証・マイクロリフレクション・コンテキスト圧縮はいずれもありません。対話セッションではスラッシュコマンドが使えます(`/help` で一覧表示、`/memory clear` ですべてのメモリを消去)。`pip install -e .` でインストールすると `fsar` コンソールスクリプトも利用できます。

音声(TTS/ASR)とソーシャル連携(Telegram/Feishu/WeChat)は WebUI バックエンドでのみ動作します。ターミナルセッションはチャット・ツール・メモリ・スケジュールをカバーします。

### 開く

ブラウザが自動的に <http://127.0.0.1:8765> を開きます。開かない場合は手動でアクセスしてください。

### macOS のみ:Computer Use の権限付与

**システム設定 → プライバシーとセキュリティ → アクセシビリティ** を開き、ターミナルアプリと Python にアクセス権を付与してください。Computer Use ツール(`cu_screenshot`、`cu_click`、`cu_type`、`cu_keypress`)を使用する場合のみ必要です。

### 停止

| プラットフォーム | コマンド |
|---|---|
| Windows | `taskkill /FI "WINDOWTITLE eq FSAR Backend*" /T /F` |
| Linux / macOS | `pkill -f "src.server.ws_server"` |

### 更新

```bash
git pull
pip install -r requirements.txt --upgrade
```

その後再起動。

## 特徴

FSAR が汎用 AI チャットアプリと異なる点。

### ローカルファースト

会話・記憶・判断履歴はすべて `~/.fsar/`——あなたのマシン上の SQLite データベース——にあります。FSAR サーバーには何もアップロードされません。LLM プロバイダーはあなたが実際に送信したメッセージだけを見ます。`~/.fsar/` を削除すれば FSAR はすべてを忘れます。

### あなたが定義したキャラクター

各セッションはあなたが書いたキャラクターカード(名前・性格・シナリオ・任意の感情状態)を実行します。自分自身を記述したユーザーカードと組み合わせると、LLM は脱線しない範囲のペルソナになります。カードを差し替えればキャラクターも変わります——コード変更は不要。

### セッションを跨いであなたを記憶する

数回の会話の後、FSAR は安定したプロフィールを構築します:明示的な好み(「VSCode を使う」)、推論された行動(「夕方にコードを書く」)、繰り返し現れるパターン(「file_ops でダウンロードを整理する」)。次回セッション開始時にそのコンテキストはすでにシステムプロンプトに入っています。もう自分自身を説明し直す必要はありません。

### あなたのスタイルに適応する

すべてのツール呼び出しがログ化されます。strategy injector がデータを観察し、後のプロンプトに投入する `## Learned Strategies` ブロックを合成します。長く使えば使うほど、FSAR は*あなたの*アシスタントとして上手くなります。

### LLM への多層防御

モデルが `rm -rf /` や `shutdown -h now` を幻視しても、サンドボックス検査より前にハードコードされたガードがツールパイプライン全体を遮断します。さらに上には:リスク分類器(SAFE → CRITICAL)、ファイルアクセスを制限する workspace gate、skill 実行前に API キーを剥離する subprocess 環境スクランバー。LLM の出力とあなたのファイルシステムの間には 5 つの層があります。

### 自前のモデル

OpenAI、Anthropic、Google、DeepSeek、または任意の OpenAI 互換カスタムエンドポイント。Ollama や LM Studio 経由のローカルモデルも動作します。プロバイダーに直接支払い——FSAR は手数料を取らず、中間データ層を持ちません。セッション途中でプロバイダーを切り替えても、FSAR は状態を失わずに新しいクライアントに差し替えます。

### 永続化するスキル

MCP サーバー(GitHub、Postgres、Slack、その他多数)または Python スキルを 1 回インストール。FSAR はその手順を experience store に行として記録します——`active` → `stale` → `archived` の状態マシンが自動昇格。次回セッションでは `experience_view` が再インストールなしで想起します。

### マルチチャンネル

同じエンジンが Telegram、Feishu(飛書)、WeChat 経由で対話します。各プラットフォームはキャラクターカードとユーザーカードを独立にオーバーライドできます——Telegram の FSAR ペルソナは GUI の FSAR ペルソナと異なっていても、2 つのインストールは不要です。

### 別ゲートで保護された Computer Use

computer-use ティア(`cua`)はモデルにデスクトップでのスクリーンショット・クリック・入力・キーストロークを許可します。リスクゲートは通常ツールとは別——macOS では OS 自体が明示的なアクセシビリティ権限を要求します。

### 軽量

FSAR はコンパクトで軽量です——単一の Python サービスとスリムな Tauri フロントエンド。重いランタイムもクラウド依存もなく、標準的なハードウェアでも快適に動作します。

## チュートリアル

> 📖 このチュートリアルは簡単な入門です。完全なドキュメント（プロジェクト概要、モジュール紹介、設定ファイルの詳細、ビルド/テスト/開発ガイド）は [`docs-public/`](docs-public/) をご覧ください。

### プロジェクト構成

```
src/
  server/         FastAPI WebSocket トランスポート
  core/           エージェントループ、プロンプト、インジェクター
  memory/         短期・長期・セマンティック・ユーザーモデル・experience
  tools/builtin/  約 25 個の組み込みツール
  security/       リスクエンジン、permissions、監査
  sandbox/        Hardline ガード、workspace gate
  skills/         Python skill ランタイム
  social/         Telegram / Feishu / WeChat アダプター
  providers/      LLM / TTS / ASR アダプター
  utils/          ロガー、設定、migrations
frontend/         Tauri 2 / React UI
data/             SQLite + ChromaDB + ログ + キャッシュ
config/           出荷時の yaml デフォルト
```

### 設定

`fsar.yaml` がランタイム設定の単一の真実の源です。

- `config/fsar.yaml.template` — 出荷時のデフォルト(読み取り専用)
- `~/.fsar/config/fsar.yaml` — あなたのコピー(UI または手編集)

初回起動時にあなたのコピーがなければテンプレートをコピーします。セクション:`llm` / `tts` / `asr` / `memory` / `security` / `social` / `mcp` / `reflection` / `permissions` / `user` / `style`。完全なスキーマは [`config/fsar.yaml.template`](config/fsar.yaml.template) を参照。

### データ配置

FSAR があなたについて覚えているものはすべて `~/.fsar/` 配下にあります:

```
~/.fsar/config/        yaml ファイル
~/.fsar/data/
  memory.db           会話、決定、ユーザーモデル、experience
  chroma/             セマンティック埋め込み
  llm_cache.db        L1/L2 レスポンスキャッシュ
  tts_cache.db        TTS オーディオキャッシュ
  logs/               ローテーションログ
```

`~/.fsar/` を削除すると FSAR はクリーン状態に戻ります。

### ビルドとテスト

Python バックエンドと Tauri フロントエンドは別アーティファクトであり、単一の「ビルド」ステップはありません。

```bash
# バックエンド
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# フロントエンド(TS/React コードを変更したときのみ必要)
cd frontend && npm install && npm run build

# テスト
pytest tests/ -q
```

クロスプラットフォームテストは `tests/test_*_cross_platform.py` にあります。

## ライセンス

[MIT](LICENSE)