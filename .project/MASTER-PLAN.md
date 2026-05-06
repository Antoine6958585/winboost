# WinBoost — MASTER PLAN

> Source de vérité du projet. À lire **avant toute action** sur WinBoost.

---

## Vision
"Le premier assistant Windows qui ne te ment pas."

- **v1** = 8 modules classiques (temp cleaner, startup, RAM, disk, privacy, dev cache, services, system info)
- **v2** = Chat IA conversationnel qui pilote le PC via un Action Registry de 150+ actions

## Positionnement
Copilot ne touche pas au système. Les optimizers ne parlent pas. **WinBoost fait les deux.**

## Modèle de revenus
- **Gratuit** : v1 complète + chat IA limité à 50 actions
- **Pro** (4,99 €/mois ou 39 €/an) : 150+ actions, profils, rollback avancé, support
- **BYO key** : gratuit, sans limite (utilisateur fournit sa clé Anthropic/OpenAI/Ollama)

## Cible
Power users Windows, développeurs, admins IT, puis utilisateurs intermédiaires via la v2.

## Stack
Python 3.12+ | CustomTkinter | Click | psutil/wmi/ctypes/winreg | Anthropic/OpenAI/Ollama | PyInstaller | pytest

## Milestones
- **v1.0** : 8 modules + CLI + GUI + .exe (Phases 1-5) — **technique : done**, release : pending Antoine
- **v2.0** : Action Registry + AI Engine + Chat GUI (Phases 6-10) — **technique : done**, release : pending Antoine

---

## État actuel (au 2026-05-06)

| Métrique | Valeur |
|----------|--------|
| Progress | **96 %** (60/62 tâches) |
| Phase active | 10 (Release v2.0) |
| Tests | **320** au total |
| Modules livrés | 8/8 |
| Actions registry | 150/150 |
| Providers LLM | 3/3 (Anthropic, OpenAI, Ollama) |
| Profils | 3/3 (Safe, Power, Expert) |
| Build | `.exe` v1 + v2 produits |
| Dernière activité code | 2026-03-25 |
| Dernière activité organisation | 2026-05-06 |

**Reste à faire** : 3 tâches, **toutes humaines** :
- T029 — GitHub Release v1.0.0 (Antoine)
- T061 — GitHub Release v2.0.0 (Antoine)
- T062 — Product Hunt draft (Enzo)

Détails actionnables : voir `TODO-HUMAN.md`.

---

## Décisions structurantes

| # | Décision | Justification |
|---|----------|---------------|
| 1 | Repo privé jusqu'à validation Antoine | Éviter une release publique prématurée |
| 2 | CustomTkinter plutôt que PyQt | Empreinte légère, dark theme natif |
| 3 | 3 providers LLM (Anthropic / OpenAI / Ollama) | BYO key + Ollama local pour les power users |
| 4 | Cache keyword local (~70 % requêtes) | Latence + coût quasi nuls sur les cas courants |
| 5 | Action Registry YAML séparé du code | Permet d'ajouter des actions sans rebuild |
| 6 | 3 profils (Safe / Power / Expert) | Modèle simple, suffisant pour différencier free/pro |
| 7 | PyInstaller plutôt que Nuitka | Stabilité, écosystème mature, support YAML data files |
| 8 | Backup auto avant action high/critical | Règle de sécurité absolue, non négociable |
| 9 | Freemium 50 actions / Pro 4,99 € | Aligne valeur perçue, conversion sur power users |
| 10 | TDD avec couverture 80 %+ | Confiance pour modifier sans régression |

---

## Règles absolues du produit

1. **Pas de modification registre** sans backup automatique
2. **Pas de suppression fichier système** — jamais
3. **Dry-run par défaut** pour les nouveaux utilisateurs (profil Safe)
4. **L'IA ne peut jamais agir sans confirmation utilisateur**
5. **Tout est réversible** — undo manager + history SQLite

---

## Risques connus

