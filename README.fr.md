# FSAR

<p align="center">
  <img src="assets/icons/logo-wordmark.svg" alt="FSAR" width="380">
</p>

<p align="center">
  <strong>Faithful · Safe · Adaptive · Reflective</strong><br>
  Un compagnon IA local-first qui grandit avec vous, pas à vos dépens.
</p>

<p align="center">
  <a href="README.md">English</a> ·
  <a href="README.zh-Hans.md">简体中文</a> ·
  <a href="README.ja.md">日本語</a> ·
  <a href="README.de.md">Deutsch</a> ·
  <a href="README.zh-Hant.md">繁體中文</a> ·
  <strong>Français</strong>
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

> **Note :** Cette traduction française n'est pas encore complète à 100 %.

## Qu'est-ce que FSAR ?

FSAR est un compagnon IA **local-first** qui **appartient à l'utilisateur**, pas à un éditeur. Les conversations, les souvenirs et l'historique des décisions vivent entièrement dans une base SQLite sous `~/.fsar/` sur votre propre machine. Rien n'est téléversé.

Le nom est aussi le contrat de conception : **F**aithful · **S**afe · **A**daptive · **R**eflective.

### Les quatre piliers

- **Faithful** — FSAR est exactement le personnage que vous avez défini (carte de personnage : nom, personnalité, scénario, état émotionnel optionnel), en conversation avec exactement l'utilisateur que vous avez décrit (carte d'utilisateur). Il ne dérive pas vers un « assistant IA générique ».
- **Safe** — Chaque appel d'outil traverse plusieurs couches de vérification : un garde-fou hardline codé en dur intercepte les commandes shell destructrices (`rm -rf /`, `shutdown`, `mkfs`) avant toute vérification de bac à sable ; un moteur de risque classe chaque outil en SAFE/LOW/MEDIUM/HIGH/CRITICAL ; une porte workspace confine l'accès aux fichiers ; un nettoyeur d'environnement de sous-processus supprime les clés API avant d'exécuter des skills.
- **Adaptive** — Chaque appel d'outil est journalisé. Un injecteur de stratégie synthétise à partir du journal de décisions et du modèle utilisateur un bloc `## Learned Strategies` pour les prompts futurs — « Préférer `edit` à `file_ops write` quand le fichier existe » n'apparaît dans le prompt système qu'une fois que le modèle en a fait lui-même l'expérience. Un magasin d'expériences conserve la connaissance procédurale, donc une installation de serveur MCP faite dans une session est rappelée dans la suivante.
- **Reflective** — Trois modes de réflexion (per-task, on-failure, idle-batch) relisent les conversations et mettent à jour le modèle utilisateur : préférences explicites (par ex. « utilise VSCode »), profil inféré (« code souvent le soir »), schémas comportementaux récurrents. La session suivante démarre avec ce contexte déjà dans le prompt système.

### Ce qu'il sait faire

