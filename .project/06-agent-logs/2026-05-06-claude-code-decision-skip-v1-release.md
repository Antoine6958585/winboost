# Décision : skip de la Release v1.0.0, une seule Release v2.0.0

**Date** : 2026-05-06
**Agent** : claude-code
**Tâche(s)** : T029 (skipped) — déblocage T061
**Demandé par** : Antoine

---

## Contexte

Après le verdict GO du Reality Checker RUN2, l'agent a soulevé un point que
le plan initial n'avait pas couvert : **on ne peut pas tirer 2 Releases
distinctes (v1.0.0 + v2.0.0) sur le même commit**. Le binaire compilé
indique `version 2.0.0` (bump effectué pendant la remédiation) — un tag
`v1.0.0` poserait sur ce commit créerait une incohérence visible immédiate
pour quiconque télécharge la "v1" et lit `WinBoost.exe --version`.

3 options ont été présentées à Antoine :
- **A** : skip v1.0.0, ne tirer que v2.0.0 (recommandé)
- **B** : tirer v1.0.0 sur un commit historique pré-phase 6 (build d'un commit ancien)
- **C** : rétro-bump (checkout pre-AI + bump à 1.0.0 + build + tag)

**Antoine a confirmé Option A.**

## Résultats

### Justifications de l'Option A

| Argument | Détail |
|----------|--------|
| Aucun utilisateur v1 | Le projet a été développé en un seul sprint en mars 2026, jamais publié, donc aucune communauté à "rétro-informer" |
| Cohérence du binaire | Le `.exe` build à partir de `main` actuel dit "2.0.0" — un tag v1.0.0 sur ce binaire crée une incohérence visible (`pip show winboost` → 2.0.0, mais Release dit v1) |
| Confusion repo public | 2 Releases simultanées sur un repo qui passe public le jour J → l'utilisateur lambda ne sait pas laquelle prendre |
| Historique préservé | Les commits de phase 1-5 (`dc7357b` → `38e0de4`) restent dans `git log`. Un curieux peut `git checkout 38e0de4 && python build.py` pour récupérer une v1 historique |
| Rapidité de ship | A = 5 min ; B = 30 min ; C = 45 min. La priorité est de débloquer Antoine après 6 semaines de stagnation |

### Changements apportés

| Fichier | Modification |
|---------|--------------|
| `status.yaml` | T029 → `status: skipped` + `skip_reason` documenté ; `progress: 97 → 98` (T029 retiré du décompte des tâches actives) |
| `TODO-HUMAN.md` | Section A (T029) remplacée par une note "SKIPPÉ" avec justification ; Section B (T061) enrichie avec verdict smoke test RUN2, étapes ordonnées (smoke test → repo public → tirer Release), template de description Release mis à jour avec les chiffres validés (382 tests, 91% coverage, 23 Mo) + mention honnête v2.0 (catalogue vs execution v2.1) |
| `MASTER-PLAN.md` | Pas de changement — la mention "v1.0 : Phases 1-5" reste vraie historiquement, juste pas de Release publique associée |

## Décisions prises

| Décision | Justification | Alternative rejetée |
|----------|---------------|---------------------|
| Skip v1.0.0 | Cf. table des justifications ci-dessus | Tirer v1 sur commit historique (effort + confusion) |
| Statut `skipped` plutôt que `cancelled` ou `won't fix` | "Skipped" est non-jugeant et précis : la tâche existait, on a décidé de ne pas la faire pour de bonnes raisons | "Cancelled" suggère un échec |
| Conserver T029 dans status.yaml plutôt que le supprimer | Traçabilité historique : on doit pouvoir comprendre dans 6 mois pourquoi v1.0.0 n'existe pas | Supprimer la tâche (perte d'historique) |
| Section A de TODO-HUMAN remplacée par une note explicative plutôt que supprimée | Idem traçabilité — un humain qui lit TODO-HUMAN doit comprendre l'état des 3 tâches initiales | Supprimer purement et simplement |
| Mention explicite dans le template de description Release : "v2.0 = catalogue, exécution réelle en v2.1" | Cohérent avec le slogan "ne te ment pas" + gère les attentes des early adopters | Glisser ce fait sous le tapis (mensonge produit) |

## Actions suivantes

### Immédiat (claude-code, cette session)
- [x] Update `status.yaml` (T029 skipped, progress 98)
- [x] Update `TODO-HUMAN.md` (section A → note skip, section B enrichie)
- [x] Ce log
- [ ] Commit + push

### Bloquant (Antoine, ~45 min)
- [ ] Smoke test humain (~15 min — étape 1 de TODO-HUMAN section B)
- [ ] Repo public + vérification LICENSE (~5 min — étape 2)
- [ ] Tirer Release v2.0.0 avec template prêt (~15 min — étape 3)
- [ ] Me dire "Release publiée" → sync `status.yaml` (~5 min — étape 4)

### Post-release (claude-code, sessions futures)
- [ ] Phase 11 — Native Windows Actions (T063 → T068, ~12-15 h dev)
- [ ] Phase 12 — MCP Standalone (T069 → T075, ~10-14 h dev)
- [ ] Phase 13 — Computer Use Pilot Mode (conditionnel, ~20-26 h dev)

### Post-release (Enzo)
- [ ] Brouillon Product Hunt (T062, ~3-4 h prépa) — section C de TODO-HUMAN

## Impact sur le projet

### Conformité Spine
- ✅ Règle n°1 : ce log
- ✅ Règle n°2 : décision prise dans le contexte projet (status + plan + smoke test)
- ✅ Honnêteté produit préservée jusque dans la description Release

### Métriques projet
- Total tâches livrées : 60 → 60 (T029 skipped ne change pas le décompte)
- Total tâches restantes (phase 10) : 3 → 2 (T029 sort du compte)
- Progress : 97 % → 98 %
- Une seule Release publique : v2.0.0

---

> Cette décision résout le dernier point de friction avant publication.
> Antoine est libre de tirer la Release v2.0.0 dès qu'il a fait son smoke
> test humain de 15 minutes.
