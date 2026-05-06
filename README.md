# WinBoost

**Le premier assistant Windows qui ne te ment pas.**

WinBoost est un assistant systeme Windows conversationnel. Il scanne, analyse et corrige les problemes courants via 8 modules d'optimisation et un chat IA intelligent avec 180+ actions natives.

## Features

### v1.0 — Modules + CLI + GUI
- **8 modules d'optimisation** independants
- **CLI complete** avec Rich (couleurs, tableaux)
- **GUI CustomTkinter** avec dark theme
- **Backup automatique** avant chaque action + rollback
- **Historique SQLite** de toutes les actions

### v2.0 — AI Engine + Chat
- **Chat IA conversationnel** avec ActionRouter + cache keyword (70% resolu localement)
- **150 actions YAML** reparties en 9 categories
- **3 profils de securite** : Safe, Power User, Expert
- **Onboarding premier lancement** (choix profil + config API)
- **History viewer** avec timeline, filtres et undo
- **Settings complet** (profil, API keys, langue, modules)
- **Providers LLM** : Anthropic (Claude), OpenAI (GPT), Ollama (local)

### v2.1 — Native Windows + Hotkey

- **+30 actions Windows-natives** (180 actions au total) : luminosite, dark mode, volume, bluetooth, focus assist, DNS, IPv6, animations, transparence, power plans
- **Hotkey global Win+Espace** : invoque WinBoost depuis n'importe quelle app, mini-overlay transparent (<50 ms), Esc pour fermer
- **Mode JSON CLI** (`--json`) : sortie parseable pour scripts et integrations
- **Helper Python `windows_native`** : API de bas niveau (brightness, dark mode, power plan) pour les developpeurs qui integrent WinBoost en lib

## Modules

| Module | Description | Risque |
|--------|-------------|--------|
| `temp_cleaner` | Nettoyage fichiers temporaires Windows | Low |
| `system_info` | Informations systeme (CPU, RAM, disques, OS) | Info |
| `startup_manager` | Gestion programmes au demarrage | Medium |
| `ram_optimizer` | Analyse et optimisation memoire vive | Medium |
| `disk_analyzer` | Analyse espace disque + gros fichiers | Low |
| `privacy_cleaner` | Traces navigateurs et donnees privees | Medium |
| `dev_cache_cleaner` | Caches dev (npm, pip, gradle, etc.) | Low |
| `service_optimizer` | Services Windows optionnels | High |

### Actions natives v2.1 (extrait)

Echantillon des 30 nouvelles actions Windows-natives ajoutees en v2.1. Liste complete dans `winboost/actions/{system,network,appearance}/actions.yaml`.

| ID | Nom | Categorie | Risque |
|----|-----|-----------|--------|
| `sys_011` | Enable Dark Mode | system | Low |
| `sys_013` | Set Brightness Low (30%) | system | Low |
| `sys_016` | Enable Focus Assist (Notifications Off) | system | Low |
| `net_011` | Disable Bluetooth | network | Medium |
| `net_015` | Set DNS Cloudflare (1.1.1.1) | network | Medium |
| `net_018` | Disable IPv6 (Registry) | network | High |
| `app_011` | Mute System Volume | appearance | Low |
| `app_018` | Disable Animations | appearance | Low |

## Installation

```bash
# Depuis les sources
git clone https://github.com/Antoine6958585/winboost.git
cd winboost
pip install -e ".[dev]"

# Ou directement l'executable
# Telecharger WinBoost.exe depuis la page Releases
```

**Prerequis** : Python 3.12+ / Windows 10+

## Utilisation

### CLI

```bash
# Scanner tous les modules
winboost scan

# Scanner un module specifique
winboost scan --module temp_cleaner

# Appliquer les corrections
winboost fix --module temp_cleaner --yes

# Informations systeme
winboost info

# Chat IA
winboost chat "desactive la telemetrie"
winboost chat "nettoie les fichiers temporaires"
winboost chat "optimise pour les jeux"

# Lancer la GUI
winboost gui
```

### Nouveautes v2.1

```bash
# Hotkey global (presser Win+Espace pour invoquer)
winboost overlay

# Sortie JSON pour scripting
winboost chat --json "passe en mode sombre"

# Exemple d'usage natif via lib Python
python -c "from winboost.utils.windows_native import set_brightness; set_brightness(50)"
```

Le mode `--json` retourne un objet conforme au schema documente dans `winboost chat --help`. Top-level keys : `query`, `resolved_by`, `message`, `has_actions`, `actions`, `blocked`. Exit code `0` en cas de succes, `1` si la requete est vide.

### GUI

```bash
winboost gui
```

L'interface graphique propose 5 pages :
- **Dashboard** : vue d'ensemble avec scan global
- **Modules** : scan/fix individuel par module avec preview
- **Chat IA** : assistant conversationnel avec actions intelligentes
- **Historique** : timeline de toutes les actions passees avec undo
- **Parametres** : profil, API keys, langue, modules actifs

### Chat IA

Le chat comprend les requetes en francais et anglais :

