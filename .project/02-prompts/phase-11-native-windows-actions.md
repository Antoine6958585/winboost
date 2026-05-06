# Phase 11 — Native Windows Actions + Hotkey Overlay (v2.1)

> Prompt d'invocation prêt à utiliser **après** que Antoine ait tiré les Releases
> v1.0.0 + v2.0.0 sur GitHub. Ne pas démarrer avant.
>
> Tâches couvertes : T063 → T068
> Effort estimé : 12-15 h dev
> Plan source : `C:/Users/Dezmen/.claude/plans/proud-weaving-walrus.md`

---

## Identité Spine

Lis et applique comme system context :

`A:/dev/spine/_agents/development/backend-developer.md`
*(ou Backend Architect en subagent_type natif si l'agent Spine n'existe pas)*

L'agent travaille en mode **TDD strict** (tests d'abord, puis implémentation),
aligné avec le standard du projet WinBoost (320 tests existants, 80 % coverage).

## Contexte projet

Lis dans cet ordre :

1. `A:/dev/winboost/CLAUDE.md` — règles produit (notamment 7 règles sécurité)
2. `A:/dev/winboost/status.yaml` — phases 11-13 ajoutées le 2026-05-06
3. `A:/dev/winboost/.project/MASTER-PLAN.md` — section "Évolution post-v2.0"
4. `A:/dev/winboost/.project/03-specs/architecture.md`
5. `A:/dev/winboost/.project/06-agent-logs/2026-05-06-claude-code-plan-evolution-v2.1-v2.3.md`
6. `A:/dev/winboost/winboost/actions/loader.py` — pour comprendre le schéma YAML
7. `A:/dev/winboost/winboost/actions/privacy/actions.yaml` — exemple de pattern existant
8. `A:/dev/winboost/winboost/ai/action_router.py` — pipeline existant
9. `A:/dev/winboost/winboost/cli/main.py` — pour modifier la CLI

## Mission

Étendre WinBoost pour répondre **littéralement** à la demande Antoine :
"Claude pilote le PC, modifie la luminosité, le dark mode, etc."

### T063 — +30 actions YAML Windows-natives (~6 h)

Crée les fichiers YAML suivants dans `winboost/actions/system/` (et `network/` pour wifi) :

| Action | Méthode d'exécution | Fichier YAML |
|--------|---------------------|--------------|
| `system_brightness_up_30` | `powershell` invoquant `WmiMonitorBrightnessMethods.WmiSetBrightness` | `system/brightness.yaml` |
| `system_brightness_down_30` | idem | `system/brightness.yaml` |
| `system_brightness_set_50` | idem (param `value`) | `system/brightness.yaml` |
| `system_dark_mode_on` | `registry_set` `HKCU\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize\AppsUseLightTheme=0` | `system/dark_mode.yaml` |
| `system_dark_mode_off` | inverse | `system/dark_mode.yaml` |
| `system_volume_mute` | `powershell` `(New-Object -ComObject WScript.Shell).SendKeys([char]173)` | `system/volume.yaml` |
| `system_volume_set_50` | `powershell` `[Audio]::Volume = 0.5` (helper class) | `system/volume.yaml` |
| `system_volume_up_10` / `down_10` | idem | `system/volume.yaml` |
| `system_bluetooth_off` | `powershell` `Get-PnpDevice -Class Bluetooth \| Disable-PnpDevice` | `system/bluetooth.yaml` |
| `system_bluetooth_on` | inverse | `system/bluetooth.yaml` |
| `system_focus_assist_priority_only` | `registry_set` `HKCU\Software\Microsoft\Windows\CurrentVersion\Notifications\Settings\Windows.SystemToast.QuietHours\NOC_GLOBAL_SETTING_TOASTS_ENABLED=0` | `system/focus_assist.yaml` |
| `system_focus_assist_off` | inverse | `system/focus_assist.yaml` |
| `system_night_light_on` | `powershell` registry NightLight | `system/night_light.yaml` |
| `system_night_light_off` | inverse | `system/night_light.yaml` |
| `system_hdr_on` / `off` | `powershell` HDR toggle | `system/hdr.yaml` |
| `system_sound_output_speaker` / `headphone` | `powershell` `Set-AudioDevice` (PowerShell module AudioDeviceCmdlets) | `system/sound_device.yaml` |
| `system_power_plan_high` / `eco` / `balanced` | `cmd` `powercfg /setactive <GUID>` | `system/power_plan.yaml` |
| `network_wifi_connect_<ssid>` | `cmd` `netsh wlan connect name=<ssid>` (template, params dynamiques) | `network/wifi_switch.yaml` |
| `network_wifi_disconnect` | `cmd` `netsh wlan disconnect` | `network/wifi_switch.yaml` |
| `network_wifi_off` / `on` | `powershell` `Disable-NetAdapter -Name "Wi-Fi"` | `network/wifi_switch.yaml` |

