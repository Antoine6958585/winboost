# Pre-Release Smoke Test — Rapport

**Date** : 2026-05-06
**Agent** : Reality Checker
**Scope** : v1.0.0 + v2.0.0
**Verdict global** : **NO-GO**

---

## Résumé exécutif

Le code WinBoost est **techniquement très solide** sur le cœur (320/320 tests verts, 150 actions YAML valides, build `.exe` en 41 s à 23,3 Mo, pas de `eval`/`exec`/`shell=True`, pas de secret, pas de fuite). Mais **plusieurs prérequis non négociables d'une release publique sont absents** : pas de fichier `LICENSE` à la racine alors que le `pyproject.toml` et le README annoncent MIT, version `pyproject.toml` figée à `0.1.0` au lieu de `2.0.0`, module `winboost/utils/admin.py` annoncé dans CLAUDE.md mais inexistant, aucun mécanisme d'élévation UAC alors que des actions `requires_admin: true` touchent au registre HKLM, couverture globale à **58 %** (cible 80 %), et 57 erreurs `ruff` sur le package alors que la checklist projet exige un lint clean. Tag impossible en l'état pour T029 + T061.

---

## Résultats des 20 tests automatisés

| #  | Test                                             | Résultat | Détails (chiffres réels) |
|----|--------------------------------------------------|----------|--------------------------|
| 1  | `pip install -e .` dans venv frais              | OK       | Python 3.12.10, venv `winboost-smoke-20260506113056`, install OK, **`winboost-0.1.0`** posé (pas 2.0.0). Deps `[ai]` non installées par défaut. |
| 2  | `pytest tests/ -q --tb=short`                    | OK       | **320 tests passed, 0 failed, 0 error** en 30,83 s. Match exact avec la spec. |
| 3  | Coverage `--cov=winboost`                        | FAIL     | **TOTAL 58 %** sur 2 673 stmts. core 91-100 % OK, modules 72-94 % (proche), `ai/*` 93-100 % mais **`ai/providers/*` à 0 %** (jamais testés), `gui/*` 13-28 %, `cli/main.py` 88 %. Cible spec : ≥80 %. **NON ATTEINT**. |
| 4  | `python -m winboost --help`                      | FAIL     | `No module named winboost.__main__`. Le package n'a pas d'entrypoint `-m`. La commande `winboost --help` (console_script) fonctionne et liste : `chat, fix, gui, info, modules, scan`. **`settings` est absent du CLI** (existe seulement en GUI). Le test 4 tel que rédigé échoue. |
| 5  | `winboost info`                                  | OK       | Affiche OS Windows 11 (10.0.26200), CPU Intel 12 threads, RAM 13.8/15.8 Go, disques A: et C:, uptime. Pas de crash. |
| 6  | `scan --module temp_cleaner` (lecture seule)     | OK       | "378.6 Mo recuperables" sur `C:\Users\Dezmen\AppData\Local\Temp` (9 188 fichiers). Aucune suppression. Note : nom du module `temp_cleaner` (pas `temp` comme dans la spec). |
| 7  | `scan --module ram_optimizer` (lecture seule)    | OK       | "RAM 87.6 % - 2009 Mo dispo - 3 processus gourmands" (MemCompression, Cursor, claude). Lecture seule. |
| 8  | `scan --module disk_analyzer` (lecture seule)    | OK       | "5.1 Go potentiellement recuperables", détaille Téléchargements 4.8 Go, temp 247 Mo, crash dumps 12.2 Mo. Lecture seule. |
| 9  | Boucle dry-run sur les 150 actions YAML          | OK       | **150/150 instanciables** : `id`, `name`, `description`, `execute.method` valides, rollback présent quand `reversible=true`. **Caveat important** : il n'existe **pas** de mode `--dry-run` exécutable côté CLI ; la "boucle dry-run" est ici une validation structurelle (instanciation `Action`), pas une simulation runtime de l'effet de chaque action. |
| 10 | Validation schema YAML                           | OK       | `ActionRegistry.load_all()` charge **150 actions, 0 erreur**. Stats : appearance 10, cleanup 20, dev_tools 20, gaming 10, network 10, performance 30, privacy 30, security 10, system 10. **Note structure** : 9 fichiers `actions.yaml` (un par catégorie) regroupant les actions, **pas** 150 fichiers individuels comme on pouvait l'inférer de la spec. |
| 11 | Build PyInstaller `python build.py`              | OK       | `dist\WinBoost.exe` créé en **41,2 s**, taille **23,3 Mo** (très en dessous des 150 Mo). Note : le binaire s'appelle `WinBoost.exe` (capitalisé), pas `winboost.exe` comme dans la spec. |
| 12 | Lancement `.exe` (timeout 10 s)                  | OK       | `WinBoost.exe --help` retourne le help Click, exit normal, code retour 0. Pas de crash. |
| 13 | Grep `eval(`, `exec(`, `os.system(`, `shell=True`| OK       | **0 occurrence** dans `winboost/`. Excellent. |
| 14 | Grep secrets (`sk-ant-`, `sk-proj-`, `AKIA`, `BEGIN PRIVATE KEY`) | OK | Hits uniquement sur des **placeholders UI** (`gui/onboarding.py:276` → `"sk-ant-..."`) et des fixtures de tests / docs. **0 vrai secret** dans le code. |
| 15 | `ruff check winboost/`                           | FAIL     | **57 erreurs** (35 auto-fixables) : I001 imports désordonnés, F401 imports inutiles, F841 variables locales mortes, E501 lignes > 100, UP017 `datetime.UTC`. Aucune n'est de sécurité, mais la checklist projet exige `ruff check .` clean. |
| 16 | `mypy` / `pyright`                               | N/A      | **Aucun type-checker configuré** dans `pyproject.toml`, pas de `mypy.ini` ni `pyrightconfig.json`. Pas de baseline existante donc rien à comparer. À traiter comme dette tech, pas bloquant pour T029/T061. |
| 17 | README à jour                                    | OK avec caveats | Examples CLI valides (`winboost scan --module temp_cleaner` confirmé). Lien `github.com/Antoine6958585/winboost.git` cohérent avec status.yaml. **Caveats** : ne mentionne pas explicitement la version (juste "v2.0" en marketing), ne signale pas l'absence de LICENSE, et la commande `winboost gui` est documentée alors que les UAC prompts ne sont pas implémentés (cf. test 19). |
| 18 | `pyproject.toml` version + deps                  | FAIL     | **`version = "0.1.0"`** (pas `2.0.0`). Idem dans `winboost/__init__.py:3` et `cli/main.py:35`. **Triple incohérence** entre code (0.1.0) et docs (v2.0). Deps utilisent `>=` (politique permissive standard, pas pinnées strictement) — acceptable mais à noter. |
| 19 | UAC prompts dans `winboost/utils/admin.py`       | FAIL     | **Le fichier `winboost/utils/admin.py` n'existe pas.** `winboost/utils/` ne contient qu'un `__init__.py` vide. Aucune occurrence de `IsUserAnAdmin`, `ShellExecuteW`, `runas` dans tout le code. Les actions `requires_admin: true` (ex: `privacy_001` qui désactive le service `DiagTrack`, ou les écritures `HKLM\\SOFTWARE\\Microsoft\\SQMClient\\Windows`) **n'ont aucun mécanisme d'élévation** : si l'utilisateur lance WinBoost sans admin, elles échoueront avec une erreur Windows brute. Le flag `requires_admin` est purement **déclaratif** (affiché en badge UI dans `gui/chat.py:203`). **Lacune produit majeure** pour un outil de tweaking système. |
| 20 | `LICENSE` à la racine                            | FAIL     | **Aucun fichier `LICENSE`, `LICENSE.md` ni `LICENSE.txt`.** Or `pyproject.toml` déclare `license = {text = "MIT"}`, le classifier `License :: OSI Approved :: MIT License` est posé, et `README.md` annonce "Licence : MIT". **Bloquant pour une release publique** : un repo qui passe public sans `LICENSE` n'autorise juridiquement aucun usage. |

