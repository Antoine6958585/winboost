# WinBoost

**Le premier assistant Windows qui ne te ment pas.**

WinBoost est un outil Python standalone d'optimisation systeme pour Windows. Il scanne, analyse et corrige les problemes courants — fichiers temporaires, programmes au demarrage, RAM, espace disque, vie privee, caches dev et services Windows.

## Features

- **8 modules d'optimisation** independants
- **CLI complete** avec Rich (couleurs, tableaux)
- **GUI CustomTkinter** avec dark theme
- **Systeme de securite** : 5 niveaux de risque, confirmation obligatoire, dry-run
- **Backup automatique** avant chaque action + rollback
- **Historique SQLite** de toutes les actions
- **3 profils utilisateur** : Safe, Power User, Expert

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

# Lister les modules
winboost modules

# Lancer la GUI
winboost gui
```

### GUI

```bash
winboost gui
```

L'interface graphique propose :
- **Dashboard** : vue d'ensemble avec scan global
- **Modules** : scan/fix individuel par module avec preview
- **Chat IA** : placeholder pour v2 (assistant conversationnel)

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
- **Critical** (rouge) : bloque par defaut

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
  gui/          -> CustomTkinter (dashboard, modules, chat)
  ai/           -> [v2] NL Parser, Action Router, Safety Engine
  actions/      -> [v2] YAML action definitions
tests/          -> pytest, 149+ tests
```

## Roadmap

- **v1.0** : 8 modules + CLI + GUI + .exe (actuel)
- **v2.0** : Chat IA conversationnel + 150 actions YAML + providers LLM

## Licence

MIT

## Equipe

Projet [Genlead](https://genlead.fr) — Enzo, Antoine, Silvio + Claude Code