Chaque action doit avoir : `id`, `name`, `description`, `category`, `risk_level`,
`execute` (avec `method` et `params`), `rollback` si applicable, `keywords` FR + EN,
`requires_admin: bool`, `reversible: bool`.

### T064 — `winboost/utils/windows_native.py` (~2 h)

Module de helpers pour les méthodes complexes :
- `set_brightness(percent: int) -> bool` (WMI)
- `get_brightness() -> int`
- `set_volume(percent: int) -> bool`
- `toggle_bluetooth(enable: bool) -> bool`
- `toggle_dark_mode(enable: bool) -> bool`
- `set_power_plan(plan: Literal["high", "eco", "balanced"]) -> bool`

Tests unitaires associés avec mocks WMI.

### T065 — Hotkey global Win+Espace → overlay texte (~3 h)

Nouveau fichier `winboost/ui/hotkey_overlay.py` :
- Listener via package `keyboard` (combinaison `win+space`)
- Mini fenêtre Tk transparente, top-most, focus auto sur input text
- Esc pour fermer, Entrée pour soumettre
- Soumet le prompt à `ActionRouter.route()`, affiche le résultat dans la même fenêtre
- Boutons inline "Apply" / "Cancel" pour les actions retournées
- Configurable dans Settings (changer le hotkey, désactiver)

**Limite documentée** : ne marche pas dans les apps lancées en admin (UAC) sauf si
WinBoost lui-même tourne en admin. Documenter dans le README.

### T066 — Mode JSON CLI (~2 h)

Modifier `winboost/cli/main.py` :
- Ajouter `--json` flag à `winboost chat`
- Si présent : sortir `RouteResult` sérialisé en JSON sur stdout, supprimer toute autre sortie
- Schéma JSON documenté dans le README + dans une dataclass `RouteResultJSON`
- Tests : `winboost chat "test" --json | jq .` doit parser sans erreur

### T067 — Tests (~2 h)

- 30+ tests unitaires pour les nouvelles actions (1 par YAML, dry-run vérifié)
- Tests pour `windows_native.py` avec mocks
- Tests pour hotkey overlay (mock keyboard listener)
- Tests pour mode JSON (parsing du schéma)
- Coverage cible : ≥ 80 % sur les nouveaux modules

### T068 — Doc (~1 h)

- README mis à jour : section "Actions Windows-natives" + "Hotkey Win+Espace"
- GIF de démo de l'overlay (10 s)
- Mise à jour `winboost --help`

## Livrable obligatoire

À la fin de la phase, écrire un log dans :
```
A:/dev/winboost/.project/06-agent-logs/{DATE}-{agent}-phase-11-native-windows-actions.md
```

Avec :
- Résumé des 30 actions ajoutées (avec leur risk_level)
- Issues rencontrées (notamment compatibilité Windows 10 vs 11 sur certaines actions)
- Métriques : nombre total d'actions dans le registry, nombre total de tests
- Verdict : prêt pour phase 12 ou besoin de revisiter ?

Mise à jour `status.yaml` : T063 → T068 en `done`, log entry ajoutée.
Commit + push : `feat: phase 11 — native Windows actions + hotkey overlay`.

## Non-négociable

- Pas de fichier écrit = travail non fait (règle Spine n°1)
- TDD strict : tests AVANT implémentation
- Aucune action `risk_level: critical` sans confirmation explicite Antoine
- Pas de modification du code existant en dehors des fichiers nécessaires
- Toutes les actions doivent passer par SafetyEngine (pas de bypass)
