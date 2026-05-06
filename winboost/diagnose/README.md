# winboost.diagnose — Diagnostics systemiques rules-based

## Pourquoi

Avant de lancer un chat IA ou d'executer des actions YAML aveuglement,
WinBoost peut **diagnostiquer** un sous-systeme Windows en ~3-5 secondes via
des checks scriptes. Le module `winboost.diagnose` expose une API simple :

```python
from winboost.diagnose.runner import DiagnosticRunner

runner = DiagnosticRunner()
report = runner.run_from_query("ma manette bluetooth bug dans rocket league")

print(report.summary)
# Exemple : "1 erreur(s), 2 warning(s) detecte(s) : Service bthserv arrete | ..."

for step in report.recommended_fix_plan:
    print(f"  Etape {step['step']}: {step['description']}")
```

## Architecture

```
winboost/diagnose/
├── __init__.py              # exports publics
├── runner.py                # DiagnosticRunner + DiagnosticReport
├── checks.py                # Check base, CheckResult, Severity, helpers PS
└── themes/
    ├── __init__.py
    ├── bluetooth.py         # 5 checks BT (use case Antoine: manette RL)
    ├── gaming.py            # 5 checks XInput / Xbox driver / Steam
    ├── network.py           # 5 checks adapter / DNS / gateway
    ├── audio.py             # 5 checks Audiosrv / endpoints / drivers
    └── display.py           # 5 checks brightness / GPU / resolution
```

## Concepts

### `Severity`
Enum stringifiable : `ok | warning | error | critical`.

### `CheckResult`
Dataclass immuable retournee par chaque check :
- `name` : ID stable du check (ex: `"bluetooth_service_status"`)
- `severity` : niveau de gravite
- `message` : message court FR
- `details` : raw data pour debug
- `suggested_actions` : tuple d'IDs YAML qui peuvent fixer (ex: `("net_011", "net_012")`)

### `Check`
Classe de base. Sous-classer puis implementer `run() -> CheckResult`. Le
runner utilise `safe_run()` qui encapsule les exceptions (`WindowsNativeError`
devient `severity=warning` au lieu de crasher tout le rapport).

### `DiagnosticReport`
Dataclass immuable contenant la trace complete + le plan de fix.
- `theme` : str (ex: `"bluetooth"` ou `"bluetooth+gaming"`)
- `query` : la requete originale
- `timestamp` : datetime UTC
- `checks` : tuple de CheckResult
- `summary` : phrase courte FR
- `recommended_fix_plan` : tuple de dicts ordonnes par severite
- `to_dict()` / `to_json()` : serialisation

## Matching de theme

`run_from_query(query)` parse la requete et matche un ou plusieurs themes
via `THEME_KEYWORDS`. Une requete polymorphe (ex: "manette bluetooth dans
rocket league") matche **plusieurs** themes (`bluetooth` + `gaming`) et
fusionne les rapports en un seul.

Si aucun keyword ne matche, le fallback est `bluetooth` (use case principal).

## Plan de fix

Les `suggested_actions` de chaque check sont aggreges :
1. Tries par severite (critical -> error -> warning)
2. Dedoublonnes (un meme action_id n'apparait qu'une fois)
3. Decrits via le catalogue `_ACTION_DESCRIPTIONS` + le message du check

Si un check problematique n'a pas de `suggested_actions`, une etape
**manuelle** est ajoutee au plan (`{"manual": True, ...}`).

## Ajouter un theme

1. Creer `winboost/diagnose/themes/{nom}.py`
2. Definir N classes heritant de `Check`, chacune avec `name` unique et `run()`
3. Exposer `get_checks() -> list[Check]`
4. Enregistrer dans `runner.py` :
   ```python
   from winboost.diagnose.themes import nouveau_theme

   THEME_REGISTRY["nouveau"] = nouveau_theme.get_checks
   THEME_KEYWORDS["nouveau"] = ("kw1", "kw2")
   ```
5. Ajouter les tests dans `tests/test_diagnose/test_themes.py`

## Limitations connues

- Les checks PowerShell sont sensibles a la locale (formats de date). Le
  parsing tolere ISO / US / EU mais peut louper des locales exotiques.
- Le check `display_hdr_support` est un proxy approximatif (compter les
  moniteurs WMI). Une detection HDR fiable demande Win32 API DXGI.
- Les checks `*_driver_freshness` ne distinguent pas un "vieux driver
  mais stable" d'un "vieux driver bugge". Le seuil est volontairement
  conservateur (1 an pour GPU, 2 ans pour BT/audio, 3 ans pour Xbox).
- Certains checks (PnP avec `-PresentOnly:$false`) peuvent demander des
  droits eleves sur certaines installations. Le `safe_run()` produit alors
  un warning au lieu de crasher.