| Risque | Impact | Mitigation actuelle |
|--------|--------|---------------------|
| Antoine ne tire pas la release rapidement | Le produit reste invisible publiquement | TODO-HUMAN.md + relance hebdo |
| Faux positifs des LLM externes (action mal mappée) | Dégradation système chez l'utilisateur | Safety Engine filtre par profil + Confirm dialog avant action high/critical |
| Coût API LLM externe élevé sur le tier gratuit | Marge négative sur free users | Cache keyword (~70 % requêtes locales) + limite 50 actions/mois sur free |
| Concurrence (Glary Utilities, CCleaner) avec marketing massif | Difficile de se faire connaître | Positionnement "ne te ment pas" + chat IA différenciant + Product Hunt |
| Faux positif antivirus sur le `.exe` PyInstaller | Friction d'install pour l'utilisateur | À documenter dans le README + soumettre le binaire à Microsoft Defender (post-T061) |
| Maintenance long terme du registre des 150 actions | Compatibilité Windows 11 / 12 future | Schema YAML versionné + tests dry-run par action |

---

## Prochaines étapes (post 2026-05-06)

### Immédiat (humain)
1. Antoine : tirer Release v1.0.0 et v2.0.0
2. Enzo : préparer brouillon Product Hunt

### Court terme (post-releases)
3. Phase **11 — GTM 3 couches** (cf. CLAUDE.md Spine, section "Phase GTM Go-To-Market")
   - L0 : Positionnement (ICP, message, choix de 2 canaux max)
   - L1 : Acquisition directe (LinkedIn outreach + cold email, 100+ contacts)
   - L2 : Crédibilité (landing, contenu, témoignages)
   - L3 : Expansion (SEO, Ads, partenariats) — **conditionnel à la traction L1**
4. Activer la section `gtm:` dans `status.yaml` à ce moment-là

### Court terme — Évolution "Claude pilote ton PC" (validée 2026-05-06)

**Plan complet** : `C:/Users/Dezmen/.claude/plans/proud-weaving-walrus.md`
**Log de validation** : `.project/06-agent-logs/2026-05-06-claude-code-plan-evolution-v2.1-v2.3.md`

| Version | Capacité | Effort | Quand |
|---------|----------|--------|-------|
| **v2.1** | +30 actions Windows-natives (luminosité WMI, dark mode, volume, Bluetooth, focus assist…) + hotkey Win+Espace overlay texte + mode JSON CLI | ~12-15 h | Après ship v2.0 |
| **v2.2** | Refactor monorepo 3 packages (`winboost-core` / `winboost-gui` / `winboost-mcp`) + serveur MCP standalone distribué via registres (smithery.ai, anthropic.com/mcp) | ~10-14 h | Après v2.1 stable |
| **v2.3** | Computer Use Pilot Mode — **conditionnel** (≥ 500 stars + ≥ 100 Pro + demande explicite). BYOK Anthropic obligatoire, profil Expert, opt-in séparé "Lab Mode" | ~20-26 h | Si traction confirmée |

**Décisions structurantes validées** :
- Voice (Whisper + TTS) **coupé** — gimmick desktop (5 % usage, +200 Mo binaire)
- Pricing Pro **passe à 9,99 €/mois** (alignement Cursor/Claude Pro)
- Computer Use **BYOK obligatoire** — protège unit economics + clarifie RGPD
- **Ship v2.0 d'abord** — interdiction de coder v2.1 avant les Releases tirées

### Moyen terme (Post-v2.3)
- Plugin marketplace (actions tierces)
- Multi-langue UI (DE, ES, PT)
- Scheduled actions
- Remote monitoring multi-PC, extension navigateur, mobile companion

---

## Conformité Spine

- ✅ Règle n°1 (agent-logs) : dossier `.project/06-agent-logs/` opérationnel depuis 2026-05-06
- ✅ Règle n°2 (triangle de contexte) : à appliquer pour toute future invocation d'agent
- ✅ `status.yaml` synchronisé
- ✅ `TODO-HUMAN.md` présent à la racine

---

## Liens utiles

- `CLAUDE.md` — instructions projet
- `README.md` — documentation utilisateur (anglais)
- `ROADMAP.md` — phases détaillées
- `status.yaml` — état machine-readable
- `TODO-HUMAN.md` — checklists humaines
- `.project/06-agent-logs/` — journal des décisions agent
- `.project/01-research/` — recherche concurrentielle + marché
- `.project/03-specs/architecture.md` — architecture technique
- `.project/04-quality/checklist.md` — checklist qualité