---

## Issues trouvées (par sévérité)

### Bloquantes (release impossible avec)

1. **LICENSE manquante** (test 20). Le `pyproject.toml`, le README et les classifiers Trove annoncent MIT mais aucun fichier de licence n'existe. Sur un repo public, c'est juridiquement bloquant et c'est le premier point que les utilisateurs voient sur GitHub. → ajouter `LICENSE` (texte MIT standard) AVANT `git push --tags`.
2. **Version `pyproject.toml` = 0.1.0 au lieu de 2.0.0** (test 18). Tag `v2.0.0` sur un binaire qui se présente comme `0.1.0` (visible dans `winboost --version`, dans `pip show winboost`, dans `WinBoost.exe --version`) crée une incohérence visible immédiate. Idem dans `winboost/__init__.py:3` et `cli/main.py:35`. → bumper en `2.0.0` (ou stratégie deux tags : `v1.0.0` puis `v2.0.0` avec deux versions distinctes).
3. **Aucune élévation UAC** (test 19). Les actions `requires_admin: true` du registre vont silencieusement échouer en exécution réelle si le binaire n'est pas lancé en tant qu'admin. C'est un mensonge produit ("Le premier assistant Windows qui ne te ment pas") — l'utilisateur clique "Appliquer", l'UI dit que c'est appliqué, et rien ne se passe (ou pire, demi-application). → soit un manifest UAC `requireAdministrator` dans le `.exe` PyInstaller, soit un helper `winboost/utils/admin.py` qui détecte et fait une relance via `ShellExecuteW`/`runas`. Sans ça, retirer la commande `apply` pour les actions admin et documenter "lance en admin" en très gros dans le README.

