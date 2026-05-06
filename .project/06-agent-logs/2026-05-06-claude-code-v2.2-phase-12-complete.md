# Phase 12 v2.2 MCP Standalone — Synthèse de fin de phase

**Agent orchestrateur** : claude-code
**Sous-agents invoqués** : 4× Backend Architect (T070, T071, T072, T073) en règle Spine n°2
**Date** : 2026-05-06
**Type** : phase synthesis / orchestration
**Statut** : code techniquement complet, **en attente de 2 actions humaines** (T074 Enzo, T075 Antoine)

---

## Contexte

Phase 12 livrée immédiatement après la phase 11 (sans validation humaine intermédiaire — choix Antoine "préfère faire les tâches humaines quand tout le code est terminé"). Le scope = exposer WinBoost en serveur MCP standalone consommable par Claude Desktop / Cursor / Code via le protocole stdio JSON-RPC.

## Décision architecturale clé : T069 en mode "refactor logique"

Le plan original (`proud-weaving-walrus.md`) prévoyait un **refactor monorepo physique** : extraction en 3 packages séparés `winboost-core` / `winboost-gui` / `winboost-mcp`. Coût estimé : ~50 fichiers déplacés, ~200 imports réécrits, 3 sous-`pyproject.toml`.

**Décision orchestrateur (validée par Antoine)** : on garde un seul package `winboost`, le MCP vit en sous-module `winboost.mcp.*`, distribution via **extras** `[mcp]`.

| Aspect | Refactor physique | Refactor logique (choisi) |
|--------|-------------------|---------------------------|
| Fichiers déplacés | ~50 | 0 (additions pures) |
| Imports réécrits | ~200 | 0 |
| `pyproject.toml` | 3 | 1 |
| Risque casser .exe GUI | Élevé | Nul |
| User MCP only | `pip install winboost-mcp` | `pip install winboost[mcp]` |
| 3 packages PyPI distincts | Oui | Non (1 package + extras) |
| Coût implémentation | ~4h | ~30 min (juste extras) |
| Réversibilité future | N/A | Refactor physique possible plus tard si besoin business |

L'esprit du plan est respecté (séparation logique), le coût est éliminé. La distribution MCP only reste possible. Le refactor physique sera réintroduit **uniquement** si on décide de publier 3 packages PyPI distincts (décision business, pas technique).

## Tâches livrées

| ID | Description | Sous-agent | Statut |
|----|-------------|-----------|--------|
| T069 | Refactor monorepo (mode logique) | claude-code (décision) | ✅ done |
| T070 | FastMCP server (5 tools) | Backend Architect | ✅ done |
| T071 | Auth token + install Claude Desktop | Backend Architect | ✅ done |
| T072 | Test compat PyInstaller-stdio | Backend Architect | ✅ done (verdict GO) |
| T073 | Tests intégration MCP | Backend Architect | ✅ done |
| T074 | Soumission registres MCP + HN | Enzo | ⏳ humaine |
| T075 | Pricing 9.99 + Stripe | Antoine | ⏳ humaine |

## Application règle Spine n°2 (audit)

Pour chaque sous-agent invoqué cette phase :

1. **Couche identité** : path Spine `engineering-backend-architect.md` fourni explicitement (vérifié présent avant invocation)
2. **Couche projet** : 6-9 fichiers WinBoost listés (CLAUDE.md, status.yaml, kickoff log v2.x, fichiers à modifier, modèles de référence, VERDICT T072 pour T071 dépendant)
3. **Couche mission** : tableau précis des livrables, contraintes non-négociables, critères de validation, format de réponse

✅ Aucun résumé du prompt Spine.
✅ Aucun log écrit côté sous-agent.
✅ Max 4 agents simultanés respecté (3 lancés en parallèle initialement, 1 en séquentiel pour T071 qui dépendait de T070).
✅ Aucun conflit de fichier entre agents (briefs précis sur les zones de modification).

## Métriques agrégées (v2.1 → v2.2)

| Indicateur | v2.1 | v2.2 | Delta |
|------------|------|------|-------|
| Tests automatisés | 610 | **682** | +72 |
| Tests skipped | 1 (Linux) | 1 (Linux) | inchangé |
| Actions registry | 180 | 180 | inchangé |
| Ruff errors | 0 | 0 | inchangé |
| Sous-modules `winboost/` | 9 | 10 (+`mcp/`) | +1 |
| Fichiers `winboost/mcp/` | 0 | 6 (server, serializers, auth, install, __init__, README) | +6 |
| CLI commands | 7 | 10 (+`mcp serve`, `mcp install/uninstall-claude-desktop`, `mcp token`) | +3 |
| Dépendances | 6 | 6 + extra `mcp` (FastMCP) | +1 extra |

