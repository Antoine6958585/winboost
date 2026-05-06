# Pre-Release Smoke Test — Rapport (RUN 2)

**Date** : 2026-05-06
**Agent** : Reality Checker (re-run #2 après remédiation)
**Scope** : v1.0.0 + v2.0.0
**Verdict global** : **GO WITH CAVEATS**

> RUN 1 (matin) : NO-GO — 3 bloquants critiques + 5 "à corriger".
> RUN 2 (ce rapport) : tous les bloquants résolus, providers à 97 %
> (concrete providers à 100 %), coverage globale 91 %, ruff clean,
> 382 tests verts. **Une régression honnêteté résiduelle dans `gui/chat.py`**
> (StatusBubble) reste à corriger mais elle est UI-only et n'empêche pas
> les tags GitHub Releases. Tag GO autorisé après acceptation Antoine
> du caveat.

---

## Résumé exécutif

La remédiation des 3 bloquants critiques + 5 points secondaires a été
exécutée correctement et est vérifiable matériellement : `LICENSE` MIT
existe avec copyright Genlead 2026, version `2.0.0` propagée dans les 3
fichiers (pyproject + `__init__.py` + `cli/main.py`) et confirmée
end-to-end via `pip show winboost` (2.0.0), `winboost --version` (2.0.0),
`python -m winboost --version` (2.0.0), `WinBoost.exe --version` (2.0.0),
le module `winboost/utils/admin.py` existe avec `is_admin /
require_admin / relaunch_as_admin / AdminRequiredError` exportés et
testés (18 passed, 1 skipped Linux), branchement effectif dans
`gui/chat.py:_execute_worker:785` (refus propre des actions
`requires_admin: true` sans élévation, statut historique
`blocked_admin_required`), 382 tests verts (vs 320 en RUN 1, +62),
coverage globale **91 %** hors GUI (vs 58 % en RUN 1, cible 80 %
dépassée), providers concrets Anthropic/OpenAI/Ollama tous à **100 %**
(vs 0 %), `ruff check winboost/ tests/` retourne `All checks passed!`
(vs 57 erreurs), `python -m winboost` fonctionne (`__main__.py` créé).
Build PyInstaller toujours OK (23,3 Mo, 36 s). **Caveat restant** : dans
`gui/chat.py:868`, le `StatusBubble` final affiche encore "Action
executee avec succes" pour les actions chat IA — alors que le worker
loggue le statut `catalogued` avec le détail honnête "execution reelle
prevue en v2.1". Le détail honnête s'affiche bien dans la `card.set_result`
(ligne 862), mais le bandeau de status reste mensonger. Lacune mineure
mais directement liée au slogan "ne te ment pas" — à fixer en v2.0.1.

---

## Résultats des 20 tests automatisés

| #  | Test                                             | Résultat | Détails (chiffres réels mesurés) |
|----|--------------------------------------------------|----------|----------------------------------|
| 1  | `pip install -e .` dans venv frais              | OK       | Python 3.12.10, venv `winboost-smoke-run2-20260506121500`, install OK, **`winboost-2.0.0`** posé (vs 0.1.0 en RUN 1). Editable wheel produite. |
| 2  | `pytest tests/ -q --tb=short`                    | OK       | **382 passed, 1 skipped, 0 failed, 0 error** en 46,06 s. +62 tests vs RUN 1 (320). Skip = test Linux relaunch_as_admin (normal sur Windows). |
| 3  | Coverage `--cov=winboost`                        | OK       | **TOTAL 91 %** (1 657 stmts / 155 missing) avec GUI exclue par `[tool.coverage.run] omit` (justification documentée : tests CustomTkinter headless coûteux + fragiles, validation manuelle Antoine via TODO-HUMAN.md). Cible spec ≥80 % **DÉPASSÉE**. |
| 4  | `python -m winboost --help`                      | OK       | `__main__.py` créé qui délègue à `cli`. Liste `chat, fix, gui, info, modules, scan` (pas de `settings` CLI — décision documentée dans le log de remédiation : sera adressé en T066/v2.1). `--version` retourne `WinBoost, version 2.0.0`. |
| 5  | `winboost info`                                  | OK       | Affiche OS Windows 11, CPU Intel 12 threads, RAM 12,6/15,8 Go, disques A:/C:, uptime 2h 4min. Pas de crash. |
| 6  | `scan --module temp_cleaner`                     | OK       | "510.8 Mo recuperables" sur `C:\Users\Dezmen\AppData\Local\Temp` (23 555 fichiers). Aucune suppression. |
| 7  | `scan --module ram_optimizer`                    | OK       | "RAM 78.9% — 3421 Mo dispo — 2 processus gourmand(s)" (MemCompression 1866 Mo, RocketLeague 1388 Mo). |
| 8  | `scan --module disk_analyzer`                    | OK       | "5.1 Go potentiellement recuperables", Téléchargements 4,8 Go, temp 246,8 Mo, crash dumps 12,2 Mo. |
| 9  | Boucle dry-run sur les 150 actions YAML          | OK       | **150/150 instanciables**, 0 erreur. Champs `id/name/description/execute.method` valides, `rollback` présent quand `reversible=true`. Caveat RUN 1 inchangé : pas de mode `--dry-run` runtime côté CLI (validation structurelle uniquement). |
| 10 | Validation schema YAML                           | OK       | `ActionRegistry.load_all()` charge **150 actions, 0 erreur**. Stats : appearance 10, cleanup 20, dev_tools 20, gaming 10, network 10, performance 30, privacy 30, security 10, system 10. Structure inchangée (9 fichiers `actions.yaml` groupés). |
| 11 | Build PyInstaller `python build.py`              | OK       | `dist\WinBoost.exe` créé en **36 s**, taille **23,3 Mo** (24 436 947 octets). |
| 12 | Lancement `.exe` (timeout 10 s)                  | OK       | `WinBoost.exe --version` → `WinBoost, version 2.0.0` (cohérent avec pyproject + `__init__.py` + `cli/main.py`). `--help` retourne le help Click, exit code 0. |
| 13 | Grep `eval(`, `exec(`, `os.system(`, `shell=True`| OK       | **0 occurrence** dans `winboost/`. Inchangé vs RUN 1. |
| 14 | Grep secrets (`sk-ant-`, `sk-proj-`, `AKIA`, `BEGIN PRIVATE KEY`) | OK | **1 hit, sur placeholder UI uniquement** (`gui/onboarding.py:275` → `placeholder_text="sk-ant-..."`). Aucun vrai secret. |
| 15 | `ruff check winboost/ tests/`                    | OK       | **All checks passed!** 0 erreur (vs 57 en RUN 1). `ruff check .` (racine) : également 0. Per-file-ignores configurés dans pyproject (privacy/dev_cache/disk_analyzer + tests). |
| 16 | `mypy` / `pyright`                               | N/A      | Aucun type-checker configuré (inchangé vs RUN 1). Dette technique tolérable post-release, pas bloquant. |
| 17 | README à jour                                    | OK avec caveats | Version v2.0 cohérente (slogan, modules, AI providers). LICENSE désormais référencée implicitement (le fichier existe à la racine). Pas de mise à jour explicite "Licence MIT — voir LICENSE", mais GitHub affiche le badge automatiquement. |
| 18 | `pyproject.toml` version + deps                  | OK       | `version = "2.0.0"` (RUN 1 : 0.1.0). Cohérent avec `winboost/__init__.py:__version__ = "2.0.0"` et `cli/main.py:@click.version_option(version="2.0.0", ...)`. **Triple cohérence vérifiée**. Deps en `>=` (politique permissive, identique RUN 1). |
| 19 | UAC prompts dans `winboost/utils/admin.py`       | OK       | Fichier **existe** (109 lignes). Exports : `AdminRequiredError, is_admin, require_admin, relaunch_as_admin` — vérifiés via import direct. Re-exportés dans `winboost/utils/__init__.py`. **Branchement effectif dans `gui/chat.py:_execute_worker:776-799`** : `if action.requires_admin and not is_admin()` → log `blocked_admin_required` + retour erreur. 18 tests admin verts (1 skip Linux). |
| 20 | `LICENSE` à la racine                            | OK       | Fichier `LICENSE` (1 064 octets) présent. Texte MIT standard, copyright **2026 Genlead**, cohérent avec `pyproject.toml:license = {text = "MIT"}` et le classifier Trove. |

---

## Issues trouvées (par sévérité)

### Bloquantes (release impossible avec)

**Aucune.** Les 3 bloquants du RUN 1 sont tous résolus avec preuves
mesurables (LICENSE existe et est MIT 2026 Genlead, version cohérente
2.0.0 dans 3 fichiers + binaire, UAC helper implémenté + intégré +
testé).

### À corriger avant release (mais pas strictement bloquantes)

1. **`StatusBubble` mensonger résiduel dans le chat IA** (`gui/chat.py:868`).
   Le worker `_execute_worker` est désormais honnête (ligne 818-822 : "Action
   enregistree (catalogue v2.0, methode 'X', parametres : ..., execution reelle
   prevue en v2.1)" + statut `catalogued` dans l'historique), et la
   `card.set_result(success, message)` reçoit le détail honnête. **Mais** le
   `StatusBubble` final ligne 868 affiche encore le texte hardcodé
   `"Action executee avec succes"` quand `success=True`. Pour un utilisateur
   non-attentif au panneau de détail, le bandeau supérieur dit que c'est exécuté
   alors qu'il s'agit d'un enregistrement catalogue. **Frontalement contradictoire
   avec le slogan "ne te ment pas"**, donc à fixer rapidement (ex. : passer
   `message` au StatusBubble plutôt que le label fixe, ou utiliser le label
   "Action enregistree (catalogue v2.0)" tant que l'executor v2.1 n'est pas
   livré). **Lacune UI seulement**, pas bloquante pour le tag GitHub Release —
   mais à fixer dans la première v2.0.1 ou avant le repo public.

2. **Coverage `ai/providers/base.py` à 86 %, pas 100 % comme annoncé**
   (test 3). Le log de remédiation parle de "providers à 100 %". Dans les
   faits, les **3 providers concrets** (anthropic/openai/ollama) **sont à
   100 %**, mais la classe abstraite `base.py` reste à 86 % (3 stmts
   manquants — probablement des `raise NotImplementedError` non
   couverts). **Inflation mineure du chiffre** dans le log de remédiation,
   mais la cible "providers couverts à 80 %" du RUN 1 est largement
   atteinte. Pas bloquant. À documenter avec exactitude lors du tag.

3. **Pas de commande `settings` CLI** (test 4, identique RUN 1). Statut :
   décision documentée dans le log de remédiation (sera adressé en T066,
   phase 11/v2.1). À noter dans les release notes.

### Notes / amélioration future

4. Pas de `mypy`/`pyright` (test 16, identique RUN 1). Dette tech post-release.
5. Structure des actions YAML : 9 fichiers groupés (test 9-10, identique RUN 1). À documenter pour la communauté.
6. Le `.exe` s'appelle `WinBoost.exe` (capital), module Python `winboost`. Cohérent branding, à mentionner dans les release notes.
7. Version 2.0.0 directe (pas de tag v1.0.0 historique). Antoine doit décider si v1.0.0 doit être tagué sur un commit ancien (avant la phase v2 AI) ou simplement sauter à v2.0.0. Pour T029 + T061 simultanés, identifier le commit cible v1.0.0 (probablement après la phase 8 — premier release v1 sans IA).
8. README ne mentionne pas explicitement "MIT — voir LICENSE" (test 17). Ajout en 1 ligne souhaitable.
9. Pas de manifest PyInstaller `uac_admin=True` (Option A non retenue, choix Option B helper sélectif documenté). Cohérent avec la philosophie "n'élève que si nécessaire".

---

## Comparaison RUN1 vs RUN2

### Bloquants critiques

| # | Bloquant RUN 1 | Statut RUN 2 | Preuve |
|---|---|---|---|
| 1 | Pas de `LICENSE` racine (mais MIT annoncé partout) | **RÉSOLU** | `LICENSE` 1 064 octets, MIT, copyright 2026 Genlead, vérifié `head -3 LICENSE` |
| 2 | Version `0.1.0` au lieu de `2.0.0` | **RÉSOLU** | `pyproject.toml:7 version = "2.0.0"`, `__init__.py:3 __version__ = "2.0.0"`, `cli/main.py:35 version="2.0.0"`, `pip show winboost` → 2.0.0, `winboost --version` → 2.0.0, `python -m winboost --version` → 2.0.0, `WinBoost.exe --version` → 2.0.0 (5 sources cohérentes) |
| 3 | Aucun mécanisme UAC | **RÉSOLU** | `winboost/utils/admin.py` (109 lignes), 4 fonctions exportées (`is_admin`, `require_admin`, `relaunch_as_admin`, `AdminRequiredError`), 18 tests passants (1 skip Linux), branchement effectif dans `gui/chat.py:_execute_worker:785` (refus + log `blocked_admin_required` si `requires_admin=true` et pas admin) |

### Points "à corriger" (5 du RUN 1)

| # | Point RUN 1 | Statut RUN 2 | Preuve |
|---|---|---|---|
| 4 | Coverage globale 58 %, providers à 0 % | **RÉSOLU avec nuance** | Coverage globale 91 % (cible 80 % dépassée). Providers concrets 100 %. `base.py` abstrait à 86 % (3 stmts non couverts). Log de remédiation annonçait "100 %" — léger excès de zèle, mais l'objectif fonctionnel est atteint. 44 tests providers passants. |
| 5 | 57 erreurs ruff | **RÉSOLU** | `ruff check winboost/ tests/` → "All checks passed!" 0 erreur. Configuration `per-file-ignores` documentée dans pyproject. |
| 6 | `python -m winboost` ne fonctionne pas | **RÉSOLU** | `winboost/__main__.py` créé (6 lignes, délègue à `cli/main.py:cli`). Test 4a : `python -m winboost --help` retourne le help Click, `--version` retourne 2.0.0. |
| 7 | Pas de commande `settings` CLI | **NON RÉSOLU (volontairement)** | Décision documentée dans le log de remédiation : hors scope smoke test, sera adressé en T066 (mode JSON CLI) phase 11/v2.1. À mentionner en release notes. |
| 8 | Doc structure YAML (9 fichiers ≠ 150) | **NON RÉSOLU (différé)** | À enrichir dans CLAUDE.md projet en v2.1. Pas un blocker. |

### Bonus honnêteté produit

| Découverte | Statut RUN 2 | Preuve |
|---|---|---|
| Mensonge "executee" du worker chat (vu dans le log de remédiation) | **PARTIELLEMENT RÉSOLU** | Le worker logge bien `catalogued` + détail "execution reelle prevue en v2.1" (`gui/chat.py:818-822, 830`), et la `card.set_result` affiche ce détail. **MAIS** le `StatusBubble` final ligne 868 affiche encore `"Action executee avec succes"` hardcodé quand `success=True`. Lacune UI résiduelle. Voir issue n°1 ci-dessus. |

### Métriques numériques

| Métrique | RUN 1 (avant) | RUN 2 (après, mesuré) | Match avec log remédiation |
|---|---|---|---|
| Tests passants | 320 | **382** | OK (annonce : 382) |
| Tests skipped | 0 | 1 | (relaunch_as_admin Linux) |
| Coverage globale | 58 % | **91 %** (hors GUI omittée) | OK (annonce : 91 % hors GUI) |
| Coverage providers | 0 % | **97 %** (concrete providers 100 %, base 86 %) | Légère inflation du log (annonce : 100 %) |
| Coverage utils/admin | N/A | 84 % | OK |
| Erreurs ruff | 57 | **0** | OK (annonce : 0) |
| LICENSE | absent | présent (MIT, 1064 o, Genlead 2026) | OK |
| Version pyproject | 0.1.0 | 2.0.0 | OK |
| `python -m winboost` | KO | OK | OK |
| Build PyInstaller | 41 s, 23,3 Mo | 36 s, 23,3 Mo | OK (taille identique) |
| Commits remédiation | n/a | 6 commits ciblés (LICENSE, version, UAC, `__main__`, ruff, providers) + 1 docs | OK |

### Nouvelles issues introduites par la remédiation

Aucune régression critique détectée. Une seule lacune UI mineure
résiduelle : le `StatusBubble` n'a pas été refondu en même temps que
le worker, créant un décalage entre le détail honnête (carte d'action)
et le bandeau supérieur ("Action executee avec succes"). Cela ne
dégrade pas le RUN 1 — le RUN 1 avait le même bandeau menteur — mais
puisque la remédiation s'est attaquée à l'honnêteté produit, c'est une
incohérence interne qui mérite d'être consignée.

---

## Tests humains requis (Antoine)

Checklist d'environ 10 minutes — identique au RUN 1, avec un focus
ajouté sur la vérification UAC :

- [ ] Lancer `WinBoost.exe gui` (depuis `dist/`) — vérifier le splash, le dashboard, les 5 cards modules, le dark theme, le branding
- [ ] Wizard onboarding 3 étapes : bienvenue → choix profil (Safe / Power / Expert) → API key (placeholder "sk-ant-...")
- [ ] Chat IA temps réel avec une vraie clé Anthropic : tester `nettoie mes temp`, `j'ai mon PC qui rame`, `desactive la telemetrie`
- [ ] **Vérifier que le `StatusBubble` après "Apply" sur une action chat dit "Action enregistree (catalogue v2.0...)" ou similaire, pas "Action executee avec succes"** — si ça dit toujours "executee avec succes", l'incohérence UI résiduelle est confirmée et il faut un fix v2.0.1
- [ ] Test `WinBoost.exe` sur une machine Windows 11 vierge (autre PC ou VM) : noter le faux positif Defender éventuel et le délai SmartScreen
- [ ] **Cliquer "Apply" sur une action `requires_admin: true` (ex. `privacy_001` DiagTrack) sans lancer en admin** → vérifier que le message d'erreur dit bien "requiert les droits administrateur" et que rien ne s'exécute (validation du bloquant n°3 résolu)
- [ ] Test du undo manager via la GUI : effectuer un scan + fix sur `temp_cleaner` (à un endroit non-critique), vérifier l'entrée dans History viewer
- [ ] Vérifier que `LICENSE` est visible sur GitHub après push (badge MIT en haut à droite de la repo page)

---

## Commandes exactes utilisées

```bash
# 0. Lecture des 2 logs de référence + prompt
# A:/dev/winboost/.project/06-agent-logs/2026-05-06-reality-checker-pre-release-smoke-test.md
# A:/dev/winboost/.project/06-agent-logs/2026-05-06-claude-code-remediation-bloquants-smoke-test.md
# A:/dev/winboost/.project/02-prompts/pre-release-smoke-test.md

# 0.1 Vérification fichiers fix annoncés
ls -la A:/dev/winboost/LICENSE A:/dev/winboost/winboost/__main__.py A:/dev/winboost/winboost/utils/admin.py
git log --oneline -20

# 0.2 Vérif version dans 3 sources
grep -n "version" A:/dev/winboost/pyproject.toml | head -10
grep -n "version" A:/dev/winboost/winboost/cli/main.py
cat A:/dev/winboost/winboost/__init__.py

# 0.3 Vérif UAC integration dans gui/chat.py
grep -n "_execute_worker\|requires_admin\|is_admin\|AdminRequiredError\|enregistree\|executee" A:/dev/winboost/winboost/gui/chat.py

# 1. Création venv frais
TS=$(date +%Y%m%d%H%M%S)
VENVDIR="/c/Users/Dezmen/AppData/Local/Temp/winboost-smoke-run2-$TS"
mkdir -p "$VENVDIR"
"C:/Users/Dezmen/AppData/Local/Programs/Python/Python312/python.exe" -m venv "$VENVDIR/venv"
PY="$VENVDIR/venv/Scripts/python.exe"
WINBOOST="$VENVDIR/venv/Scripts/winboost.exe"
# -> /c/Users/Dezmen/AppData/Local/Temp/winboost-smoke-run2-20260506121500

# 2. Install editable + deps
"$PY" -m pip install --upgrade pip
"$PY" -m pip install -e .                                           # Test 1 (winboost-2.0.0 OK)
"$PY" -m pip show winboost                                          # Vérif version 2.0.0
"$PY" -m pip install pytest pytest-mock pytest-cov ruff anthropic openai pyinstaller

# 3. Tests pytest
"$PY" -m pytest tests/ -q --tb=short                                # Test 2 — 382 passed, 1 skipped
"$PY" -m pytest tests/ --cov=winboost --cov-report=term             # Test 3 — TOTAL 91 %

# 4. CLI entrypoints
"$PY" -m winboost --help                                            # Test 4a — OK (vs KO en RUN 1)
"$PY" -m winboost --version                                         # Test 4b — 2.0.0
"$WINBOOST" --version                                               # Test 4c — 2.0.0
"$WINBOOST" info                                                    # Test 5
"$WINBOOST" scan --module temp_cleaner                              # Test 6
"$WINBOOST" scan --module ram_optimizer                             # Test 7
"$WINBOOST" scan --module disk_analyzer                             # Test 8

# 5. Validation YAML actions (boucle dry-run + schema)
"$PY" -c "from winboost.actions.loader import ActionRegistry; reg=ActionRegistry(); reg.load_all(); print(len(reg._actions))"
# -> 150 (Tests 9-10)

# 6. Build PyInstaller
rm -rf dist build *.spec
"$PY" build.py                                                      # Test 11 — 36s, 23.3 Mo
./dist/WinBoost.exe --version                                       # Test 12 — 2.0.0
./dist/WinBoost.exe --help                                          # Test 12b — exit 0

# 7. Audit code (Grep)
# Pattern : \beval\(|\bexec\(|os\.system\(|shell\s*=\s*True   sur winboost/ -> 0 hit (Test 13)
# Pattern : sk-ant-|sk-proj-|AKIA|BEGIN PRIVATE KEY            sur winboost/ -> 1 placeholder UI (Test 14)

# 8. Lint
"$PY" -m ruff check winboost/ tests/                                # Test 15 — All checks passed!
"$PY" -m ruff check .                                               # OK

# 9. Type-check (N/A)
ls mypy.ini pyrightconfig.json                                      # Test 16 — N/A (inchangé)

# 10. README + LICENSE + utils/admin
head -3 LICENSE                                                     # Test 20 — MIT 2026 Genlead
"$PY" -c "from winboost.utils import admin; print([x for x in dir(admin) if not x.startswith('_')])"
"$PY" -c "from winboost.utils import is_admin, AdminRequiredError, require_admin, relaunch_as_admin; print('OK 4 importable')"
"$PY" -m pytest tests/test_utils/test_admin.py -v                   # Test 19 — 18 passed, 1 skip

# 11. Coverage isolée providers
"$PY" -m pytest tests/test_ai/test_providers.py --cov=winboost.ai.providers
# -> TOTAL 97 % (concrete 100 %, base 86 %)
```

Logs de session présents dans le shell pour traceback.

---

## Verdict final

**GO WITH CAVEATS** pour les tags GitHub Releases v1.0.0 (T029) et v2.0.0 (T061).

Justification en 3 lignes :

1. **Bloquants RUN 1 tous résolus avec preuves matérielles** : `LICENSE` MIT
   présent + version `2.0.0` cohérente sur 5 sources (pyproject, `__init__`,
   `cli/main`, `pip show`, binaire `.exe`) + UAC helper avec 18 tests verts
   et branchement effectif dans le worker chat — chacun vérifié par
   exécution réelle, pas par confiance dans le log de remédiation.
2. **Métriques quantitatives largement au-dessus des cibles** : 382 tests
   verts (vs 320, +62), coverage 91 % (vs cible 80 %), 0 erreur ruff (vs
   57), build PyInstaller stable à 23,3 Mo, providers concrets à 100 %.
3. **Caveat unique** : `gui/chat.py:868` `StatusBubble` affiche encore
   "Action executee avec succes" hardcodé alors que le worker logge
   correctement `catalogued`. Incohérence UI mineure mais directement liée
   au slogan "ne te ment pas" — à fixer dans la v2.0.1 ou avant que le repo
   passe public, pas bloquant pour le tag.

### Ce qui doit être corrigé avant repo public (par claude-code, hors smoke test)

1. **`gui/chat.py:864-870`** : remplacer le label hardcodé du `StatusBubble`
   par le `message` reçu (ou un label neutre type "Action enregistree dans
   l'historique"). 5 lignes de code, ~10 minutes.
2. **README.md** : ajouter une ligne "Licence : MIT — voir [LICENSE](LICENSE)" en bas. ~2 minutes.
3. **Release notes du tag v2.0.0** : mentionner explicitement "execution
   reelle des actions YAML prevue en v2.1" pour aligner la communication
   externe avec ce que fait réellement le worker chat. ~5 minutes.

### Ce qui est tolérable post-release

- Coverage `ai/providers/base.py` à 86 % (la classe abstraite ne nécessite pas 100 %)
- Pas de `mypy`/`pyright` configuré (dette tech)
- Pas de commande `settings` CLI (planifié T066/v2.1)
- Doc structure YAML 9 fichiers groupés (à enrichir v2.1)

### Décision Antoine attendue

- **Stratégie de tag** : v1.0.0 sur quel commit ? Probablement le dernier
  commit pré-v2 (avant l'ajout du chat IA, soit la fin de phase 8). Si on
  tag v1.0.0 directement sur le commit courant, le binaire dira `version
  2.0.0` et la cohérence est cassée. Recommandation : identifier le commit
  v1 (probablement avant `1c37670` ou autour) et tagger là, puis tag
  v2.0.0 sur HEAD.
- **Fix `StatusBubble` avant ou après tag** : si le repo passe public au
  même moment que le tag v2.0.0, fixer avant. Si la mise en public est
  différée, on peut shipper et fixer en v2.0.1 dans la semaine.

---

> Rapport produit en lecture/exécution seule. **Aucune modification de code**
> effectuée pendant ce smoke test (conformément à la consigne et à la règle
> Spine n°1). Verdict basé sur 20 tests automatisés + lecture de code +
> exécution end-to-end du binaire `.exe`.
