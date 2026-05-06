# Phase 11 v2.1 — Batch network + appearance (T063 finalisation)

**Agent orchestrateur** : claude-code
**Sous-agents invoqués** : 2× Backend Architect (en parallèle, règle Spine n°2)
**Date** : 2026-05-06
**Type** : feature implementation
**Issue référence** : T063 (30 actions YAML Windows-natives)

---

## Contexte

Première moitié de T063 livrée précédemment (10 actions system : sys_011→sys_020). Ce batch finalise les 20 actions restantes via 2 sous-agents en parallèle, déclenchés selon la règle Spine n°2 (triangle de contexte identité+projet+mission).

**Demande Antoine** : "applique la règle 2 du Spine pour lancer des agents sur les tâches".

## Triangle de contexte appliqué (règle Spine n°2)

Pour chaque sous-agent invoqué :

1. **Couche identité (Spine)** : prompt source `~/.claude/agents/engineering-backend-architect.md` (path résolu via `agents-index.yaml`, fichier vérifié présent avant invocation)
2. **Couche projet** : 6 fichiers WinBoost listés explicitement dans le prompt
   - `CLAUDE.md` (conventions stack/sécurité)
   - `status.yaml` (état phase 11 in_progress)
   - `06-agent-logs/2026-05-06-claude-code-phase-11-kickoff.md` (brief de phase)
   - `actions/schema.py` (validation schema)
   - `actions/system/actions.yaml` (modèle exact pour le format des nouvelles actions, sys_011→sys_020 servant de référence)
   - le fichier YAML cible à étendre
3. **Couche mission** : tableau précis des 10 actions à créer (id, nom, effet, méthode), règles non-négociables (champs obligatoires, méthodes valides, risk levels, admin, reversible), critères de validation (yaml.safe_load, dédup, count), format de réponse attendu

Aucun sous-agent ne s'est vu fournir de résumé du prompt Spine — chacun a reçu le path à lire (respect strict de la règle "ne JAMAIS résumer le prompt Spine"). Pas de log écrit côté sous-agent (règle d'orchestration : c'est l'orchestrateur qui consolide).

## Résultats

### Network — 10 actions (net_011 → net_020)

| id | name | risk | admin |
|----|------|------|-------|
| net_011 | Disable Bluetooth | low | true |
| net_012 | Enable Bluetooth | low | true |
| net_013 | Disconnect Wi-Fi | low | false |
| net_014 | Flush DNS Cache (Native) | info | false |
| net_015 | Set DNS Cloudflare (1.1.1.1) | low | false |
| net_016 | Reset DNS to Auto (DHCP) | low | false |
| net_017 | Reset Winsock (Repair) | medium | true |
| net_018 | Disable IPv6 (Registry) | medium | true |
| net_019 | Enable IPv6 (Registry) | medium | true |
| net_020 | Disable Network Discovery (Firewall) | low | true |

### Appearance — 10 actions (app_011 → app_020)

| id | name | risk | admin |
|----|------|------|-------|
| app_011 | Mute System Volume | low | false |
| app_012 | Unmute System Volume | low | false |
| app_013 | Volume Set Low (20%) | low | false |
| app_014 | Volume Set Medium (50%) | low | false |
| app_015 | Volume Set High (80%) | low | false |
| app_016 | Disable System Sounds | low | false |
| app_017 | Enable System Sounds (Default) | low | false |
| app_018 | Disable Animations | low | false |
| app_019 | Enable Animations | low | false |
| app_020 | Disable Transparency Effects | low | false |

### Tests ajoutés (T067 finalisation)

Extension de `tests/test_actions/test_native_actions.py` avec 2 nouvelles classes :
- `TestNetworkV21` : 6 tests structurels + 2 tests métier (winsock non-reversible, IPv6 disabled_components, DNS Cloudflare)
- `TestAppearanceV21` : 6 tests structurels + 2 tests métier (mute keywords, transparency registry)
- `TestV21Totals` : 1 test global (30 actions v2.1 cumulées)

