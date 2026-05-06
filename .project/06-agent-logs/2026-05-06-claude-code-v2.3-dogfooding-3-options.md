# Phase 13 v2.3 — Dogfooding 3 options en parallèle (A + B + C)

**Agent orchestrateur** : claude-code
**Sous-agents invoqués** : 3 en parallèle (règle Spine n°2)
**Date** : 2026-05-06
**Type** : phase synthesis / accélération produit

---

## Contexte — décision dogfooding

Antoine a explicitement validé la pré-implémentation de la v2.3 sans attendre la traction (≥500 stars + ≥100 Pro signups). Justification (sa parole) :

> "je suis le premier utilisateur de ce produit si moi ca regle mes probleme perso ce sera pareil pour les utilisateur futurs"

Use case déclencheur concret : sa manette Bluetooth bug en jeu (Rocket League). WinBoost v2.2 propose `net_011 Disable Bluetooth` mais ne l'**exécute pas vraiment** (catalogage). Il veut que ça résolve le problème pour de vrai.

## 3 options livrées en parallèle (~3500 lignes total + 240 nouveaux tests)

| Option | Description | Agent | Effort | Statut |
|--------|-------------|-------|--------|--------|
| **A** | Brancher l'executor RÉEL des actions YAML (registry/service/PS/cmd/FS) | Backend Architect | ~6-8h dev | ✅ done |
| **B** | Computer Use Pilot Mode (Anthropic, BYOK, RGPD opt-in) | Backend Architect | ~10h dev | ✅ done (backend, GUI T081 reste) |
| **C** | Module `diagnose` rules-based (5 thèmes) | Senior Developer | ~3-4h dev | ✅ done |

## Application règle Spine n°2 (audit)

Pour chaque sous-agent invoqué :
1. **Couche identité** : path Spine `engineering-backend-architect.md` (ou `engineering-senior-developer.md` pour C) fourni explicitement
2. **Couche projet** : 7-13 fichiers WinBoost listés (CLAUDE.md, status.yaml, kickoff log, fichiers à modifier, modèles de référence, contexte business — manette Antoine)
3. **Couche mission** : architecture cible, contraintes non-négociables, tests obligatoires (≥ 20-30), zones de modification précises pour éviter conflits

✅ Aucun résumé du prompt Spine.
✅ Aucun log écrit côté sous-agent.
✅ 3 agents simultanés (max 4 respecté).
✅ **Aucun conflit fichier** : briefs précisaient les zones (A touche core/+gui/chat+mcp/server, B isolé dans pilot/, C isolé dans diagnose/, AUCUN ne touche cli/main.py — orchestrateur consolide).

## Détails Option A — Executor réel YAML actions

### Architecture livrée
```
winboost/core/executor.py (1100L)
├── ActionExecutor.apply(action) -> ApplyResult
├── 10 méthodes : registry_set, registry_delete, service_*, powershell, cmd, delete_path, clear_directory, scheduled_task_disable
├── Whitelist FS stricte (TEMP, LOCALAPPDATA\Temp, caches dev, Windows\Temp, Windows\Logs, Minidump)
├── Blacklist registry (HKLM\SYSTEM\Setup, ControlSet*\Control\Lsa, BCD00000000, SAM, SECURITY)
├── Scan command pattern destructeur (format X:, Remove-Item C:\, diskpart clean, etc.)
├── Backup auto registry sur high/critical (reg.exe export)
├── Idempotence registry_set (lit valeur courante avant écriture)
├── Timeout 30s configurable
├── Dry-run mode
└── HistoryManager logging unifié

winboost/gui/chat.py — _execute_worker rebranché : plus de "catalogué", apply réel
winboost/mcp/server.py — tool apply réel avec ApplyResult sérialisé
```

### Sample d'usage
```bash
# AVANT T082 (v2.2)
$ winboost chat --json "active dark mode"
{ "actions": [{"id": "sys_011", ...}] }
# clic "Apply" -> "Action enregistrée dans le catalogue (exécution réelle prévue v2.1.x)"

# APRÈS T082 (v2.3)
$ winboost chat --json "active dark mode"
{ "actions": [{"id": "sys_011", ...}] }
# clic "Apply" -> "Action exécutée — registry HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Themes\Personalize mis à jour (2 valeur(s))"
# ré-apply -> "Déjà appliqué — registry à la valeur cible." (idempotence)
```

### Limitations honnêtes (signalées par l'agent)
- `service_*` et `scheduled_task_disable` non testables sans admin en CI (tests mockés)
- `_backup_before` registry peut échouer silencieusement si la clé n'existe pas (rollback_id=None mais action continue)
- GUI `_execute_worker` ne crée pas de `BackupManager` par défaut (3 lignes à ajouter si besoin)

## Détails Option B — Computer Use Pilot Mode

### Architecture livrée
```
winboost/pilot/
├── anthropic_pilot.py (924L) — orchestrateur Computer Use loop
├── sandbox.py (197L) — zones d'écran configurables + safety
├── confirmation_ui.py (297L) — preview annoté (rectangle rouge)
├── budget.py (315L) — plafond mensuel 5 EUR default + tracking USD/EUR
├── README.md — doc complète + RGPD + scenario manette canonique
└── pyproject.toml extra `[pilot]` = anthropic + Pillow + pyautogui

Tests : 65 (BYOK absent / profil pas Lab / RGPD pas accepté / plafond atteint / 6e action consécutive sans confirm / Esc cancel / sandbox limite / audit trail / coût tokens / sérialisation config / reset mensuel)
```

