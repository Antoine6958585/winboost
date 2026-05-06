# Phase 13 v2.3 — Onglet Diagnose dans la GUI CustomTkinter

**Agent** : Frontend Developer (engineering-frontend-developer.md)
**Date** : 2026-05-06
**Type** : feature delivery (T084 — Diagnose GUI tab)

---

## Contexte

Antoine vient de resoudre son 1er bug DualSense via `winboost diagnose` en CLI
(cf. log `2026-05-06-claude-code-v2.3-dogfooding-3-options.md`). Le module
`winboost/diagnose/` est livre depuis 2026-05-06 (T083, Option C dogfooding) :
runner rules-based + 5 themes + DiagnosticReport + recommended_fix_plan.

Probleme : aucune integration GUI. L'utilisateur final doit ouvrir un terminal
pour declencher un diagnostic. Cette tache transforme WinBoost d'un outil dev
en outil grand public.

## Livrables

| Fichier | Lignes | Role |
|---------|--------|------|
| `winboost/gui/diagnose_page.py` | 567 | Page CustomTkinter — DiagnosePage + CheckResultCard + FixStepCard + ManualStepDialog |
| `winboost/gui/app.py` | +5 | Onglet "Diagnose" entre "Chat IA" et "Historique" |
| `tests/test_gui/test_diagnose_page.py` | 433 | 25 tests unitaires (CTk mocke) |

## Decisions UX