### À corriger avant release (mais pas strictement bloquantes)

4. **Coverage globale à 58 %, cible 80 %** (test 3). Les zones critiques (core, ai, modules) sont au-dessus de 80 %, mais `ai/providers/*` est à **0 %** et la GUI à 13-28 %. Les providers à 0 % signifient que personne n'a jamais exécuté `AnthropicProvider.complete()` même mocké — c'est exactement le code qui parle à l'API en prod. À couvrir au minimum à 80 % avec mocks `httpx`/`anthropic.Anthropic`. La GUI à 13-28 % est plus défendable (tests de smoke uniquement), mais à signaler.
5. **57 erreurs ruff** (test 15). Aucune n'est sécuritaire, mais la `checklist.md` du projet inclut "Ruff lint clean" comme critère avant push. 35 sont auto-fixables (`ruff check . --fix`). À nettoyer en 5 minutes.
6. **`python -m winboost` ne fonctionne pas** (test 4). Pas de `winboost/__main__.py`. Le smoke test du prompt utilisait `python -m winboost --help` ; cela échoue avec `No module named winboost.__main__`. La commande `winboost` (console_script) fonctionne. À ajouter pour la robustesse : un `__main__.py` qui appelle `cli`.
7. **Pas de commande `settings` CLI** (test 4). La spec attendait `scan, fix, info, chat, gui, settings`. La CLI expose `chat, fix, gui, info, modules, scan` — `settings` est uniquement GUI. Soit ajuster la spec, soit ajouter `winboost settings` (aligné sur `winboost gui` + page settings).
8. **Structure des actions YAML : 9 fichiers, pas 150** (tests 9-10). Ce n'est pas un bug — le contenu est OK, 150 actions valides — mais le contrat affiché dans CLAUDE.md ("Chaque action est un fichier YAML dans `actions/{categorie}/`") laisse entendre 1 fichier = 1 action. La réalité : 1 fichier `actions.yaml` par catégorie regroupant N actions. À documenter pour la communauté future qui voudra ajouter des actions.

### Notes / amélioration future

9. Pas de `mypy`/`pyright` configuré (test 16). Pas bloquant, mais le projet a beaucoup de typing — un `mypy --strict winboost/core` serait gagnant rapide.
10. Pas de mode `--dry-run` exécutable côté CLI pour les actions YAML (test 9). La spec parle de "150 actions YAML, dry-run" mais il n'existe pas de `winboost action run privacy_001 --dry-run`. Le dry-run est limité au scan des modules v1 ("scan" = lecture, "fix" = exécution). À ajouter pour v2.1 — c'est le canal naturel pour exposer les 150 actions hors du chat.
11. Le `.exe` s'appelle `WinBoost.exe` (capital) mais le module Python `winboost`. Cohérent côté branding, à documenter dans le README pour éviter la confusion `pip install winboost` vs téléchargement `WinBoost.exe`.
12. Pas de manifest PyInstaller "asInvoker" explicite. Sur Windows 10/11, sans manifest, le binaire hérite du contexte parent — comportement OK mais à figer pour éviter les surprises Defender.
13. README ne référence pas le commit ou la version exacte — vérifier en revue Antoine que `WinBoost.exe` posé dans la release correspond bien au commit du tag.