Mise à jour des compteurs globaux (4 tests) :
- `test_load_180_actions` (était 160 puis 150)
- `test_category_counts` : network 20, appearance 20, system 20
- `test_action_count` (router) : 180

## Métriques

| Avant batch | Après batch |
|-------------|-------------|
| 466 tests | 565 tests (+99) |
| 160 actions | 180 actions (+20) |
| 0 ruff error | 0 ruff error |

## Décisions et points de vigilance signalés par les sous-agents

### Doublons fonctionnels (network)

Le sous-agent network a signalé que **4 nouvelles actions chevauchent fonctionnellement des actions v2.0 existantes** :
- net_001 (Flush DNS) ↔ net_014 (Flush DNS Native)
- net_002 (Reset Winsock) ↔ net_017 (Reset Winsock Repair)
- net_004 (Disable IPv6) ↔ net_018 (Disable IPv6 Registry)
- net_010 (Network Discovery) ↔ net_020 (Disable Network Discovery Firewall)

**Pas de conflit d'id** (les ids restent uniques), mais doublon de comportement. Différences :
- Format YAML : ancien plat (`name/value/type`) vs nouveau structuré (`values: [{name,type,data}]`)
- Keywords distincts : permet au NL parser de router différemment selon la formulation utilisateur (ex: "vide DNS" vs "flush dns")
- Risk levels parfois différents

**Décision** : on garde les deux pour v2.1. À consolider plus tard si Antoine signale de la confusion utilisateur. Tâche potentielle T082 (post-v2.1) : *"Audit doublons fonctionnels du registry, fusion YAML legacy → format v2.1"*. Pas urgent.

### Approximations techniques acceptées (appearance)

- **app_011/012 (mute/unmute)** : touche `[char]173` est strictement un toggle ; impossible de garantir l'état final sans wrapper natif `audioendpointvolume.SetMute()`. Limitation documentée dans la `description` de app_012.
- **app_013-015 (volume)** : approche SendKeys (full down + N up) — la baseline n'est pas garantie si l'utilisateur a des contrôles externes (ex: SoundVolumeView, AutoHotkey). Acceptable pour v2.1 sans dépendance externe (`pycaw`, `nircmd`). À durcir en v2.2 si plaintes utilisateur.
- **app_016/017 (system sounds)** : la valeur registry `(Default)` est interprétée comme la valeur par défaut sans nom (convention Windows). Dépend de `winboost/actions/executor.py` pour gérer cette convention au moment de l'exécution réelle (v2.1+).

### Décision de format (appearance)

- **app_018/019 (animations)** : nécessitent 2 paths registry distincts (`WindowMetrics` + `VisualEffects`). Le sous-agent a légitimement choisi `method: powershell` au lieu de `registry_set` (limité à 1 path par action). Cohérent avec le pattern PS des sys_013-015.

## Actions suivantes (phase 11 reste)

| ID | Tâche | Estimé | Priorité |
|----|-------|--------|----------|
| T065 | Hotkey global Win+Espace + overlay texte | ~3 h | high (wow factor démo) |
| T066 | Mode JSON CLI (`winboost chat --json`) | ~30 min | medium |
| T068 | README + démo GIF de l'overlay | ~1 h | low (post-T065) |

T065 nécessite tests in-vivo (multiple apps) + GIF de démo → idéalement dans une session où Antoine peut valider visuellement.
T066 est un chantier court et indépendant → peut être traité en autonomie dans la prochaine session.

## Impact projet

- `status.yaml` : T063 → done (30/30 actions livrées), T067 → done (les nouveaux tests couvrent les 30 actions)
- `MASTER-PLAN.md` : à jour, pas de modification de plan
- Pas de breaking change. La v2.0 (la Release publique) reste intacte. Tout est additif.

## Validation

- `python -m pytest tests/` : 565 passed, 1 skipped (Linux only)
- `python -m ruff check .` : All checks passed
- 0 doublon d'id (vérifié à 3 niveaux : `grep|uniq -d`, validation schema, fixtures pytest)
- Schema validation : 180/180 actions valides
