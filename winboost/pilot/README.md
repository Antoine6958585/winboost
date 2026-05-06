# `winboost.pilot` — Computer Use Pilot Mode (v2.3, Lab tier)

> **Statut : pre-implementation v2.3.** Le module est livre mais l'integration GUI complete (Settings + executor pyautogui) reste a faire en T081. Le pilot tourne deja en CLI/test avec un confirmer mocke.

Le module `winboost.pilot` permet a Claude de **piloter visuellement** ton PC via l'API Anthropic Computer Use. Il prend des screenshots, analyse l'ecran, propose une action (clic, frappe clavier, etc.), te montre une preview annotee, et n'execute QUE si tu confirmes.

## Quand l'utiliser

Cas d'usage canonique : ta **manette Bluetooth bug** dans ton jeu favori. Plutot que de naviguer toi-meme dans Device Manager + Services + Bluetooth Settings, tu lances :

```python
pilot.run("ma manette Bluetooth bug dans Rocket League")
```

Et le pilot va, par lui-meme :

1. Capturer ton ecran
2. Comprendre le contexte (Rocket League ouvert, manette dans Devices)
3. Proposer **etape 1** : ouvrir Settings Bluetooth
4. Te demander de confirmer (preview du clic en rouge sur l'ecran annote)
5. Cliquer si tu confirmes
6. Capturer le nouvel ecran
7. Proposer **etape 2** : verifier le statut de la manette
8. ...
9. Boucler jusqu'a resolution OU echec OU `Esc` (cancel global) OU plafond budgetaire

## Garde-fous (NON-NEGOCIABLES)

| # | Garde-fou | Pourquoi |
|---|-----------|----------|
| 1 | **BYOK Anthropic** obligatoire | C'est ton argent, tu paies tes propres tokens |
| 2 | **Profil Lab** requis | Separation stricte du Pro standard, c'est experimental |
| 3 | **Notice RGPD + opt-in granulaire** | Les screenshots partent vers les serveurs Anthropic (US, hors UE) |
| 4 | **Plafond mensuel hard** (default 5 EUR) | Pas de derive economique silencieuse |
| 5 | **Confirmation visuelle a chaque action** | Aucun mode "trust me, just do it" |
| 6 | **Sandbox d'ecran** | Le pilot ne voit/touche que la zone autorisee |
| 7 | **Plafond 5 actions consecutives** | Re-confirmation obligatoire ensuite |
| 8 | **Audit trail SQLite + screenshots locaux** | Tu peux re-tracer apres coup |
| 9 | **Cancel global immediat** (`pilot.stop()`) | Sortie d'urgence |

## Notice RGPD (lis avant d'activer)

L'utilisation du Pilot envoie les donnees suivantes a l'API Anthropic :

- **Screenshots** de la zone Sandbox (image PNG)
- **Texte OCR** que Claude infere des screenshots
- **System info** que tu fournis dans le prompt initial

L'API Anthropic est hebergee aux **Etats-Unis** (datacenters AWS US-East principalement). En tant qu'utilisateur europeen, tu transferes des donnees personnelles **hors UE**. Les conditions :

- Anthropic conserve les requetes selon ses TOS (typiquement 30 jours, peut etre 0 jour avec ZDR si tu es eligible)
- L'IP source de tes requetes est connue d'Anthropic (la tienne, le BYOK est direct)
- Tu peux a tout moment supprimer ta cle API et tes screenshots locaux

**Tous les screenshots restent egalement stockes localement** pour audit (`%LOCALAPPDATA%\WinBoost\pilot_screenshots\`). Aucun upload cloud autre qu'Anthropic.

### Opt-in granulaire (3 cases a cocher)

Pour activer le Pilot, ta config doit avoir :

```json
{
  "profile": "lab",
  "pilot": {
    "rgpd": {
      "screenshots": true,
      "ocr_text": true,
      "system_info": true,
      "accepted_at": "2026-05-06T12:34:56Z"
    }
  }
}
```

Si une seule de ces cases est `false` ou absente -> `RGPDNotAcceptedError` et le pilot ne demarre pas.

## Installation

```bash
pip install winboost[pilot]
```

Cela ajoute :

- `anthropic>=0.40` (SDK officiel)
- `Pillow>=10.0` (annotation des screenshots)
- `pyautogui>=0.9.54` (executor par defaut, optionnel)

## Usage

### Niveau API Python

```python
from winboost.core.config import Config
from winboost.core.history import HistoryManager
from winboost.pilot import (
    AnthropicPilot,
    BudgetManager,
    ConfirmationManager,
    Sandbox,
)
from winboost.pilot.sandbox import Region

config = Config()
config.set("profile", "lab")
config.set("pilot", {
    "rgpd": {
        "screenshots": True,
        "ocr_text": True,
        "system_info": True,
        "accepted_at": "2026-05-06T12:34:56Z",
    },
})
config.save()

# Sandbox restreinte a la fenetre principale (1280x800 a coords (100,100))
sandbox = Sandbox(
    mode="application",
    region=Region(100, 100, 1280, 800),
    max_consecutive_actions=5,
)

# Plafond mensuel : 5 EUR (default)
budget = BudgetManager()
print(f"Reste ce mois : {budget.remaining_eur:.2f} EUR")

# Confirmer GUI Tk (a brancher en T081, ici on suppose deja fait)
from winboost.gui.pilot_dialog import build_tk_confirmer  # placeholder T081
confirmer = ConfirmationManager(confirmer=build_tk_confirmer())

# Audit trail
history = HistoryManager()

# Screenshot provider et executor (en T081, livres par la GUI)
from winboost.gui.pilot_executor import (
    capture_sandbox,
    execute_action,
)

pilot = AnthropicPilot(
    api_key=os.environ["ANTHROPIC_API_KEY"],
    config=config,
    sandbox=sandbox,
    confirmation=confirmer,
    budget=budget,
    history=history,
    screenshot_provider=capture_sandbox,
    action_executor=execute_action,
    model="claude-opus-4-7",
)

result = pilot.run("ma manette Bluetooth bug dans Rocket League")

print(f"Iterations : {result.iterations}")
print(f"Cout total : {result.total_cost_eur:.4f} EUR")
print(f"Termine ? {result.completed} (raison: {result.abort_reason})")
for action in result.actions:
    print(f"  iter {action.iteration} : {action.proposed.short_label()} "
          f"-> {action.decision} (executee: {action.executed})")
```

### Cancel global

```python
# Depuis un thread UI (Esc binding par exemple) :
pilot.stop()
```

Le loop sort proprement avec `result.abort_reason == "user_stop"`.

## Scenario canonique : manette Bluetooth qui bug

Ce scenario doit fonctionner end-to-end :

1. **User** : "ma manette Bluetooth bug dans Rocket League"
2. **Pilot** : capture screenshot du bureau
3. **Claude** propose : `click(450, 1000)` (icone Demarrer)
   - **Rationale** : "Pour ouvrir le menu Demarrer et acceder a Settings"
   - **Preview** : screenshot annote avec rectangle rouge sur l'icone
4. **User** : confirme
5. **Pilot** : execute le clic, capture nouveau screenshot
6. **Claude** propose : `type("bluetooth")` puis `key("Enter")`
   - **Rationale** : "Pour rechercher Bluetooth Settings"
7. **User** : confirme (et clique "autoriser 3 suivantes" pour eviter la fatigue)
8. **Pilot** : execute, batch de 3 = autorise sans re-confirmer
9. ...
10. **Claude** detecte la manette en grise dans Devices, propose un toggle Bluetooth Off/On
11. ...
12. **Claude** : "La manette est de retour. Je peux relancer Rocket League ?"
13. **User** : confirme
14. **Pilot** : execute, fin de loop (`completed=True`, `stop_reason='end_turn'`)

## Limitations connues

### SDK Anthropic Computer Use

Au moment ou ce module est ecrit (2026-05), l'API Computer Use d'Anthropic est en **public beta**. Le client `anthropic.Anthropic.beta.messages.create(...)` accepte le tool `computer_20250124` avec le header beta `computer-use-2025-01-24`. Si l'API stabilise et change la signature, ce module devra etre mis a jour. Le `client_factory` injectable permet de patcher facilement sans toucher au coeur du loop.

### Modeles supportes

- `claude-opus-4-7` (default) -- meilleure qualite, plus cher
- `claude-sonnet-4-6` (alias `claude-sonnet-4-20250514`) -- bon compromis cout/qualite

Si tu utilises un modele non liste dans `MODEL_PRICING`, le fallback est `claude-sonnet-4-6` (estimation prudente du cout).

### Screenshot provider et executor

Ce module **ne capture pas l'ecran lui-meme** et **n'execute pas les clics lui-meme**. Il faut fournir :

- `screenshot_provider: (Sandbox) -> bytes` : capture la zone autorisee
- `action_executor: (ProposedAction) -> None` : execute clic/type/key

C'est volontaire : on garde `winboost/pilot/` libre de toute dependance UI/OS lourde. La couche GUI (T081) fournit ces deux callables. En tests, ils sont mockes.

### Pas de batch sans validation initiale

Meme si l'utilisateur clique "autoriser 5 suivantes", la sandbox `check_can_act()` continue d'appliquer. Si le plafond consecutif est atteint au milieu d'un batch, le loop se met en pause et redemande une confirmation explicite (synthese : `kind="wait"`).

### Pas de mode totalement headless en production

Le confirmer par defaut leve `NotImplementedError`. Si tu cables `make_yes_confirmer()` en production, tu CONTOURNES sciemment la securite -- ce helper existe **uniquement pour les tests**. Le pilot detecte mais ne peut pas l'empecher : c'est ta responsabilite.

## Architecture interne

```
winboost/pilot/
├── __init__.py            # Lazy proxies, pas d'import lourd
├── anthropic_pilot.py     # AnthropicPilot, le loop principal
├── budget.py              # BudgetManager + MODEL_PRICING + reset mensuel auto
├── confirmation_ui.py     # ConfirmationManager + ProposedAction + helpers tests
└── sandbox.py             # Sandbox + Region + SandboxViolationError
```

Decoupage par responsabilite (SRP) :

- **Budget** ne sait rien de l'ecran ni de la confirmation ;
- **Sandbox** ne sait rien des couts ni de l'API ;
- **Confirmation** ne sait rien des limites ni du budget ;
- **AnthropicPilot** est le seul a orchestrer les 4 et appeler l'API.

## Tests

```bash
pytest tests/test_pilot/ -v
```

23 tests couvrent :

- Validation BYOK / profil Lab / RGPD opt-in
- Plafond mensuel et reset automatique
- Plafond consecutif sandbox
- Annotation screenshot (Pillow)
- Audit trail HistoryManager
- Telemetrie tokens (mock Anthropic)
- Sandbox violations (clic hors zone, full_screen sans flag)
- Cancel global (`pilot.stop()`)
- Sequencement allow_batch
- Serialisation PilotResult.to_dict
- Reset mensuel via clock injectable

Aucun appel reseau reel en CI : le `client_factory` est entierement mocke.

## Roadmap

| Tache | Status | Owner |
|-------|--------|-------|
| T076 module `winboost/pilot/anthropic_pilot.py` | done | claude-code |
| T077 sandbox + zone configurable | done | claude-code |
| T078 confirmation visuelle obligatoire | done | claude-code |
| T079 BYOK + plafond mensuel | done | claude-code |
| T080 notice RGPD + opt-in granulaire | done | claude-code (notice) + antoine (UI Settings) |
| T081 tier Lab + integration GUI Settings | not_started | claude-code (en T081 v2.3 GUI) |

## Contact

Bug ou question sur le Pilot : ouvre une issue avec le tag `pilot/v2.3`.
Pour les sujets RGPD : [contact@genlead.fr](mailto:contact@genlead.fr).