- Exécuter des commandes shell (PowerShell sous Windows, bash ailleurs) avec garde-fou hardline
- Lire, modifier, chercher des fichiers dans des workspaces délimités
- Ouvrir des applications et URL via une table d'alias bac-à-sable
- Chercher et récupérer le web via le serveur [Exa MCP](https://mcp.exa.ai) gratuit — aucune clé API requise
- Analyser images et PDF localement
- Piloter votre ordinateur (Computer Use / cua) : capture, clic, frappe, touche — barrière de risque séparée
- Persister les nouveaux skills en lignes d'expérience SQLite (P6) — l'installation MCP d'une session devient le rappel de la suivante
- Dialoguer via Telegram, Feishu ou WeChat grâce au pont social

## Démarrage rapide

Vous avez besoin de **Python 3.11+** et **Node.js 18+**. Installez-les avec le gestionnaire de paquets de votre plateforme (`brew install python@3.11 node`, `apt install python3.11 python3.11-venv nodejs`, ou sous Windows les installateurs depuis python.org / nodejs.org).

### Cloner et installer

```bash
git clone https://github.com/sildo466/FSAR.git
cd FSAR
python3 -m venv .venv
source .venv/bin/activate    # Windows : .venv\Scripts\activate
pip install -r requirements.txt
```

### Lancer

| Plateforme | Commande |
|---|---|
| Windows | `start.bat` |
| Linux / macOS | `./start.sh` |

Le premier lancement installe les dépendances frontend (`npm install`) et construit l'UI (`npm run build`) ; les lancements suivants sautent l'installation et reconstruisent en quelques secondes.

### CLI terminal

```bash
python main.py
```

Exécute FSAR dans votre terminal — mêmes mémoire, outils intégrés et barrières de sécurité, sans l'interface navigateur. La boucle est plus simple que celle de la WebUI : budget d'outils fixe, sans niveaux de capacité, sous-agents, vérification contradictoire, micro-réflexion ni compression de contexte. La session interactive accepte les commandes slash (`/help` pour la liste ; `/memory clear` efface toute la mémoire). Une installation avec `pip install -e .` fournit aussi un script console `fsar`.

La voix (TTS/ASR) et les passerelles sociales (Telegram/Feishu/WeChat) ne fonctionnent qu'avec le backend WebUI ; la session terminal couvre le chat, les outils, la mémoire et les tâches planifiées.

### Ouvrir

Le navigateur s'ouvre automatiquement sur <http://127.0.0.1:8765>. Sinon, naviguez-y manuellement.

### macOS uniquement : accorder la permission Computer Use

Ouvrez **Réglages système → Confidentialité et sécurité → Accessibilité** et accordez l'accès à votre terminal et à Python. Nécessaire uniquement pour les outils Computer Use (`cu_screenshot`, `cu_click`, `cu_type`, `cu_keypress`).

### Arrêter

| Plateforme | Commande |
|---|---|
| Windows | `taskkill /FI "WINDOWTITLE eq FSAR Backend*" /T /F` |
| Linux / macOS | `pkill -f "src.server.ws_server"` |

### Mettre à jour

```bash
git pull
pip install -r requirements.txt --upgrade
```

Puis relancez.

## Points forts

Ce qui distingue FSAR d'une app de chat IA générique.

### Local-first

Vos conversations, vos souvenirs et votre historique de décisions vivent entièrement dans `~/.fsar/` — une base SQLite sur votre machine. Rien n'est téléversé vers un serveur FSAR. Le fournisseur de LLM ne voit que les messages que vous envoyez effectivement, comme avec n'importe quel client de chat. Supprimez `~/.fsar/` et FSAR oublie tout.

### Un personnage que vous avez défini, pas un assistant générique

Chaque session exécute une carte de personnage que vous avez écrite : nom, personnalité, scénario, état émotionnel optionnel. Combinée à une carte d'utilisateur qui vous décrit, le LLM reçoit une persona au périmètre bien défini — pas un « assistant IA serviable » qui dérive. Changez la carte, changez le personnage ; aucune modification de code.

### Il se souvient de vous d'une session à l'autre

Après quelques conversations, FSAR construit un profil stable : préférences explicites (« utilise VSCode »), comportements inférés (« code souvent le soir »), schémas récurrents (« range généralement les téléchargements via file_ops »). La session suivante démarre avec ce contexte déjà dans le prompt système. Vous n'avez plus jamais à vous re-expliquer.

### Il s'adapte à votre style

Chaque appel d'outil est journalisé. Un injecteur de stratégie observe les données et synthétise un bloc `## Learned Strategies` pour les prompts futurs — « Préférer `edit` à `file_ops write` quand le fichier existe » n'apparaît qu'une fois que le modèle en a fait lui-même l'expérience. Plus vous utilisez FSAR, meilleur il devient en tant que *votre* assistant.

### Défense en profondeur face au LLM

Même si le modèle hallucine `rm -rf /` ou `shutdown -h now`, un garde-fou codé en dur court-circuite toute la chaîne d'outils avant la moindre vérification de bac à sable. Par-dessus : un classificateur de risque (SAFE → CRITICAL), une porte workspace qui confine l'accès aux fichiers, et un nettoyeur d'environnement de sous-processus qui supprime les clés API avant l'exécution des skills. Cinq couches entre toute sortie de LLM et votre système de fichiers.

### Apportez votre propre modèle

OpenAI, Anthropic, Google, DeepSeek, ou tout endpoint personnalisé compatible OpenAI. Les modèles locaux via Ollama ou LM Studio fonctionnent aussi. Vous payez le fournisseur directement — pas de marge FSAR, pas de couche de données intermédiaire. Si vous changez de fournisseur en pleine session, FSAR remplace le client sans perdre l'état.

### Des skills qui persistent

Installez un serveur MCP (GitHub, Postgres, Slack et des centaines d'autres) ou un skill Python une seule fois. FSAR enregistre la procédure comme une ligne du magasin d'expériences — machine à états `active` → `stale` → `archived` avec promotion automatique. À la session suivante, `experience_view` la rappelle sans réinstallation.

### Multi-canal

Le même moteur dialogue via Telegram, Feishu (Lark) et WeChat. Chaque plateforme peut surcharger indépendamment la carte de personnage et la carte d'utilisateur — votre persona FSAR sur Telegram peut différer de celle sur l'interface graphique, sans deux installations.

### Computer Use, barrière séparée

Un niveau Computer Use (`cua`) permet au modèle de capturer, cliquer, taper et frapper des touches sur votre bureau. La barrière de risque est séparée des outils ordinaires — et sous macOS le système lui-même exige une autorisation d'accessibilité explicite.

### Empreinte légère

FSAR est compact et léger — un service Python unique plus un frontend Tauri minimal. Pas de runtime lourd ni de dépendance au cloud ; il tourne sans peine sur du matériel modeste.

## Tutoriel

> 📖 Ce tutoriel est une introduction rapide. Pour la documentation complète (aperçu du projet, référence des modules, guide de configuration complet, guide de build/test/développement), voir [`docs-public/`](docs-public/).

### Structure du projet

```
src/
  server/         Transport WebSocket FastAPI
  core/           Boucle agent, prompts, injecteurs
  memory/         court terme, long terme, sémantique, modèle utilisateur, expérience
  tools/builtin/  ~25 outils intégrés
  security/       Moteur de risque, permissions, audit
  sandbox/        Garde-fou hardline, porte workspace
  skills/         Runtime des skills Python
  social/         Adaptateurs Telegram / Feishu / WeChat
  providers/      Adaptateurs LLM / TTS / ASR
  utils/          Logger, configuration, migrations
frontend/         UI Tauri 2 / React
data/             SQLite + ChromaDB + logs + cache
config/           valeurs par défaut yaml fournies
```

### Configuration

`fsar.yaml` est l'unique source de vérité pour la configuration d'exécution.

- `config/fsar.yaml.template` — valeurs par défaut fournies, lecture seule
- `~/.fsar/config/fsar.yaml` — votre copie, modifiée via l'UI ou à la main

Au premier lancement, le modèle est copié si votre copie manque. Sections : `llm` / `tts` / `asr` / `memory` / `security` / `social` / `mcp` / `reflection` / `permissions` / `user` / `style`. Schéma complet : [`config/fsar.yaml.template`](config/fsar.yaml.template).

### Disposition des données

Tout ce que FSAR retient de vous vit sous `~/.fsar/` :

```
~/.fsar/config/        fichiers yaml
~/.fsar/data/
  memory.db           conversations, décisions, modèle utilisateur, expérience
  chroma/             plongements sémantiques
  llm_cache.db        cache L1/L2 des réponses
  tts_cache.db        cache audio TTS
  logs/               journaux rotatifs
```

Supprimez `~/.fsar/` pour remettre FSAR à un état propre.

### Build et tests

Le backend Python et le frontend Tauri sont des artefacts séparés ; il n'y a pas d'étape unique de « build ».

```bash
# Backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Frontend (nécessaire seulement si vous modifiez du code TS/React)
cd frontend && npm install && npm run build

# Tests
pytest tests/ -q
```

Les tests multi-plateforme sont dans `tests/test_*_cross_platform.py`.

## Licence

[MIT](LICENSE)