# WinBoost — Roadmap

## Vision
Le premier assistant Windows qui ne te ment pas.
v1 = 8 modules d'optimisation. v2 = Chat IA conversationnel.

---

## Milestone v1.0 — Modules + CLI + GUI

### Phase 1 : Foundation (4-6h agent) ✅
- [x] Core : base_module (ABC), engine, config
- [x] Modules : temp_cleaner, system_info
- [x] CLI Click
- [x] Tests unitaires (60 tests, 84% couverture)
- **Livrable** : `winboost scan --module temp`

### Phase 2 : Modules critiques (4-6h agent) ✅
- [x] startup_manager
- [x] ram_optimizer
- [x] disk_analyzer
- [x] Tests par module (102 tests, 80% couverture)
- **Livrable** : 5 modules CLI

### Phase 3 : GUI (4-5h agent) ✅
- [x] CustomTkinter dashboard + dark theme
- [x] Vue par module avec cards (scan/fix individuels)
- [x] Chat placeholder (UI prete, v2)
- **Livrable** : App GUI fonctionnelle (`winboost gui`)

### Phase 4 : Modules avances + Backup (4-5h agent) ✅
- [x] privacy_cleaner, dev_cache_cleaner, service_optimizer
- [x] Systeme backup/undo + SQLite history
- [x] Tests (149 total, 81% couverture hors GUI)
- **Livrable** : 8 modules + backup

### Phase 5 : Release v1.0 (2-3h agent) ✅
- [x] Build PyInstaller .exe (spec + build.py)
- [x] Icone + splash screen
- [x] README.md complet
- [x] Tests E2E (172 tests total)
- [ ] GitHub Release v1.0.0 (antoine)
- [x] Repo reste prive (decision enzo)
- **Livrable** : v1.0.0 sur GitHub

---

## Milestone v2.0 — AI Engine + Chat

### Phase 6 : Action Registry (5-7h agent) ✅
- [x] Format YAML + schema validation + loader dynamique
- [x] 150 actions (privacy 30, performance 30, cleanup 20, dev_tools 20, network 10, security 10, appearance 10, gaming 10, system 10)
- [x] Tests (204 total, 0 erreurs validation)
- **Livrable** : 150 actions testables en dry-run

### Phase 7 : AI Engine (6-8h agent) ✅
- [x] NL Parser (requete -> intent structure)
- [x] Action Router (intent -> actions filtrees)
- [x] Safety Engine (risk filtering par profil)
- [x] Keyword Cache (resolution locale sans LLM, ~70%)
- [x] Providers (Anthropic, OpenAI, Ollama)
- [x] CLI chat + 27 tests AI (231 total)
- **Livrable** : `winboost chat "nettoie mes temp"` en CLI

### Phase 8 : Chat GUI (4-5h agent) ✅
- [x] Widget conversationnel integre (ChatPage + ChatBubble + TypingIndicator)
- [x] Indicateurs de risque + boutons inline (ActionCard + badges couleur)
- [x] Preview before/after (PreviewPanel + ConfirmDialog)
- [x] Integration chat -> engine -> modules (ActionRouter + History logging)
- [x] Tests GUI chat (30 tests, 261 total)
- **Livrable** : Chat IA dans la GUI

### Phase 9 : Profils + Onboarding (3-4h agent) ✅
- [x] Profils Safe/Power/Expert (ProfileCard + switch + persistence)
- [x] Onboarding first-launch (3 etapes: bienvenue + profil + API)
- [x] History viewer (HistoryPage + filtres + timeline + details)
- [x] Undo manager avance (backup/restore + logging)
- [x] Settings UI (profil, API keys, langue, modules)
- [x] Tests (32 tests, 293 total)
- **Livrable** : Experience complete

### Phase 10 : Release v2.0 (2-3h agent) ✅
- [x] Build PyInstaller v2 (hidden imports + YAML data files)
- [x] README v2 complet (features, profils, chat, architecture)
- [x] Tests E2E complets (27 tests v2 + 320 total)
- [ ] GitHub Release v2.0.0 (antoine)
- [ ] Product Hunt draft (enzo)
- **Livrable** : v2.0.0 sur GitHub

---

---

## Milestone v2.x — "Claude pilote ton PC" (validee 2026-05-06)

### Phase 11 : Native Windows Actions (12-15h agent) — apres ship v2.0
- [ ] T063 : +30 actions YAML Windows-natives (luminosite WMI, dark mode, volume, BT, focus, wifi, HDR, night mode, sound device, power plan)
- [ ] T064 : Module `winboost/utils/windows_native.py` (helpers WMI/PowerShell)
- [ ] T065 : Hotkey global Win+Espace -> overlay texte (package `keyboard`)
- [ ] T066 : Mode JSON CLI (`winboost chat --json`)
- [ ] T067 : 30+ tests pour les nouvelles actions (unit + dry-run)
- [ ] T068 : README + demo GIF de l'overlay
- **Livrable** : actions natives qui repondent litteralement a la demande Antoine (luminosite etc.)

### Phase 12 : MCP Standalone (10-14h agent)
- [ ] T069 : Refactor monorepo 3 packages (winboost-core / winboost-gui / winboost-mcp)
- [ ] T070 : Implementation FastMCP (5 tools : chat, scan, apply, list_actions, undo)
- [ ] T071 : Auth token local + commande `winboost-mcp install-claude-desktop`
- [ ] T072 : Test compatibilite PyInstaller-stdio (risque #1 du challenge)
- [ ] T073 : 25+ tests d'integration MCP (mock client)
- [ ] T074 : Soumission registres MCP (smithery.ai + anthropic.com/mcp) + post HackerNews
- [ ] T075 : Pricing : passage Pro 4.99 EUR -> 9.99 EUR/mois (decision validee)
- **Livrable** : `pip install winboost-mcp` + Claude Desktop pilote WinBoost

### Phase 13 (CONDITIONNELLE) : Computer Use Pilot Mode (20-26h agent)
**Declenchement** : >= 500 stars GitHub + >= 100 Pro signups + demande explicite users
- [ ] T076 : Module `winboost/pilot/anthropic_pilot.py` (Anthropic computer_use_xxxxxxxx tool)
- [ ] T077 : Sandbox + zone d'ecran configurable
- [ ] T078 : Confirmation visuelle obligatoire (preview screenshot annote)
- [ ] T079 : BYOK Anthropic obligatoire + plafond mensuel parametrable
- [ ] T080 : Notice RGPD + opt-in granulaire (CNIL compliant)
- [ ] T081 : Tier "Lab" + integration GUI Settings
- **Livrable** : actions hors registry (navigation UI, apps tierces) avec garde-fous

---

## Post-v2.3 (long terme)
- Plugin marketplace (actions tierces)
- Multi-langue UI (DE, ES, PT)
- Scheduled actions
- v3.0 : Remote monitoring multi-PC, extension navigateur, mobile companion

---

## Totaux
- 10 phases livrees + 2 prevues + 1 conditionnelle = 13 phases potentielles
- 62 taches livrees + 19 prevues (phases 11-13) = 81 taches potentielles
- Agent v1.0 + v2.0 : 34-47h (DONE)
- Agent v2.1 + v2.2 : 22-29h (apres ship v2.0)
- Agent v2.3 (conditionnel) : 20-26h
- v1.0 : Phases 1-5 (~18-25h agent)
- v2.0 : Phases 6-10 (~20-27h agent)
- v2.1 : Phase 11 (~12-15h agent)
- v2.2 : Phase 12 (~10-14h agent)
- v2.3 : Phase 13 (~20-26h agent, conditionnel)
