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

### Phase 7 : AI Engine (6-8h agent)
- [ ] NL Parser (LLM -> intent)
- [ ] Action Router (intent -> actions)
- [ ] Safety Engine (risk filtering)
- [ ] Providers (Anthropic, OpenAI, Ollama)
- **Livrable** : `winboost chat "nettoie mes temp"` en CLI

### Phase 8 : Chat GUI (4-5h agent)
- [ ] Widget conversationnel integre
- [ ] Indicateurs de risque + boutons inline
- [ ] Preview before/after
- **Livrable** : Chat IA dans la GUI

### Phase 9 : Profils + Onboarding (3-4h agent)
- [ ] Profils Safe/Power/Expert
- [ ] Onboarding first-launch
- [ ] History viewer + undo manager
- **Livrable** : Experience complete

### Phase 10 : Release v2.0 (2-3h agent)
- [ ] Build .exe v2 + README + tests E2E
- **Livrable** : v2.0.0 sur GitHub

---

## Post-v2.0
- v2.1 : Plugin marketplace
- v2.2 : Multi-langue (DE, ES, PT)
- v2.3 : Scheduled actions
- v3.0 : Remote monitoring multi-PC, extension navigateur, mobile companion

---

## Totaux
- 10 phases, 62 taches
- Agent : 34-47h | Humain : 12-15h
- v1.0 : Phases 1-5 (~18-25h agent)
- v2.0 : Phases 6-10 (~20-27h agent)