```
> desactive la telemetrie
  3 action(s) proposee(s) (via mots-cles)
  [MEDIUM] Disable DiagTrack Service
  [MEDIUM] Disable Telemetry Registry Keys
  [LOW]    Clear Telemetry Data

> optimise pour les jeux
  5 action(s) proposee(s) (via categorie)
  [LOW]    Enable Game Mode
  [MEDIUM] Disable Game DVR
  ...
```

Chaque action affiche :
- Badge de risque colore (Info/Low/Medium/High/Critical)
- Score de pertinence
- Boutons inline : Details, Simuler (dry-run), Appliquer
- Preview : methode, parametres, reversibilite, rollback

## Demo overlay

![WinBoost overlay demo](docs/assets/winboost-overlay-demo.gif)

> GIF a capturer : `winboost overlay` lance, presser Win+Espace, taper "active le mode focus", voir l'overlay s'ouvrir centre, afficher l'action proposee, et se fermer apres execution.

**Comment tester l'overlay** :

```bash
cd A:/dev/winboost
pip install -e .
winboost overlay
```

Puis presser **Win+Espace** depuis n'importe quelle app. Si rien ne se passe, relancer dans un terminal admin (le package `keyboard` requiert parfois admin sur Windows 10/11).

## Securite

WinBoost est concu pour ne jamais endommager votre systeme :

1. **Jamais de modification registre sans backup**
2. **Jamais de suppression de fichiers systeme**
3. **Confirmation obligatoire** avant toute action
4. **Mode dry-run** par defaut pour les nouveaux utilisateurs
5. **Historique complet** de toutes les actions (SQLite)
6. **Rollback disponible** via le systeme de backup
7. **Processus systeme proteges** (listes blanches)

### Niveaux de risque

- **Info** (bleu) : lecture seule
- **Low** (vert) : confirmation simple
- **Medium** (jaune) : preview + explication + confirmation
- **High** (orange) : warning + dry-run + double confirmation
- **Critical** (rouge) : bloque par defaut, mode expert requis

### Profils

| Profil | Risque max | Dry-run | Usage |
|--------|-----------|---------|-------|
| **Safe** (defaut) | Low | Obligatoire | Debutants |
| **Power User** | Medium | Non | Utilisateurs avises |
| **Expert** | High | Non | Administrateurs |

## Stack

- Python 3.12+
- CustomTkinter (GUI principale) + Tk pur (overlay hotkey)
- Click (CLI)
- psutil + wmi + ctypes + winreg (Windows APIs)
- `keyboard >= 0.13.5` (hotkey global Win+Espace)
- Anthropic API / OpenAI / Ollama (providers LLM)
- PyInstaller (.exe standalone)
- pytest + pytest-mock (TDD, 565+ tests)
- SQLite (logs, historique actions)
- YAML (registry des 180 actions)

## Build .exe

```bash
pip install -e ".[dev]"
python build.py
# -> dist/WinBoost.exe
```

## Developpement

```bash
# Installer les dependances dev
pip install -e ".[dev]"

# Lancer les tests
pytest tests/ -v

# Tests avec couverture
pytest tests/ --cov=winboost --cov-report=term-missing

# Linter
ruff check winboost/
```

## Architecture

```
winboost/
  core/         -> BaseModule (ABC), Engine, Config, Backup, History
  modules/      -> 8 modules independants
  cli/          -> Click CLI + Rich output (commandes scan, fix, chat, gui, overlay)
  gui/          -> CustomTkinter (5 pages) + hotkey_overlay.py (Tk pur)
  ai/           -> NL Parser, Action Router, Safety Engine, Cache, Providers
  actions/      -> 180 YAML action definitions (9 categories)
  utils/        -> windows_api, windows_native (helpers WMI/PowerShell), logger, admin
tests/          -> pytest, 565+ tests (1 skip Linux)
```

## Limitations connues v2.1

- **Hotkey global** : peut necessiter de lancer `winboost overlay` en admin sur certaines configs Windows (limitation du package `keyboard`)
- **Volume via SendKeys** : approche par envoi de touches virtuelles (VolumeDown/VolumeUp). Pas ideal si l'utilisateur a un controle audio externe (SoundVolumeView, AutoHotkey)
- **Mute = toggle** : `winboost chat "mute"` agit comme un toggle (re-pressing remet le son). Distinguer mute/unmute strict necessiterait `pycaw` (out of scope v2.1)
- **Brightness WMI** : peut echouer sur ecrans externes ou docks qui ne supportent pas `WmiMonitorBrightnessMethods`. Fallback documente dans `winboost.utils.windows_native.WindowsNativeError`

## Roadmap

- **v1.0** : 8 modules + CLI + GUI + .exe (Phases 1-5)
- **v2.0** : Chat IA + 150 actions + profils + onboarding (Phases 6-10)
- **v2.1** : +30 actions Windows-natives + hotkey overlay + JSON CLI (Phase 11) — actuel
- **v2.2** : MCP standalone (`winboost-mcp`) — refactor monorepo 3 packages (Phase 12)
- **v2.3** : Computer Use Pilot Mode (BYOK Anthropic, conditionnel) — Phase 13

## License

MIT

## Equipe

Projet [Genlead](https://genlead.fr) — Enzo, Antoine, Silvio + Claude Code