### Pré-requis utilisateur
1. **Profil Lab** dans la config (séparation stricte du Pro)
2. **RGPD opt-in granulaire** : screenshots, OCR text, system info — chacun un toggle
3. **Clé API Anthropic** via env `ANTHROPIC_API_KEY` ou `--api-key` (BYOK obligatoire, **pas de fallback gratuit**)
4. **Plafond mensuel** default 5 EUR (~30-50 actions Computer Use)

### Limitations honnêtes
- **GUI Settings T081 reste à faire** : screenshot_provider + action_executor + opt-in UI sont injectables, à brancher en GUI
- **SDK Anthropic Computer Use en public beta** : `client_factory` injectable permet de patcher si l'API change
- **Pas de chiffrement local des screenshots** (à documenter dans RGPD UI)
- **Pricing tables hardcoded 2026-01** : USD=EUR pessimiste pour ne jamais sous-estimer

## Détails Option C — Module diagnose rules-based

### Architecture livrée
```
winboost/diagnose/
├── runner.py (472L) — DiagnosticRunner.run_from_query, multi-thèmes auto-detect, ThreadPoolExecutor
├── checks.py (291L) — Check base + helpers safe_run(), severity StrEnum
├── themes/
│   ├── bluetooth.py (403L) — service bthserv, drivers BT, devices appairés, conflits XInput
│   ├── gaming.py (338L) — gamepads, drivers Xbox, Steam Input, dual-input conflicts, XblGameSave
│   ├── network.py (289L) — adapter, DNS resolution, gateway, Dnscache
│   ├── audio.py (317L) — Audiosrv, default devices, drivers
│   └── display.py (314L) — brightness WMI, multi-écrans, GPU drivers, HDR
└── README.md

Tests : 110 (matching, fix plan, summary, exceptions, sérialisation, validation, par thème)
```

### Test live en session — query Antoine
```
$ winboost diagnose --json "ma manette bluetooth bug dans rocket league"
{
  "theme": "bluetooth+gaming",
  "checks": [10],
  "summary": "9 warning(s) detecte(s) : ...",
  "recommended_fix_plan": [
    {"step": 1, "action_id": "net_012", "description": "Redémarrer le service Bluetooth"},
    {"step": 2, "manual": True, "description": "Mettre à jour driver Xbox via Windows Update Optional"},
    {"step": 3, "action_id": "net_011", "description": "Toggle BT off/on (si manette toujours pas détectée)"}
  ]
}
```

Match parfait : NL parser identifie `bluetooth + gaming`, lance les checks par thème, propose un plan ordonné mêlant actions YAML (T082 les exécutera vraiment) + étapes manuelles.

## Consolidation orchestrateur (claude-code)

### CLI commands ajoutées
- `winboost diagnose <query>` (avec `--json`) — appelle DiagnosticRunner, sortie Rich ou JSON
- `winboost pilot <query>` (avec `--api-key`, `--budget-eur`) — vérifie profil Lab + RGPD + BYOK, message clair pour la GUI Settings T081

### Tests fixés
- `test_cli/test_main.py::test_version` : 2.0.0 → 2.2.0
- `test_e2e/test_cli_e2e.py::test_version` : 2.0.0 → 2.2.0

## Métriques agrégées (v2.2 → v2.3)

| Indicateur | v2.2 | v2.3 | Delta |
|------------|------|------|-------|
| Tests automatisés | 682 | **922** | +240 |
| Lignes Python (winboost/) | ~5500 | ~10500 | +5000 |
| CLI commands | 10 | **12** (+diagnose, +pilot) | +2 |
| Sous-modules `winboost/` | 10 | **12** (+diagnose, +pilot) | +2 |
| Méthodes d'exécution YAML branchées | 0 | **10** | +10 |
| Thèmes diagnostic | 0 | **5** (BT, gaming, network, audio, display) | +5 |
| Ruff errors | 0 | 0 | inchangé |

## Ce qui reste — actions humaines + polish

### Actions humaines (inchangées)
- T074 (Enzo) : registres MCP + post HN
- T075 (Antoine) : pricing 9.99 EUR + Stripe + landing + email Pro
- T080 (Antoine) : notice RGPD + opt-in UI granulaire pour Pilot
- T081 : intégration GUI Settings du Pilot Mode (Tier Lab + screenshot_provider Tk + action_executor pyautogui)

### Polish technique optionnel
- Fix UnicodeDecodeError cp1252 dans certains checks (stderr PowerShell binaire)
- Build `winboost-mcp.exe` séparé (5-10 Mo, recommandation T072)
- Volume via `pycaw` (mute strict)
- Brightness fallback DDC/CI (écrans externes)

## Tag GitHub à venir

Une fois tous les tests humains validés (Antoine pour la manette via diagnose, GUI Pilot T081), on tirera **v2.3.0** avec asset `WinBoost.exe` rebuildé.

## Décisions actées dans cette session

1. **Refactor monorepo physique reporté indéfiniment** (déjà acté en T069 v2.2). v2.3 reste mono-package + extras.
2. **Pas de Refactor `winboost-mcp.exe` séparé maintenant** (recommandation T072). Reporté en v2.3.x si Enzo signale un problème de taille (62 Mo) au moment du post HN.
3. **Computer Use accéléré sans attendre traction** — décision dogfooding Antoine 2026-05-06.
4. **Pricing Pro 9.99 EUR confirmé** (cf. plan v2.x), à implémenter par Antoine T075.
