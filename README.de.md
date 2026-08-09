# FSAR

<p align="center">
  <img src="assets/icons/logo-wordmark.svg" alt="FSAR" width="380">
</p>

<p align="center">
  <strong>Faithful · Safe · Adaptive · Reflective</strong><br>
  Ein Local-First-AI-Begleiter, der mit dir wächst, nicht auf deine Kosten.
</p>

<p align="center">
  <a href="README.md">English</a> ·
  <a href="README.zh-Hans.md">简体中文</a> ·
  <a href="README.ja.md">日本語</a> ·
  <strong>Deutsch</strong> ·
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

> **Hinweis:** Diese deutsche Übersetzung ist noch nicht zu 100 % vollständig.

## Was ist FSAR?

FSAR ist ein Local-First-AI-Begleiter, der **dem Nutzer gehört**, nicht einem Anbieter. Konversationen, Erinnerungen und Entscheidungshistorie leben vollständig in einer SQLite-Datenbank unter `~/.fsar/` auf deiner eigenen Maschine. Es wird nichts hochgeladen.

Der Name ist zugleich der Designvertrag: **F**aithful · **S**afe · **A**daptive · **R**eflective.

### Die vier Säulen

- **Faithful** — FSAR ist genau die Figur, die du in der Character Card festlegst (Name, Persönlichkeit, Szenario, optionaler Emotionszustand). Sie spricht mit dem Nutzer, den du in der User Card beschrieben hast. Es driftet nicht in einen "generischen Assistenten" ab.
- **Safe** — Jeder Tool-Aufruf durchläuft mehrstufige Prüfungen: Ein hartkodierter Hardline-Wächter blockiert destruktive Shell-Befehle (`rm -rf /`, `shutdown`, `mkfs`) noch vor jeder Sandbox-Prüfung. Eine Risiko-Engine klassifiziert jedes Werkzeug als SAFE/LOW/MEDIUM/HIGH/CRITICAL. Ein Workspace-Gate schränkt Datei-Zugriffe ein. Ein Subprocess-Env-Scrubber entfernt API-Keys und Tokens, bevor Skills ausgeführt werden.
- **Adaptive** — Jeder Tool-Aufruf wird protokolliert. Ein Strategy-Injector synthetisiert aus dem Decision-Log und dem User-Modell einen `## Learned Strategies`-Block für künftige Prompts — "Bevorzuge `edit` gegenüber `file_ops write`, wenn die Datei existiert" taucht im System-Prompt erst auf, nachdem das Modell sich diese Lektion am eigenen Leib erarbeitet hat. Ein Experience-Store speichert prozedurales Wissen, sodass eine in einer Session installierte MCP-Server-Installation in der nächsten erinnert wird.
- **Reflective** — Drei Reflexions-Modi (per-task, on-failure, idle-batch) lesen Konversationen erneut und aktualisieren das User-Modell: explizite Präferenzen (z. B. "nutzt VSCode"), abgeleitetes Profil ("codet häufig abends"), wiederkehrende Verhaltensmuster. Die nächste Session startet mit diesem Kontext bereits im System-Prompt.

### Was kann FSAR?

