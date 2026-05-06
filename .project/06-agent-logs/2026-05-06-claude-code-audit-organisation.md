# Audit organisation WinBoost — Mise en conformité règles Spine n°1 et n°2

**Date** : 2026-05-06
**Agent** : claude-code
**Tâche(s)** : meta — pas de TID dédié (tâche d'organisation)
**Demandé par** : Enzo

---

## Contexte

Demande explicite d'Enzo : *"fais une mise à jour du projet pour tout ce qui est
organisation règle n°1 et n°2... pour qu'on puisse avancer proprement"*.

WinBoost est techniquement à 96 % (60/62 tâches done), mais le projet n'avait
jamais été mis en conformité avec les deux règles absolues du Spine :

- **Règle n°1** : tout travail d'agent doit produire un log dans `.project/06-agent-logs/`
- **Règle n°2** : aucun agent invoqué sans triangle de contexte (Spine + projet + mission)

Le dossier `06-agent-logs/` n'existait pas. Aucun log historique. Le projet a été
inactif depuis le 25 mars (≈ 6 semaines), et la reprise nécessite un état des
lieux propre avant d'avancer (releases publiques + GTM).

## Résultats

### Inventaire avant remise en ordre

| Élément | État avant | État après |
|---------|-----------|-----------|
| `.project/06-agent-logs/` | **Absent** | Créé + README + 2 logs |
| Log rétroactif phases 1-10 | Absent | Écrit (`2026-05-06-claude-code-synthese-retroactive-phases-1-10.md`) |
| Log organisation du jour | — | Ce fichier |
| `MASTER-PLAN.md` | 33 lignes, vision + stack uniquement | Enrichi : État actuel, Décisions, Risques, Prochaines étapes |
| `TODO-HUMAN.md` | Absent | Créé : T029 + T061 + T062 avec checklists actionnables |
| `status.yaml` `last_updated` | `2026-03-25` | `2026-05-06` |
| `status.yaml` `logs[]` | Dernier = 2026-03-25 | + entrée 2026-05-06 (régularisation) |
| `.project/02-prompts/` | 1 prompt (phase 1) seulement | Constat : insuffisant mais non bloquant (toutes les phases sont done) |
| `.project/01-research/` | competitors.md + market.md | OK, garder en l'état |
| `.project/03-specs/` | architecture.md | OK |
| `.project/04-quality/` | checklist.md | OK |

### Conformité règle n°2 (triangle de contexte)

Le projet n'a pas eu d'invocation d'agent récente (dernier travail = 25 mars,
avant que la règle n°2 soit formalisée). À partir de maintenant, toute
invocation d'agent sur WinBoost devra suivre le canevas :

1. **Couche identité** : prompt Spine (`A:/dev/spine/_agents/{cat}/{nom}.md`)
2. **Couche projet** : `CLAUDE.md` + `status.yaml` + `.project/MASTER-PLAN.md`
3. **Couche mission** : brief utilisateur + livrable (chemin absolu) + format

Ce canevas est rappelé dans `CLAUDE.md` à la racine du Spine et dans
`_templates/common/agent-invocation.template.md`.

## Décisions prises

| Décision | Justification | Alternative rejetée |
|----------|---------------|---------------------|
| Écrire UN log de synthèse rétroactive plutôt que 10 logs reconstruits | Reconstruire fidèlement 10 logs détaillés 6 semaines plus tard est impossible et trompeur. Une synthèse honnête vaut mieux qu'une reconstruction approximative. | 10 logs rétroactifs un par phase (faux historique) |
| Ne pas créer de prompts de phase rétroactifs | Les phases sont déjà done — recréer leurs prompts n'apporte rien. Un seul prompt phase-1 suffit comme exemple historique. | Reconstituer les 9 prompts manquants |
| Créer un `TODO-HUMAN.md` plutôt que d'ajouter des tâches dans status.yaml | Les 3 tâches bloquantes sont déjà dans status.yaml (T029, T061, T062). Le fichier TODO-HUMAN expose la checklist actionnable que l'humain doit suivre. | Tout dans status.yaml (moins lisible côté humain) |
| Pas de section `gtm:` dans status.yaml pour l'instant | Le projet n'est pas encore en phase GTM (releases pas tirées). On ajoutera la section quand T061 sera done et qu'on enclenchera la phase 11. | Pré-créer la section vide (bruit) |
| Ne PAS toucher au code | La demande est purement organisationnelle. Le code est figé depuis le 25/03 et fonctionne (320 tests). Aucune raison d'y toucher dans ce passage. | Faire un "petit refacto" en passant (hors scope) |
| Ne PAS push automatiquement vers GitHub | Mémoire utilisateur autorise le push direct sur main, mais on commit d'abord, on confirme l'état, puis on pousse à la fin. | Push immédiat après chaque commit |

## Actions suivantes

### Pour claude-code (cette session)
- [x] Créer `.project/06-agent-logs/` + README
- [x] Écrire log de synthèse rétroactive phases 1-10
- [x] Écrire ce log d'audit organisation
- [ ] Enrichir `MASTER-PLAN.md` avec sections État / Décisions / Risques / Prochaines étapes
- [ ] Créer `TODO-HUMAN.md` avec les 3 tâches bloquantes
- [ ] Mettre à jour `status.yaml` (last_updated + log du jour)
- [ ] Commits structurés (4-5 commits, message `chore:` ou `docs:`)

### Pour Antoine (humain)
- [ ] Tirer GitHub Release **v1.0.0** (T029) — voir `TODO-HUMAN.md` section A
- [ ] Tirer GitHub Release **v2.0.0** (T061) — voir `TODO-HUMAN.md` section B

### Pour Enzo (humain)
- [ ] Brouillon Product Hunt (T062) — voir `TODO-HUMAN.md` section C
- [ ] Décider du go/no-go phase GTM après les releases

### Pour la suite (post-releases)
- [ ] Enclencher la phase 11 = **phase GTM** (selon CLAUDE.md Spine, structure 3 couches)
- [ ] Créer `gtm:` dans `status.yaml` à ce moment-là

## Impact sur le projet

### Fichiers créés
- `.project/06-agent-logs/README.md`
- `.project/06-agent-logs/2026-05-06-claude-code-synthese-retroactive-phases-1-10.md`
- `.project/06-agent-logs/2026-05-06-claude-code-audit-organisation.md` (ce fichier)
- `TODO-HUMAN.md`

### Fichiers modifiés
- `.project/MASTER-PLAN.md` — enrichi
- `status.yaml` — `last_updated` + nouvelle entrée logs

### Fichiers NON modifiés (volontairement)
- `ROADMAP.md` — fidèle à l'état réel, rien à changer
- `CLAUDE.md` projet — déjà suffisant
- Tout le code — hors scope de l'organisation

### Conformité Spine après ce passage
- ✅ Règle n°1 (agent-logs) : dossier créé, 2 logs présents, README de rappel
- ✅ Règle n°2 (triangle de contexte) : projet prêt à recevoir des invocations conformes
- ✅ Documentation projet : MASTER-PLAN enrichi, TODO-HUMAN explicite
- ✅ status.yaml synchronisé avec la date du jour

---

> Ce log clôture la phase de remise en ordre organisationnelle. Le projet est
> prêt à reprendre proprement. Les prochaines étapes sont du ressort humain
> (releases) puis de l'orchestrateur (phase GTM).
