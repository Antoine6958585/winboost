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

### Phase 2 : Modules critiques (4-6h agent)
- [ ] startup_manager
- [ ] ram_optimizer
- [ ] disk_analyzer
- [ ] Tests par module
- **Livrable** : 5 modules CLI

### Phase 3 : GUI (4-5h agent)
- [ ] CustomTkinter dashboard + dark theme
- [ ] Vue par module avec cards
- [ ] Chat placeholder
- **Livrable** : App GUI fonctionnelle

### Phase 4 : Modules avances + Backup (4-5h agent)
- [ ] privacy_cleaner, dev_cache_cleaner, service_optimizer
- [ ] Systeme backup/undo + SQLite history
- **Livrable** : 8 modules + backup

### Phase 5 : Release v1.0 (2-3h agent)
- [ ] Build PyInstaller .exe
- [ ] README, branding, tests E2E
- **Livrable** : v1.0.0 sur GitHub

---

## Milestone v2.0 — AI Engine + Chat

### Phase 6 : Action Registry (5-7h agent)
- [ ] Format YAML + schema validation
- [ ] 150 actions (privacy, performance, cleanup, dev_tools, network, security, etc.)
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