- Shell-Befehle ausführen (Windows: PowerShell, sonst bash) mit Hardline-Wächter
- Dateien in abgegrenzten Workspaces lesen, bearbeiten, durchsuchen
- Apps und URLs über eine sandboxierte Alias-Tabelle öffnen
- Web suchen und abrufen über den kostenlosen [Exa-MCP](https://mcp.exa.ai)-Server — kein API-Key erforderlich
- Bilder und PDFs lokal analysieren
- Deinen Computer bedienen (Computer Use / cua): Screenshot, Klick, Tippen, Tastendruck — separat abgesichert
- Neue Skills als SQLite-Experience-Zeilen (P6) speichern — die MCP-Installation einer Session ist die Erinnerung der nächsten
- Über Telegram, Feishu oder WeChat via Social-Bridge kommunizieren

## Schnellstart

Du brauchst **Python 3.11+** und **Node.js 18+**. Installiere sie mit dem Paketmanager deiner Plattform (`brew install python@3.11 node`, `apt install python3.11 python3.11-venv nodejs`, oder unter Windows die Installer von python.org / nodejs.org).

### Klonen und installieren

```bash
git clone https://github.com/sildo466/FSAR.git
cd FSAR
python3 -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Starten

| Plattform | Befehl |
|---|---|
| Windows | `start.bat` |
| Linux / macOS | `./start.sh` |

Der erste Start installiert Frontend-Abhängigkeiten (`npm install`) und baut die UI (`npm run build`); spätere Starts überspringen die Installation und rebuilden in Sekunden.

### Terminal-CLI

```bash
python main.py
```

Führt FSAR im Terminal aus — gleicher Speicher, gleiche integrierte Werkzeuge, gleiche Sicherheitsregeln, nur ohne Browser-UI. Die Loop ist einfacher als die der WebUI: festes Tool-Budget, keine Capability-Tiers, keine Subagenten, keine adversariale Verifikation, keine Mikro-Reflexion, keine Kontext-Komprimierung. In der interaktiven Sitzung funktionieren Slash-Befehle (`/help` zeigt alle; `/memory clear` löscht alle Erinnerungen). Mit `pip install -e .` gibt es außerdem das `fsar`-Konsolenskript.

Sprache (TTS/ASR) und die Social-Bridges (Telegram/Feishu/WeChat) laufen nur mit dem WebUI-Backend; die Terminalsitzung deckt Chat, Werkzeuge, Speicher und geplante Aufgaben ab.

### Öffnen

Der Browser öffnet sich automatisch auf <http://127.0.0.1:8765>. Falls nicht, öffne die URL manuell.

### Nur macOS: Computer-Use-Berechtigung erteilen

Öffne **Systemeinstellungen → Datenschutz & Sicherheit → Bedienungshilfen** und erteile deinem Terminal und Python Zugriff. Nur für die Computer-Use-Werkzeuge (`cu_screenshot`, `cu_click`, `cu_type`, `cu_keypress`) erforderlich.

### Stoppen

| Plattform | Befehl |
|---|---|
| Windows | `taskkill /FI "WINDOWTITLE eq FSAR Backend*" /T /F` |
| Linux / macOS | `pkill -f "src.server.ws_server"` |

### Aktualisieren

```bash
git pull
pip install -r requirements.txt --upgrade
```

Danach neu starten.

## Highlights

Was FSAR von einer generischen KI-Chat-App unterscheidet.

### Local-First

Deine Konversationen, Erinnerungen und Entscheidungshistorie liegen vollständig in `~/.fsar/` — einer SQLite-Datenbank auf deiner Maschine. Es wird nichts zu einem FSAR-Server hochgeladen. Der LLM-Provider sieht nur die Nachrichten, die du tatsächlich sendest, genau wie bei jedem Chat-Client. Lösche `~/.fsar/` und FSAR vergisst alles.

### Eine Figur, die du definiert hast, kein generischer Assistent

Jede Session führt eine Character Card aus, die du geschrieben hast: Name, Persönlichkeit, Szenario, optionaler Emotionszustand. Kombiniert mit einer User Card, die dich beschreibt, erhält das LLM eine eng umrissene Persona — keinen "hilfreichen KI-Assistenten", der abschweift. Karte tauschen, Figur tauschen — keine Code-Änderung.

### Es erinnert sich über Sessions hinweg an dich

Nach wenigen Konversationen baut FSAR ein stabiles Profil auf: explizite Präferenzen ("nutzt VSCode"), abgeleitetes Verhalten ("codet häufig abends"), wiederkehrende Muster ("sortiert Downloads meist über file_ops"). Die nächste Session startet mit diesem Kontext bereits im System-Prompt. Du musst dich nie erneut erklären.

### Es passt sich deinem Stil an

Jeder Tool-Aufruf wird protokolliert. Ein Strategy-Injector beobachtet die Daten und synthetisiert einen `## Learned Strategies`-Block für künftige Prompts — "Bevorzuge `edit` gegenüber `file_ops write`, wenn die Datei existiert" taucht erst auf, nachdem das Modell sich diese Lektion am eigenen Leib erarbeitet hat. Je länger du FSAR nutzt, desto besser wird es darin, *dein* Assistent zu sein.

### Mehrstufige Verteidigung gegen das LLM

Selbst wenn das Modell `rm -rf /` oder `shutdown -h now` halluziniert, schneidet ein hartkodierter Wächter die gesamte Tool-Pipeline ab, bevor irgendeine Sandbox-Prüfung läuft. Darüber: ein Risiko-Klassifizierer (SAFE → CRITICAL), ein Workspace-Gate, das Datei-Zugriffe einschränkt, und ein Subprocess-Env-Scrubber, der API-Keys vor der Skill-Ausführung entfernt. Fünf Schichten zwischen jeder LLM-Ausgabe und deinem Dateisystem.

### Bring dein eigenes Modell

OpenAI, Anthropic, Google, DeepSeek oder jeder beliebige OpenAI-kompatible Endpunkt. Lokale Modelle via Ollama oder LM Studio funktionieren ebenfalls. Du zahlst direkt an den Provider — keine FSAR-Aufschläge, keine zwischengeschaltete Datenschicht. Wenn du mitten in der Session den Provider wechselst, tauscht FSAR den Client aus, ohne den Zustand zu verlieren.

### Skills, die bestehen bleiben

Installiere einen MCP-Server (GitHub, Postgres, Slack und Hunderte weitere) oder einen Python-Skill einmal. FSAR protokolliert das Verfahren als Zeile im Experience-Store — `active` → `stale` → `archived`-Zustandsmaschine mit automatischer Hochstufung. In der nächsten Session erinnert `experience_view` das Verfahren ohne Neuinstallation.

### Multi-Channel

Dieselbe Engine spricht über Telegram, Feishu (Lark) und WeChat. Jede Plattform kann die Character Card und User Card unabhängig überschreiben — deine Telegram-FSAR-Persona kann sich von deiner GUI-FSAR-Persona unterscheiden, ohne zwei Installationen.

### Computer Use, separat abgesichert

Ein Computer-Use-Tier (`cua`) erlaubt dem Modell Screenshot, Klick, Tippen und Tastendruck auf deinem Desktop. Das Risiko-Gate ist vom Standard-Tool getrennt — und unter macOS verlangt das OS selbst eine explizite Bedienungshilfen-Berechtigung.

### Geringe Ressourcen

FSAR ist kompakt und leichtgewichtig — ein einziger Python-Dienst plus ein schlankes Tauri-Frontend. Kein schwerer Laufzeit- oder Cloud-Bedarf; es läuft auch auf bescheidener Hardware flüssig.

## Anleitung

> 📖 Diese Anleitung ist nur ein Schnellstart. Die vollständige Dokumentation (Projektübersicht, Modulreferenz, vollständige Konfigurationsanleitung, Build-/Test-/Entwicklungsleitfaden) finden Sie unter [`docs-public/`](docs-public/).

### Projektstruktur

```
src/
  server/         FastAPI WebSocket-Transport
  core/           Agent-Schleife, Prompts, Injectors
  memory/         Kurzzeit, Langzeit, semantisch, User-Modell, Experience
  tools/builtin/  ~25 eingebaute Werkzeuge
  security/       Risiko-Engine, Permissions, Audit
  sandbox/        Hardline-Wächter, Workspace-Gate
  skills/         Python-Skill-Laufzeit
  social/         Telegram / Feishu / WeChat-Adapter
  providers/      LLM / TTS / ASR-Adapter
  utils/          Logger, Konfiguration, Migrations
frontend/         Tauri 2 / React-UI
data/             SQLite + ChromaDB + Logs + Cache
config/           ausgelieferte yaml-Standards
```

### Konfiguration

`fsar.yaml` ist die einzige Quelle der Wahrheit für die Laufzeitkonfiguration.

- `config/fsar.yaml.template` — ausgelieferte Standards, schreibgeschützt
- `~/.fsar/config/fsar.yaml` — deine Kopie, per UI oder manuell bearbeitet

Beim ersten Start wird die Vorlage kopiert, falls deine Kopie fehlt. Sektionen: `llm` / `tts` / `asr` / `memory` / `security` / `social` / `mcp` / `reflection` / `permissions` / `user` / `style`. Vollständiges Schema siehe [`config/fsar.yaml.template`](config/fsar.yaml.template).

### Datenlayout

Alles, was FSAR über dich speichert, liegt unter `~/.fsar/`:

```
~/.fsar/config/        yaml-Dateien
~/.fsar/data/
  memory.db           Konversationen, Entscheidungen, User-Modell, Experience
  chroma/             semantische Embeddings
  llm_cache.db        L1/L2-Antwortcache
  tts_cache.db        TTS-Audiocache
  logs/               rotierende Log-Dateien
```

Lösche `~/.fsar/`, um FSAR in einen sauberen Zustand zurückzusetzen.

### Bauen und testen

Python-Backend und Tauri-Frontend sind getrennte Artefakte; es gibt keinen einzelnen "Build"-Schritt.

```bash
# Backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Frontend (nur nötig, wenn du TS/React-Code änderst)
cd frontend && npm install && npm run build

# Tests
pytest tests/ -q
```

Cross-Plattform-Tests liegen in `tests/test_*_cross_platform.py`.

## Lizenz

[MIT](LICENSE)