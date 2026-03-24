# WinBoost — Windows AI System Assistant

## Description
Outil Python standalone Windows. Assistant systeme conversationnel.
v1 = 8 modules d'optimisation (CLI + GUI). v2 = Chat IA + Action Registry.

## Equipe
- Enzo : CEO, decisions strategiques, validation
- Antoine : Dev, gestion projets, execution technique
- Silvio : Dev, developpement, GitHub silvio-dadderio
- Claude Code : Agent IA principal, 95% de l'execution

## Stack
- Python 3.12+
- CustomTkinter (GUI)
- Click (CLI)
- psutil + wmi + ctypes + winreg (Windows APIs)
- Anthropic API / OpenAI / Ollama (LLM v2)
- PyInstaller (.exe standalone)
- pytest + pytest-mock (TDD)
- SQLite (logs, historique actions)
- JSON (config locale)

## Architecture
```
winboost/
  core/         -> base_module, engine, config, backup, history
  modules/      -> 8 modules independants (temp, startup, ram, disk, privacy, dev, service, sysinfo)
  ai/           -> nl_parser, action_router, safety_engine, providers/, cache
  actions/      -> YAML action definitions (150+ actions, classees par categorie)
  cli/          -> Click CLI
  gui/          -> CustomTkinter GUI + chat widget
  utils/        -> windows_api, logger, admin
tests/          -> pytest, miroir de winboost/
```

## Conventions
- Commits : feat:, fix:, chore:, refactor:, docs:
- Code : anglais
- Docs et commentaires : francais
- Tests : pytest, TDD, couverture 80%+
- Chaque module implemente BaseModule (ABC)
- Chaque action est un fichier YAML dans actions/{categorie}/

## Regles de securite
1. Jamais de modification registre sans backup automatique
2. Jamais de suppression fichier systeme
3. Point de restauration avant actions high/critical
4. Mode dry-run par defaut pour nouveaux utilisateurs
5. Historique complet SQLite local
6. Undo toujours disponible
7. L'IA ne peut JAMAIS agir sans confirmation utilisateur

## Safety Levels
- info (bleu) : lecture seule
- low (vert) : confirmation simple
- medium (jaune) : preview + explication + confirmation
- high (orange) : warning + dry-run obligatoire + double confirm
- critical (rouge) : bloque par defaut, mode expert requis

## Profils utilisateur
- safe : max_risk=low, dry_run_first=true (defaut)
- power_user : max_risk=medium
- expert : max_risk=high

## Phases
- v1.0 : Phases 1-5 (8 modules + CLI + GUI + build .exe)
- v2.0 : Phases 6-10 (Action Registry + AI Engine + Chat GUI)

## Commandes
- `winboost scan` : scanner tous les modules
- `winboost scan --module temp` : scanner un module specifique
- `winboost fix --module temp` : appliquer les corrections
- `winboost info` : infos systeme
- `winboost chat "requete"` : chat IA (v2)
- `winboost gui` : lancer la GUI