1. **Couleurs severity dediees**, distinctes des `RISK_COLORS` du chat (qui
   parlent de risque d'action). Ici on parle de severite *check* :
   - `ok` = `#27ae60` (vert)
   - `warning` = `#f39c12` (orange)
   - `error` = `#e74c3c` (rouge)
   - `critical` = `#9b59b6` (magenta)
2. **Threading via `threading.Thread`** + `self.after(0, ...)` pour les retours
   UI. Pendant le scan : bouton `disabled` + texte "Diagnostic en cours...",
   entree desactivee. Pas de double-scan possible (`_is_scanning` flag).
3. **4 exemples cliquables** qui *pre-remplissent* la zone de saisie sans
   declencher le scan — l'utilisateur peut ajuster la formulation. Couvrent
   les 5 themes (manette/BT, internet, son, ecran).
4. **Empty query** : message d'erreur affiche dans un label `_error_label`
   (cache par defaut), plutot que de griser le bouton (Tk gere mal la
   reactivite cross-event ; un message clair vaut mieux qu'un bouton inerte).
5. **CheckResultCard** : header avec badge severity colore + nom du check en
   mono + message wrappe. Bouton "Details" optionnel (visible uniquement s'il
   y a des `suggested_actions` ou `details` a montrer) qui expand un panel
   avec les actions suggerees + dump cle/valeur des `details`.
6. **FixStepCard** : 2 modes visuels distincts via badge :
   - `AUTO` (vert) avec bouton "Appliquer" -> `ActionExecutor.apply()`
   - `MANUEL` (orange) avec bouton "Voir details" -> popup `ManualStepDialog`
   Apres execution : badge OK/ERR + message en bas, bouton transforme en
   "Termine" disabled. Pas de re-tentative (l'utilisateur peut cliquer
   "Re-diagnostiquer" pour relancer le scan complet).
7. **ManualStepDialog** : Toplevel scrollable avec titre, check d'origine
   (mono), description longue, et section "Alternative" si presente. Permet
   d'afficher des descriptions multi-lignes (DS4Windows, Device Manager...)
   sans encombrer la carte principale.
8. **Lazy-load ActionRegistry** : on ne charge le registry qu'au 1er click
   "Appliquer" (souvent l'utilisateur regarde le rapport sans appliquer).

## Friction utilisateur identifiee et traitee

- **Diagnostic = 5-10s** : sans loader, l'UI semble freeze. Solution :
  spinner texte + label "Lancement des checks systeme... (5-10s typique)".
- **Re-scan apres fix** : un fix peut ne pas changer l'etat (admin requis,
  rollback). Solution : apres affichage du rapport, le bouton devient
  "Re-diagnostiquer" pour rappeler que c'est l'action attendue.
- **Plan de fix vide** : si aucun probleme, on affiche "Aucun fix necessaire"
  en vert plutot qu'une section vide.

## Tests (25 au total, >= 8 demandes)

Repartition :
- 4 tests d'import / palette / structure app.py
- 3 tests CheckResultCard (instanciation, badges, toggle details)
- 5 tests FixStepCard (apply auto, apply manuel, set_result success, set_result failure, defense action_id manquant)
- 4 tests interactions (empty query, valid query, ignore pendant scan, fill_example)
- 3 tests runner (call runner, exception handling, disable button)
- 1 test display rapport (clear + render)
- 3 tests apply_worker (success, registry miss, executor exception)
- 2 tests E2E soft avec DiagnosticRunner reel + theme stub

Pattern : `unittest.mock.patch` + `MagicMock`. Aucun test ne necessite de
display reel — coherent avec `tests/test_gui/test_chat.py` et
`tests/test_gui/test_hotkey_overlay.py`.

## Validation

```
python -m pytest tests/test_gui/test_diagnose_page.py -v --tb=short
   25 passed in 0.29s

python -m ruff check winboost/gui/diagnose_page.py tests/test_gui/test_diagnose_page.py winboost/gui/app.py
   All checks passed!

python -c "from winboost.gui.diagnose_page import DiagnosePage; print('OK')"
   OK

python -m pytest tests/ -q
   958 passed, 1 skipped in 38.53s   (vs 922 baseline avant T084)
```

Aucune regression sur les 933 tests existants.

## Limitations

- **Tests CTk en CI Linux** : `customtkinter` peut etre installe mais
  `tk.Tk()` echoue sans display. Notre approche `MagicMock` + `__new__`
  contourne le probleme — les 25 tests passent sans display reel. En CI
  Windows headless, meme garantie.
- **Aucune validation visuelle automatisee** : pas de screenshot test, pas
  d'integration avec un VRT (visual regression). Antoine validera in vivo
  via `winboost gui` -> onglet "Diagnose".
- **Pas de cancel pendant scan** : le diagnostic est I/O-bound (PowerShell)
  et dure 5-10s ; pas de bouton Cancel pour l'instant. Le thread est
  `daemon=True` donc shutdown propre a la fermeture de l'app.
- **Pas de history/persistance des diagnostics** : chaque scan ecrase le
  precedent. Un futur enrichissement pourrait stocker les rapports dans
  SQLite (HistoryManager existe deja pour les actions).

## Impact projet

- **Phase 13 progress** : T082 + T083 (Options A + C v2.3) avaient prepare
  le terrain. Cette tache (T084 implicite — pas encore au status.yaml)
  ferme la boucle GUI : utilisateur lambda peut lancer un diagnostic et
  appliquer les fix sans toucher au terminal.
- **Antoine peut tester son 2eme bug via la GUI** sans CLI.
- **Pas d'impact MCP/CLI** : la page se branche sur les modules existants
  (`DiagnosticRunner`, `ActionExecutor`, `ActionRegistry`) sans modifier
  leur contrat.

## Actions suivantes

1. Antoine : tester `python -m winboost gui` -> onglet Diagnose -> query
   "manette bluetooth" -> verifier visuel + click Apply sur un step auto.
2. Si OK : ajouter T084 dans status.yaml phase 13 + log de validation.
3. Si polish demande : couleurs accessibility (contraste WCAG AA),
   raccourci Ctrl+R pour relancer, tooltip sur les actions YAML.

## Decisions actees

- Pas de cancel button pour l'instant (5-10s de scan tolere par UX).
- Severity colors dedies plutot que reuse de RISK_COLORS — semantique
  differente (severite check != risque action).
- Apply en thread (consistance avec chat.py) + lazy-load registry.