## Décisions architecturales validées (post-livraison)

1. **Lazy-load FastMCP** : `import fastmcp` confiné dans `winboost/mcp/server.py`, jamais dans `__init__.py`. Test `TestImportSafety` garantit que `import winboost.mcp` reste sans-effet pour les utilisateurs hors extra MCP.
2. **Injection de dépendances** : `create_server(router=, engine=, registry=, backup_manager=, history_manager=, config=, actions_dir=)` — tous kwargs optionnels. 100% testable sans toucher à un vrai filesystem ni au registre Windows.
3. **Point d'entrée `apply` MCP** : alignement sur le comportement existant `gui/chat._execute_worker` (status="catalogued" + log via `HistoryManager`). Pas de mensonge produit : la réponse contient *"Execution systeme reelle prevue post-MCP standalone"*. Le schéma reste stable quand l'executor réel des YAML sera branché.
4. **Point d'entrée `undo` MCP** : `BackupManager.get_backup(rollback_id)` + `restore_backup(rollback_id)`. Trace via `HistoryManager` pour cohérence avec le history-viewer GUI.
5. **CLI groupe Click** : `winboost mcp` est un groupe (4 sous-commandes : serve, install-claude-desktop, uninstall-claude-desktop, token). Rétro-compat : `winboost mcp` sans sous-commande = `winboost mcp serve` (via `invoke_without_command=True`).
6. **Token MCP** : `secrets.token_urlsafe(32)` (256 bits d'entropie), persistance `%APPDATA%\WinBoost\mcp_token.txt` (Windows) / `~/.config/winboost/mcp_token.txt` (Unix), permissions 0600 best-effort.
7. **Install Claude Desktop** : backup horodaté obligatoire avant toute modification de `claude_desktop_config.json`, dry_run par défaut sur la commande CLI, force=False sécurise les ré-installs.

## Verdict T072 (PyInstaller-stdio compat)

**GO sous 3 conditions** (à respecter dans la build v2.2.x) :

1. **Reconfigurer stdin/stdout en UTF-8** au démarrage du serveur :
   ```python
   sys.stdin.reconfigure(encoding="utf-8")
   sys.stdout.reconfigure(encoding="utf-8")
   ```
   Sans cela, Windows utilise cp1252 et casse silencieusement les caractères non-ASCII.

2. **`sys.stdout.flush()` après chaque write** — `line_buffering=True` ne suffit pas à 100% sous le bootloader PyInstaller.

3. **Build en `--console` mode**, pas `--windowed`. Console est plus robuste pour stdio.

**Recommandation** (Option A préférée du verdict) : ship `winboost-mcp.exe` séparé (~5-10 Mo, FastMCP + stdio uniquement) plutôt qu'inclure le MCP dans `WinBoost.exe` (54 Mo). Cold-start ~300 ms acceptable pour un MCP server long-lived.

POC complet dans `tests/mcp_compat/` (5 fichiers + `VERDICT.md`), reproductible en ~30 secondes.

## Tests cumulés tests/test_mcp/ (72 tests)

| Fichier | Tests | Auteur |
|---------|-------|--------|
| `test_server.py` | 20 | T070 (Backend Architect) |
| `test_integration.py` | 27 | T073 (Backend Architect) |
| `test_auth.py` | 11 | T071 (Backend Architect) |
| `test_install.py` | 14 | T071 (Backend Architect) |

Coverage des 5 tools MCP : 100% (chaque tool a ≥ 4 tests entre unit + intégration).

## Actions humaines requises (phase 11 + phase 12 cumulées)

### Phase 11 (v2.1) — Antoine
1. Tester `winboost overlay` in vivo (≥3 apps)
2. Capturer `winboost-overlay-demo.gif` (cf. `docs/assets/README.md`)
3. Me dire **"Phase 11 validée"** → passage `phase_validated_by`

### Phase 12 (v2.2) — Enzo (T074)
1. Tag GitHub `v2.2.0` (à tirer après validation phase 11+12 par Antoine)
2. Soumission au registre **smithery.ai** (https://smithery.ai/submit) avec metadata MCP
3. Soumission à **anthropic.com/mcp** (registre officiel)
4. Post HackerNews : *"Show HN: WinBoost MCP — pilot Windows from Claude Desktop"* (titre indicatif)
5. Tweet/LinkedIn (à coordonner avec Antoine)

### Phase 12 (v2.2) — Antoine (T075)
1. Décision business : passage Pro **4,99 → 9,99 EUR/mois**
2. Mise à jour Stripe (nouveau prix, plan annuel 79 EUR à conserver ou ajuster)
3. Landing page WinBoost mise à jour (pricing + mention MCP)
4. Email aux Pro existants (préserver leur tarif legacy ou migrer ? décision Antoine)

## Décisions reportées (post-validation phase 11+12)

- **Tag GitHub v2.2.0** : à tirer après validation Antoine de phase 11 (overlay GIF) + commit du GIF + validation phase 12. Bloque T074.
- **Build winboost-mcp.exe séparé** : optimisation v2.2.x (cf. recommandation T072). Pas critique pour v2.2.0 initiale (`pip install winboost[mcp]` suffit).
- **Refactor monorepo physique** : reporté indéfiniment. Réintroduit seulement si décision business de publier 3 packages PyPI distincts.

## Impact projet

- `status.yaml` : 5 tâches code phase 12 → done, progress 98 → 100, current_phase 11 → 12, current_milestone v2.1 → v2.2
- `MASTER-PLAN.md` : à jour, T069 noté en mode logique (à compléter dans le commit)
- `TODO-HUMAN.md` : à enrichir avec sections E (T074 Enzo) et F (T075 Antoine)
- Aucun breaking change. v2.0 et v2.1 publiques restent intactes. Toutes les nouveautés v2.2 sont additives via `winboost.mcp.*`.

## Fichiers livrés cette phase (cumul)

```
winboost/mcp/__init__.py         (T070, 28L, lazy proxy)
winboost/mcp/server.py           (T070, 353L, FastMCP + 5 tools + run_stdio)
winboost/mcp/serializers.py      (T070, 107L, helpers depuis cli/main.py)
winboost/mcp/auth.py             (T071, 109L, token MCP local)
winboost/mcp/install.py          (T071, 240L, patch Claude Desktop config)
winboost/mcp/README.md           (T070+T071, 95L, doc dédiée + sections install/token)
winboost/cli/main.py             (T070+T071, +60L, groupe `winboost mcp` + 4 sous-commandes)
pyproject.toml                   (T070, +3L, extra `[mcp]` = fastmcp>=0.2)
tests/test_mcp/__init__.py       (T070, marqueur)
tests/test_mcp/test_server.py    (T070, 436L, 20 unit-tests)
tests/test_mcp/test_integration.py (T073, 568L, 27 workflow tests)
tests/test_mcp/test_auth.py      (T071, 11 tests token)
tests/test_mcp/test_install.py   (T071, 14 tests install)
tests/mcp_compat/__init__.py     (T072)
tests/mcp_compat/poc_mcp_server.py (T072, mini stdio server)
tests/mcp_compat/poc_client.py   (T072, client subprocess)
tests/mcp_compat/build_poc.py    (T072, build script PyInstaller)
tests/mcp_compat/VERDICT.md      (T072, verdict GO sous 3 conditions)
.project/06-agent-logs/2026-05-06-claude-code-v2.2-phase-12-complete.md (ce fichier)
```

Total : ~2200 lignes ajoutées (code + tests + docs) sur la phase 12, 0 régression.

## Récap session globale (Release v2.0 → fin code v2.2)

| Métrique | Début session (post-v2.0) | Fin session (code v2.2) | Delta |
|----------|---------------------------|------------------------|-------|
| Tests | 382 | **682** | +300 |
| Actions registry | 150 | 180 | +30 |
| Sous-modules `winboost/` | 9 | 10 | +1 (mcp/) |
| CLI commands | 6 | 10 | +4 (overlay, mcp serve, install/uninstall, token) |
| Phases techniques complètes | 10/13 (v2.0) | 12/13 (v2.2) | +2 phases |
| Commits poussés | 5 (Release + transitions + 3 batches) | 8+ (release + phase 11 + phase 12) | +3+ |
| Sous-agents Spine n°2 invoqués | 0 | 7 (3 phase 11 + 4 phase 12) | +7 |

Phase 13 (v2.3 Computer Use) reste **conditionnelle** : déclenchement seulement si v2.2 montre traction (≥500 stars GitHub, ≥100 Pro signups, ≥50 commentaires demandant Computer Use).
