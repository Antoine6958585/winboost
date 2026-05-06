# Pre-Release Smoke Test — WinBoost v1.0.0 + v2.0.0

> Prompt à coller dans une session Claude Code dédiée pour valider le code
> AVANT que Antoine tire les GitHub Releases (T029 + T061).
> Agent recommandé : **Reality Checker** (par défaut "NEEDS WORK", evidence-based).

---

## Identité Spine

Lis d'abord et applique comme ton system context :

**Agent recommandé** : `Reality Checker`
→ subagent_type natif Claude Code, "Stops fantasy approvals, evidence-based certification - Default to NEEDS WORK, requires overwhelming proof for production readiness"

Si Reality Checker n'est pas adapté, fallback sur `Evidence Collector` (screenshot-obsessed, fantasy-allergic QA specialist).

## Contexte projet

Lis ces fichiers avant tout, dans cet ordre :

1. `A:/dev/winboost/CLAUDE.md` — règles produit (notamment les 7 règles de sécurité)
2. `A:/dev/winboost/status.yaml` — état actuel : 96 %, phase 10, T029/T061/T062 not_started
3. `A:/dev/winboost/.project/MASTER-PLAN.md` — décisions, risques connus
4. `A:/dev/winboost/.project/03-specs/architecture.md` — architecture technique
5. `A:/dev/winboost/.project/04-quality/checklist.md` — checklist qualité existante
6. `A:/dev/winboost/.project/06-agent-logs/2026-05-06-claude-code-synthese-retroactive-phases-1-10.md` — récap de ce qui a été livré

**Ne pas modifier de code.** Ce smoke test est en lecture/exécution seule. Si tu trouves un bug,
tu le **rapportes** ; tu ne le corriges pas dans cette session (ce sera une session séparée).

## Mission

Valider que **WinBoost v1 et v2 sont prêts à être releasés publiquement** sur GitHub
(`Antoine6958585/winboost`, repo qui passera public au moment du tag v2.0.0).

### Scope automatisable (TOI, claude-code)

| # | Test | Critère de réussite |
|---|------|---------------------|
| 1 | `python -m pip install -e .` dans un venv frais | Install OK, 0 erreur |
| 2 | `python -m pytest tests/ -q --tb=short` | **320 tests passent**, 0 fail, 0 error |
| 3 | `python -m pytest tests/ --cov=winboost --cov-report=term-missing` | **Couverture ≥ 80 %** sur core + modules + ai |
| 4 | `python -m winboost --help` | Liste : scan, fix, info, chat, gui, settings |
| 5 | `python -m winboost info` | Affiche specs Windows sans crash |
| 6 | `python -m winboost scan --module temp` (dry-run) | Liste fichiers, ne supprime rien |
| 7 | `python -m winboost scan --module ram` (dry-run) | Idem |
| 8 | `python -m winboost scan --module disk` (dry-run) | Idem |
| 9 | Boucle sur les 150 actions YAML : chaque `--dry-run` ne crash pas | 150 / 150 OK |
| 10 | Validation schema YAML : tous les fichiers `actions/**/*.yaml` valides | 0 erreur de schema |
| 11 | Build PyInstaller : `python build.py` | `dist/winboost.exe` créé, taille < 150 Mo |
| 12 | Lancement du `.exe` en background avec timeout 10s | Pas de crash immédiat (exit code attendu : timeout) |
| 13 | Audit code : grep `eval(`, `exec(`, `os.system(`, `shell=True` | Justifier chaque occurrence ou flagger |
| 14 | Audit secrets : grep `sk-ant-`, `sk-proj-`, `AKIA`, `BEGIN PRIVATE KEY` dans le code (hors tests/fixtures) | 0 hit attendu |
| 15 | Lint : `ruff check winboost/` (ou équivalent défini dans `pyproject.toml`) | 0 erreur, warnings acceptables si justifiés |
| 16 | Type check si configuré (`mypy winboost/` ou `pyright`) | Cohérent avec la baseline du projet |
| 17 | Vérifier `README.md` racine : à jour, exemples CLI valides, lien GitHub correct | OK |
| 18 | Vérifier `pyproject.toml` : version = 2.0.0, dépendances pinnées | OK |
| 19 | Lire `winboost/utils/admin.py` (ou équivalent) — vérifier que les UAC prompts sont bien gardés | OK |
| 20 | Vérifier qu'il existe une `LICENSE` à la racine | **Si absent → flag** : Antoine doit ajouter MIT avant release publique |

### Scope NON automatisable (laisser à Antoine)

À lister dans le rapport en section "Tests humains requis" :

- Lancement `winboost gui` et navigation visuelle (dashboard, cards, dark theme, branding)
- Wizard d'onboarding 3 étapes (bienvenue → profil → API key)
- Chat IA temps réel avec une vraie clé Anthropic ("nettoie mes temp", "j'ai mon PC qui rame")
- Test du `.exe` sur une machine Windows 11 vierge (faux positif Defender)
- Vérification visuelle du splash screen
- Test du undo manager via la GUI

## Livrable obligatoire

Écris un rapport structuré dans :

```
A:/dev/winboost/.project/06-agent-logs/{DATE}-reality-checker-pre-release-smoke-test.md
```

(Remplace `{DATE}` par la date du jour `YYYY-MM-DD`.)

### Structure imposée

```markdown
# Pre-Release Smoke Test — Rapport

**Date** : YYYY-MM-DD
**Agent** : Reality Checker (ou Evidence Collector)
**Scope** : v1.0.0 + v2.0.0
**Verdict global** : GO / NO-GO / GO WITH CAVEATS

---

## Résumé exécutif (3-5 lignes)

...

## Résultats des 20 tests automatisés

| # | Test | Résultat | Détails |
|---|------|----------|---------|
| 1 | venv install | ✅ / ❌ | ... |
| ... |
| 20 | LICENSE présente | ✅ / ❌ | ... |

## Issues trouvées (par sévérité)

### 🔴 Bloquantes (release impossible avec)
- ...

### 🟡 À corriger avant release (mais pas bloquantes)
- ...

### 🟢 Notes / amélioration future
- ...

## Tests humains requis (Antoine)

Checklist de ~10 min :
- [ ] ...
- [ ] ...

## Commandes exactes utilisées

```bash
# Liste de toutes les commandes lancées pour reproductibilité
```

## Verdict final

GO / NO-GO / GO WITH CAVEATS — justifier en 3 lignes.
Si NO-GO ou CAVEATS : lister précisément ce qui doit être corrigé (et par qui).
```

## Non-négociable

- **Pas de fichier écrit = travail non fait** (règle Spine n°1)
- **Pas de modification de code dans cette session** — uniquement lecture + exécution + rapport
- **Si un test crashe, capturer le traceback complet** dans le rapport
- **Ne pas inventer un GO** : si le coverage est à 75 % au lieu de 80 %, c'est un caveat, pas un GO silencieux
- **Citer les chiffres réels** (nombre de tests passés, coverage exact, taille du `.exe`, durée du build)

## Comment invoquer ce prompt

Dans une session Claude Code à la racine `A:/dev/winboost` :

```
Active l'agent Reality Checker et exécute le prompt
.project/02-prompts/pre-release-smoke-test.md.
```

Ou plus directement, copier/coller ce prompt entier dans la session.
