# 06-agent-logs — Journal de travail des agents

## Règle Spine n°1 (rappel)

> Si un agent fait du travail, il écrit un log. Pas de log = le travail n'existe pas.

Ce dossier contient **tout** le travail d'agent qui n'est pas du code pur :
recherche, analyse, plan, audit, décision structurante.

Le code, lui, est tracé par Git. Les logs ici servent à expliquer **le pourquoi**
des décisions et à reconstruire le contexte 6 mois plus tard.

## Convention de nommage

```
YYYY-MM-DD-{agent}-{sujet}.md
```

Exemples :
- `2026-05-06-claude-code-audit-organisation.md`
- `2026-05-06-claude-code-synthese-retroactive-phases-1-10.md`
- `2026-06-15-marketing-strategist-positionnement-launch-v2.md`

## Contenu obligatoire

Chaque log doit contenir au minimum :

1. **Contexte** — pourquoi ce travail a été fait
2. **Résultats** — données, chiffres, conclusions
3. **Décisions** — choix faits + justification + alternatives rejetées
4. **Actions suivantes** — tâches à créer, fichiers à modifier
5. **Impact projet** — mises à jour status.yaml / MASTER-PLAN / ROADMAP

Template : `A:/dev/spine/_templates/common/agent-log.template.md`

## Règle d'or

Aucun agent ne considère son travail comme terminé tant que le log n'est pas
**écrit ET commité** avec le message :

```
docs: agent-log — {sujet}
```
