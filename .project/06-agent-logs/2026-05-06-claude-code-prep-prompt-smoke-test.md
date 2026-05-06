# Préparation du prompt Pre-Release Smoke Test

**Date** : 2026-05-06
**Agent** : claude-code
**Tâche(s)** : meta — préparation pour T029/T061 (releases)
**Demandé par** : Antoine

---

## Contexte

Antoine a demandé si Claude Code peut faire le smoke test pré-release à sa place.
Réponse : oui à ~85 %. Les 15 % restants (validation visuelle GUI, UX chat, test
sur machine vierge) restent à charge humaine — c'est le bon split.

Pour permettre une exécution propre par un agent dédié (au lieu de mélanger ça
avec d'autres tâches dans une session généraliste), on prépare un prompt
dédié dans `.project/02-prompts/pre-release-smoke-test.md`.

## Résultats

### Livrable produit
- `A:/dev/winboost/.project/02-prompts/pre-release-smoke-test.md` — prompt complet
  - Triangle de contexte (règle n°2) intégré : identité Spine + couche projet + mission
  - 20 tests automatisables détaillés avec critères de réussite chiffrés
  - Liste explicite des tests humains à charge d'Antoine
  - Structure imposée du rapport de sortie
  - Critères "non négociables" pour éviter un GO silencieux

### Choix d'agent
Agent recommandé : **Reality Checker** (subagent_type natif).
Justification : "Default to NEEDS WORK, requires overwhelming proof for production
readiness" — exactement le profil voulu pour une release publique.
Fallback : **Evidence Collector**.

## Décisions prises

| Décision | Justification | Alternative rejetée |
|----------|---------------|---------------------|
| Smoke test dans une session Claude Code dédiée | Séparation propre de la charge cognitive, log dédié | Mélanger avec d'autres tâches |
| Agent Reality Checker plutôt qu'API Tester ou Performance Benchmarker | API Tester = APIs HTTP. Performance Benchmarker = bench, pas QA. Reality Checker est le seul qui défaut à NO-GO. | API Tester (mauvais scope) |
| **Lecture/exécution seule, pas de modif code** | Si bug trouvé, on le rapporte mais on le corrige dans une SESSION SÉPARÉE | Laisser l'agent patcher au passage (pollution de scope) |
| 20 tests numérotés avec critères chiffrés | Évite l'ambiguïté "ça marche à peu près" | Description en prose |
| Liste explicite des tests humains | Antoine doit savoir ce qui reste à sa charge — pas de zone grise | Implicite |

## Actions suivantes

- [x] Créer le prompt
- [x] Écrire ce log
- [ ] **Antoine** : invoquer l'agent (commande dans `TODO-HUMAN.md` ou directement
      dans une session Claude Code à la racine du projet WinBoost)
- [ ] L'agent invoqué écrira son propre log dans `06-agent-logs/`
- [ ] Si verdict GO : Antoine tire les releases (T029 + T061)
- [ ] Si verdict NO-GO : nouvelle session pour fixer + re-run du smoke test

## Impact sur le projet

### Fichiers créés
- `.project/02-prompts/pre-release-smoke-test.md`
- `.project/06-agent-logs/2026-05-06-claude-code-prep-prompt-smoke-test.md` (ce fichier)

### Fichiers NON modifiés
- `status.yaml` — pas de nouvelle tâche, c'est de la prep pour T029/T061 existantes
- Code — hors scope

### Conformité Spine
- ✅ Règle n°1 : ce log
- ✅ Règle n°2 : le prompt produit suit le triangle de contexte (Spine + projet + mission)
