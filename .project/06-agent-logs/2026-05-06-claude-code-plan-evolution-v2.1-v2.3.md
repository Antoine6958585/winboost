# Plan validé — Évolution WinBoost v2.1 → v2.3 (Claude pilote le PC)

**Date** : 2026-05-06
**Agent** : claude-code (orchestrateur) + Plan agent (challenger)
**Tâche(s)** : meta — planification stratégique pour les phases 11, 12, 13
**Demandé par** : Antoine

---

## Contexte

Antoine a lancé une discussion d'amélioration produit autour des nouvelles
capacités Claude / Anthropic 2026 : permettre à Claude de **piloter directement
le PC Windows** (instruction simple texte ou voix, actions au-delà des 150
du registry, exemple cité : luminosité). Aussi orienté devs.

Le plan complet a été élaboré en 4 phases (Plan Mode) :
1. Cartographie du code existant via Explore agent (zones AI Engine, Action Registry, modules, surface d'exposition)
2. Draft initial : MCP n°1 + Voice n°2 + Computer Use n°3
3. **Challenge brutal par Plan agent** : 6 angles morts identifiés
4. Plan révisé + 4 arbitrages tranchés par Antoine

Plan complet sauvegardé : `C:/Users/Dezmen/.claude/plans/proud-weaving-walrus.md`

## Résultats

### Faille majeure découverte par le challenger

**Le draft initial priorisait MCP en n°1 — c'était égocentrique technique.**
La demande littérale d'Antoine ("Claude prend le contrôle du PC, modifier la
luminosité") n'est PAS couverte par MCP — elle nécessite des **actions
Windows-natives** dans le registry (luminosité WMI, dark mode registry, volume
PowerShell, Bluetooth PnP, focus assist, etc.).

→ Repriorisation : v2.1 = étendre l'Action Registry avec ~30 actions natives,
v2.2 = MCP standalone pour distribution massive, v2.3 = Computer Use conditionnel.

### 4 arbitrages validés par Antoine

| # | Arbitrage | Décision validée | Impact |
|---|-----------|------------------|--------|
| 1 | Voice (Whisper + TTS) | **Coupé** | Économie 14-18 h dev + ~200 Mo binaire. Remplacé par hotkey Win+Espace overlay texte (~3 h). |
| 2 | Structure MCP | **Monorepo 3 packages** | `winboost-core` + `winboost-gui` + `winboost-mcp`. Distribution massive via registres MCP. +4 h refactor. |
| 3 | Pricing Pro | **9,99 €/mois** (vs 4,99 €) | Absorbe coûts futurs Computer Use + finance distribution MCP. Aligné Cursor/Claude Pro. |
| 4 | Computer Use | **v2.3 conditionnel + BYOK obligatoire** | Protège unit economics ($0.05-0.15/tâche) + clarifie RGPD (screenshots vers Anthropic US). Construit seulement si v2.1+v2.2 traction. |

### Phasage final

| Version | Capacité | Effort dev | Quand |
|---------|----------|-----------|-------|
| **v2.0** | Ship existant tel quel | 0 (déjà fait) | NOW — bloque sur Antoine pour les Releases GitHub |
| **v2.1** | +30 actions Windows-natives + hotkey overlay texte + mode JSON CLI | ~12-15 h | Après ship v2.0 |
| **v2.2** | Refactor monorepo + winboost-mcp standalone (FastMCP, distribution registres) | ~10-14 h | Après v2.1 stable |
| **v2.3** | Computer Use Pilot Mode (BYOK, opt-in expert) | ~20-26 h | Conditionnel : ≥ 500 stars + 100 Pro + demande explicite |

### Risques identifiés (challenge agent)

1. **PyInstaller + MCP stdio** : asyncio + stdin/stdout binaire non garanti compatible PyInstaller
2. **Computer Use multi-DPI Windows** : Claude entraîné sur Ubuntu, coordonnées off de 5-15 px sur scaling 125 %/150 %
3. **RGPD Computer Use** : screenshots vers Anthropic US → risque CNIL si pas opt-in granulaire
4. **Unit economics Computer Use** : ~$30/mois user à 20 tâches/jour → Pro 4,99 € impossible (mitigé par BYOK + Pro 9,99 €)
5. **Hotkey global vs UAC admin** : ne marche pas dans apps élevées (VS, Docker Desktop)

## Décisions prises

| Décision | Justification | Alternative rejetée |
|----------|---------------|---------------------|
| Étendre Action Registry AVANT MCP | Demande littérale Antoine = actions natives, pas wrapper protocole | MCP en priorité 1 (égocentrique technique) |
| Monorepo 3 packages | Distribution dev frictionless via registres MCP, le `.exe` GUI reste pur | Module MCP intégré (taille, friction) |
| Voice coupé | 5 % usage desktop + 200 Mo binaire = ROI négatif | Inclure Voice par crainte de manquer un use case |
| Pricing Pro 9,99 € | Absorbe coûts futurs + aligne marché | Garder 4,99 € (déficit Computer Use structurel) |
| Computer Use BYOK obligatoire | Protège unit economics + clarifie RGPD | Inclus dans Pro (déficitaire + risque CNIL) |
| Computer Use v2.3 conditionnel | Mesurer traction MCP + actions natives d'abord | Roadmap CU ferme dès maintenant |
| Ship v2.0 d'abord | Risque #1 réel = release pas tirée, pas le choix d'archi | Coder v2.1 en parallèle (over-engineering masqué en planning) |

## Actions suivantes

### Immédiat (claude-code, cette session)
- [x] Plan complet validé et écrit
- [x] Ce log
- [ ] Enrichir `.project/MASTER-PLAN.md` — section "Évolution post-v2.0"
- [ ] Enrichir `ROADMAP.md` — phases 11, 12, 13 prévisionnelles
- [ ] Mettre à jour `status.yaml` — ajouter phases 11-13 avec tâches `not_started`
- [ ] Créer prompt `.project/02-prompts/phase-11-native-windows-actions.md`
- [ ] Créer prompt `.project/02-prompts/phase-12-mcp-standalone.md`
- [ ] Pas de prompt v2.3 (conditionnel — sera créé si déclenché)
- [ ] Commits structurés + push

### Bloquant (Antoine)
- [ ] Tirer Releases v1.0.0 + v2.0.0 (T029 + T061) — voir `TODO-HUMAN.md`
- [ ] Décider du jour J du repo public + ajout LICENSE MIT
- [ ] Confirmation explicite de la nouvelle grille pricing (Free / Pro 9,99 € / Lab BYOK)

### Post-ship v2.0 (claude-code, sessions futures)
- [ ] Démarrer phase 11 via prompt dédié
- [ ] Phase 12 après stabilisation phase 11
- [ ] Mesure 8-12 semaines avant décision phase 13

## Impact sur le projet

### Fichiers à créer (cette session)
- `.project/06-agent-logs/2026-05-06-claude-code-plan-evolution-v2.1-v2.3.md` (ce fichier)
- `.project/02-prompts/phase-11-native-windows-actions.md`
- `.project/02-prompts/phase-12-mcp-standalone.md`

### Fichiers à modifier (cette session)
- `.project/MASTER-PLAN.md` — ajout section "Évolution post-v2.0"
- `ROADMAP.md` — ajout phases 11, 12, 13
- `status.yaml` — ajout des phases avec ~25 nouvelles tâches `not_started`

### Fichiers à NE PAS modifier (volontairement)
- Tout le code Python — interdiction de coder v2.1 avant ship v2.0
- `pyproject.toml` — pas encore de refactor monorepo

### Conformité Spine
- ✅ Règle n°1 : ce log
- ✅ Règle n°2 : plan a été élaboré avec triangle de contexte (Spine + projet WinBoost + mission Antoine)
- ✅ Plan persisté dans `~/.claude/plans/proud-weaving-walrus.md`

---

> Plan stratégique de l'évolution Claude-pilote-PC validé. Implémentation suspendue
> jusqu'au ship v2.0 par Antoine. Prompts de phase 11 et 12 préparés à
> l'avance pour invocation propre dès que possible.