---

## Tests humains requis (Antoine)

Checklist d'environ 10 minutes, à faire **après** correction des bloquants 1-3 ci-dessus :

- [ ] Lancer `WinBoost.exe gui` (depuis `dist/`) — vérifier le splash, le dashboard, les 5 cards modules, le dark theme, le branding
- [ ] Wizard onboarding 3 étapes : bienvenue → choix profil (Safe / Power / Expert) → API key (avec placeholder "sk-ant-...")
- [ ] Chat IA temps réel avec une vraie clé Anthropic : tester `nettoie mes temp` (cache local attendu), `j'ai mon PC qui rame` (route LLM attendue), `desactive la telemetrie` (3 actions privacy proposées)
- [ ] Test `WinBoost.exe` sur une machine Windows 11 vierge (autre PC ou VM) : noter le faux positif Defender éventuel et le délai SmartScreen
- [ ] Vérification visuelle splash screen (icône, durée, transition vers la fenêtre principale)
- [ ] Test du undo manager via la GUI : effectuer un scan + fix sur `temp_cleaner` (à un endroit non-critique), vérifier l'entrée dans History viewer, déclencher l'undo, confirmer la restauration via SQLite
- [ ] Lancer `WinBoost.exe scan` **en tant qu'admin** vs. **utilisateur standard** sur une action `requires_admin: true` (ex. désactivation DiagTrack) : confirmer ou infirmer le bloquant n°3 (élévation UAC)

---

## Commandes exactes utilisées

```powershell
# 0. Lecture du contexte
# A:/dev/winboost/CLAUDE.md, status.yaml, MASTER-PLAN.md, architecture.md, checklist.md, synthese-retroactive.md

# 1. Création venv frais
$ts = Get-Date -Format "yyyyMMddHHmmss"
$venvdir = "$env:TEMP\winboost-smoke-$ts"
New-Item -ItemType Directory -Force -Path $venvdir | Out-Null
& "C:\Users\Dezmen\AppData\Local\Programs\Python\Python312\python.exe" -m venv "$venvdir\venv"
# -> C:\Users\Dezmen\AppData\Local\Temp\winboost-smoke-20260506113056\venv

$venv = "$venvdir\venv"
& "$venv\Scripts\python.exe" -m pip install --upgrade pip
& "$venv\Scripts\python.exe" -m pip install -e .                           # Test 1
& "$venv\Scripts\python.exe" -m pip install "pytest>=8.0" "pytest-mock>=3.12" "pytest-cov>=4.1" "ruff>=0.5" "anthropic>=0.40" "openai>=1.50" "pyinstaller>=6.0"

# 2. Tests pytest
& "$venv\Scripts\python.exe" -m pytest tests/ -q --tb=short                 # Test 2
& "$venv\Scripts\python.exe" -m pytest tests/ --cov=winboost --cov-report=term-missing  # Test 3

# 4-8. CLI
& "$venv\Scripts\python.exe" -m winboost --help                             # Test 4 (FAIL)
& "$venv\Scripts\winboost.exe" --help                                       # Test 4 alt
& "$venv\Scripts\winboost.exe" info                                         # Test 5
& "$venv\Scripts\winboost.exe" scan --module temp_cleaner                   # Test 6
& "$venv\Scripts\winboost.exe" scan --module ram_optimizer                  # Test 7
& "$venv\Scripts\winboost.exe" scan --module disk_analyzer                  # Test 8

# 9-10. Actions YAML : script Python dédié dans le venv
& "$venv\Scripts\python.exe" "C:\...\winboost-smoke-20260506113056\test_actions.py"

# 11-12. Build PyInstaller + lancement .exe
& "$venv\Scripts\python.exe" build.py
$proc = Start-Process -FilePath "A:\dev\winboost\dist\WinBoost.exe" -ArgumentList "--help" -PassThru -NoNewWindow `
    -RedirectStandardOutput "$env:TEMP\winboost-exe-stdout.txt" -RedirectStandardError "$env:TEMP\winboost-exe-stderr.txt"
