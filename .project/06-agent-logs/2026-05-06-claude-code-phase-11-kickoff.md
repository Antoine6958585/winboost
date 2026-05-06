# Phase 11 — Kickoff v2.1 "Native Windows Actions + Hotkey overlay"

**Agent** : claude-code
**Date** : 2026-05-06
**Type** : kickoff/planning
**Source plan** : `C:/Users/Dezmen/.claude/plans/proud-weaving-walrus.md` (validé par Antoine 2026-05-06)

---

## Contexte

La Release v2.0.0 vient d'être publiée (commit `b46ff06`, tag `v2.0.0`, repo public). Phase 10 close et validée par antoine. Antoine a donné le go pour démarrer la phase 11 sans attendre T062 (Product Hunt, déféré en GTM future).

**Demande Antoine littérale** : "Mode focus, ferme Slack/Spotify, baisse luminosité, dark mode" → exécuté en une instruction.

Cette phase répond à cette demande **en étendant le registry d'actions** avec des actions Windows-natives qui n'existaient pas en v2.0 (luminosité, dark mode système, volume, bluetooth, focus assist…). Pas de MCP encore (c'est v2.2), pas de Computer Use (v2.3 conditionnel).

## Périmètre v2.1 (6 tâches T063 → T068)

| ID | Description | Effort | Statut |
|----|-------------|--------|--------|
| T063 | +30 actions YAML Windows-natives (brightness, dark_mode, volume, bluetooth, focus_assist, wifi, hdr, night_mode, sound_device, power_plan…) | ~6 h | not_started |
| T064 | Module `winboost/utils/windows_native.py` (helpers WMI/PowerShell partagés) | inclus T063 | not_started |
| T065 | Hotkey global Win+Espace → overlay texte (package `keyboard`) | ~3 h | not_started |
| T066 | Mode JSON CLI (`winboost chat --json`) | ~2 h | not_started |
| T067 | 30+ tests pour les nouvelles actions (unit + dry-run) | ~2 h | not_started |
| T068 | README + demo GIF de l'overlay | ~1 h | not_started |

**Total estimé** : ~14 h dev + tests.

## Décisions architecturales (déjà actées dans le plan, pas à redébattre)

1. **Voice coupé** — pas de Whisper/TTS, gimmick desktop, +200 Mo binaire pour ~5% usage
2. **Hotkey texte** plutôt que voix — 90% du wow factor pour 15% de l'effort
3. **Pas de MCP en v2.1** — c'est v2.2 (refactor monorepo 3 packages séparé)
4. **Pas de Computer Use en v2.1** — c'est v2.3 conditionnel + BYOK obligatoire
5. **Méthodes d'execution** : on s'appuie sur `powershell` et `registry_set` existants. Pas de nouvelle method dans le schema (évite invalidation de tous les YAML existants). Si besoin spécifique (WMI Brightness), c'est encapsulé dans un script PS one-liner ou un helper Python appelé via `powershell`.
6. **Compatibilité 8 modules + 150 actions v2.0** : aucun breaking change. Les nouveaux YAML sont additionnels.

## Plan d'exécution (ordre proposé)

1. **T063 + T064 ensemble** (le helper Python sert à factoriser les commandes PS répétitives des YAML)
   - Créer `winboost/utils/windows_native.py` avec helpers stateless (set_brightness, set_dark_mode, get_volume, set_volume, etc.)
   - Créer les 30 nouveaux YAML répartis :
     - `system/actions.yaml` (extension) : dark_mode, focus_assist, brightness, hdr, night_mode, power_plan, taskbar_align, transparency_effects, animations, mouse_speed (10)
     - `network/actions.yaml` (extension) : bluetooth_toggle, wifi_disconnect, hotspot_toggle, airplane_mode, ethernet_priority, dns_flush, network_reset, mtu_optimal, ipv6_disable, network_discovery (10)
     - `appearance/actions.yaml` (extension) : volume_set, mute_toggle, sound_device_default, system_sounds_off, accent_color, taskbar_color, lock_screen_image, wallpaper_set, font_size, hibernate_toggle (10)
2. **T067** : tests dry-run pour chaque nouvelle action (mock WMI + registry)
3. **T066** : flag `--json` sur `winboost chat` (sortie sérialisable du `RouteResult`)
4. **T065** : overlay hotkey (le plus complexe en pratique — package `keyboard`, fenêtre Tk transparente, focus auto)
5. **T068** : README + demo GIF (en dernier, capture l'écran fini)

## Risques connus

| Risque | Probabilité | Mitigation |
|--------|-------------|------------|
| WMI Brightness ne marche pas sur tous les écrans (ex: externes, dock) | Moyenne | Helper retourne `NotSupportedError`, l'action YAML log proprement |
| Package `keyboard` requiert admin sur certains systèmes | Moyenne | Fallback : raccourci dans GUI (cliqué) si hotkey global échoue |
| Hotkey ne capture pas en mode admin si app cible est aussi admin | Moyenne | Documenté, fallback bouton GUI |
| PowerShell scripts bloqués par execution policy | Faible | Toutes les commandes wrappées en `powershell -ExecutionPolicy Bypass -Command "..."` |

## Critères de réussite (recopiés du plan)

- [ ] +30 actions YAML mergées, schéma validé, 30+ tests passent
- [ ] Hotkey Win+Espace fonctionne dans 95 % des apps (test sur 10 apps : Chrome, VS Code, Slack, Spotify, Discord, Excel, Teams, OBS, Steam, Notion)
- [ ] `winboost chat --json` retourne du JSON parseable, schéma documenté
- [ ] Démo GIF dans le README

## Actions suivantes immédiates

1. Étendre `system/actions.yaml` avec les 10 premières actions (brightness + dark_mode + focus_assist + hdr + night_mode + power_plan + taskbar_align + transparency + animations + mouse_speed)
2. Créer `winboost/utils/windows_native.py` (helpers initiaux : `set_brightness`, `set_dark_mode`, `get_brightness`)
3. Créer `tests/actions/test_native_actions.py` (squelette + 5 premiers tests)
4. Commit incrémental par bloc cohérent (3-5 actions + leurs tests)

## Mises à jour status.yaml prévues à chaque commit

À chaque T063→T068 marqué `done` : update tâche + log dans `logs:` + recalcul progress.
