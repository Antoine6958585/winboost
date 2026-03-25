# WinBoost

**Le premier assistant Windows qui ne te ment pas.**

WinBoost est un assistant systeme Windows conversationnel. Il scanne, analyse et corrige les problemes courants via 8 modules d'optimisation et un chat IA intelligent avec 150+ actions.

## Features

### v1.0 — Modules + CLI + GUI
- **8 modules d'optimisation** independants
- **CLI complete** avec Rich (couleurs, tableaux)
- **GUI CustomTkinter** avec dark theme
- **Backup automatique** avant chaque action + rollback
- **Historique SQLite** de toutes les actions

### v2.0 — AI Engine + Chat
- **Chat IA conversationnel** avec ActionRouter + cache keyword (70% resolu localement)
- **150+ actions YAML** reparties en 9 categories
- **3 profils de securite** : Safe, Power User, Expert
- **Onboarding premier lancement** (choix profil + config API)
- **History viewer** avec timeline, filtres et undo
- **Settings complet** (profil, API keys, langue, modules)
- **Providers LLM** : Anthropic (Claude), OpenAI (GPT), Ollama (local)

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
  cli/          -> Click CLI + Rich output
  gui/          -> CustomTkinter (5 pages: dashboard, modules, chat, history, settings)
  ai/           -> NL Parser, Action Router, Safety Engine, Cache, Providers
  actions/      -> 150+ YAML action definitions (9 categories)
tests/          -> pytest, 293+ tests
```

## Roadmap

- **v1.0** : 8 modules + CLI + GUI + .exe (Phases 1-5)
- **v2.0** : Chat IA + 150 actions + profils + onboarding (Phases 6-10) — actuel

## Licence

MIT

## Equipe

Projet [Genlead](https://genlead.fr) — Enzo, Antoine, Silvio + Claude Code