$proc.WaitForExit(10000)

# 13-14. Audit code (via outil Grep, équivalent ripgrep)
# Pattern : \beval\(|\bexec\(|os\.system\(|shell\s*=\s*True   sur winboost/
# Pattern : sk-ant-|sk-proj-|AKIA|BEGIN PRIVATE KEY            sur winboost/

# 15. Lint
& "$venv\Scripts\python.exe" -m ruff check winboost/                        # 57 erreurs

# 19-20. Audit fichiers
# ls A:/dev/winboost/LICENSE          -> not found
# ls A:/dev/winboost/winboost/utils/  -> __init__.py uniquement
```

Logs persistés :

- `$env:TEMP\winboost-test1-install.log` (install)
- `$env:TEMP\winboost-test2-pytest.log` (320 tests)
- `$env:TEMP\winboost-test3-cov.log` (coverage 58 %)
- `$env:TEMP\winboost-test11-build.log` (PyInstaller)
- `$env:TEMP\winboost-test15-ruff.log` (57 ruff errors)
- `$env:TEMP\winboost-exe-stdout.txt` (.exe --help)

---

## Verdict final

**NO-GO** pour les tags GitHub Releases v1.0.0 (T029) et v2.0.0 (T061) en l'état.

Justification en 3 lignes :
1. **Légal** : pas de fichier `LICENSE`, alors que tout le métadata annonce MIT — un repo public sans `LICENSE` ne donne juridiquement aucun droit d'usage et c'est la première chose que GitHub affiche.
2. **Versionning** : `pyproject.toml` + `winboost/__init__.py` + `cli/main.py` annoncent `0.1.0`, alors que les tags ciblés sont `v1.0.0` et `v2.0.0` — incohérence immédiatement visible par tout utilisateur (`winboost --version`).
3. **Sécurité produit** : `requires_admin: true` est purement déclaratif, sans aucun mécanisme d'élévation UAC ; les actions registre HKLM échoueront silencieusement pour un utilisateur non-admin, ce qui contredit frontalement le positionnement "ne te ment pas".

### Plan minimal pour passer en GO (≈2 h de travail)

À faire par **claude-code** (revue Antoine + Silvio), dans une session séparée (pas dans ce smoke test, qui est lecture seule) :

1. Créer `LICENSE` racine (texte MIT standard, copyright Genlead, année 2026). → **antoine** ou **claude-code**
2. Bumper `pyproject.toml` à `2.0.0` + `winboost/__init__.py:__version__ = "2.0.0"` + `cli/main.py:@click.version_option(version="2.0.0", ...)`. Décider stratégie : tag `v2.0.0` direct ou `v1.0.0` (commit historique antérieur ?) puis `v2.0.0`. → **antoine** (décision) + **claude-code** (exécution)
3. Implémenter `winboost/utils/admin.py` avec `is_admin()` (via `ctypes.windll.shell32.IsUserAnAdmin`) et `relaunch_as_admin()` (via `ShellExecuteW("runas", ...)`), branchement dans `apply` actions `requires_admin`. Alternative plus rapide : ajouter le manifest PyInstaller `uac_admin=True` (dans `build.py`) → tout le `.exe` réclame admin au lancement, plus simple, à valider produit. → **claude-code** (impl) + **antoine** (décision UX)
4. `ruff check winboost/ --fix` (35 fixes auto) + revue manuelle des 22 restantes (E501 sur les listes de chemins → soit `# noqa: E501` soit reformatage). → **claude-code**
5. Couvrir `winboost/ai/providers/*` à ≥80 % avec tests mockés (httpx pour Anthropic + OpenAI, urllib pour Ollama). → **claude-code**

Une fois ces 5 points faits, relancer ce même smoke test : si verdict = GO, Antoine peut tirer T029 + T061. Coverage GUI à 13-28 % et `mypy` non configuré restent acceptables comme dette technique post-release.

---

> Rapport produit en lecture/exécution seule. **Aucune modification de code** effectuée pendant ce smoke test (conformément à la consigne).
