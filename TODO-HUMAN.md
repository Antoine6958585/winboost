# TODO-HUMAN — WinBoost

> Tâches qui ne peuvent **PAS** être faites par Claude Code et qui bloquent la sortie publique.
> À jour au **2026-05-06** (post-remédiation smoke test, verdict GO clean).

---

## A. ~~GitHub Release v1.0.0 (T029)~~ — SKIPPÉ

**Décision Antoine 2026-05-06** : pas de Release v1.0.0 publique. Le projet est passé de 0 à v2.0 en un sprint en mars 2026, aucun utilisateur v1 à informer. Tirer 2 Releases simultanées sur le repo public crée plus de confusion que de valeur. **Une seule Release sera publiée : v2.0.0** (section B ci-dessous).

L'historique git conserve les commits de phase 1-5 (`dc7357b` → `38e0de4`) — la v1 est techniquement accessible via `git checkout 38e0de4` pour qui voudrait la build.

---

## B. Antoine — GitHub Release v2.0.0 + repo public (T061) — ✅ DONE 2026-05-06

**Statut** : `done`
**URL** : https://github.com/Antoine6958585/winboost/releases/tag/v2.0.0
**Asset** : WinBoost.exe (54,7 Mo, SHA256 `70d94d070902cc7bdf6bba05ed05e0fd9042e7c847994a6d25b6b22888d6b644`)
**Tag** : v2.0.0 sur commit `ba8a9a6` (main)
**Latest release** : ✅

### Verdict smoke test (Reality Checker RUN2 — 2026-05-06) : **GO CLEAN**

Tous les bloquants levés, métriques mesurées matériellement :
- 382 tests passent, 1 skip (Linux)
- Coverage 91 % hors GUI (cible 80 %)
- 0 erreur ruff
- LICENSE MIT présent
- Version 2.0.0 cohérente sur 5 sources
- UAC helper opérationnel + intégration GUI
- `python -m winboost` OK
- `WinBoost.exe` : **23,3 Mo**, build en 36 s

Rapport complet : `.project/06-agent-logs/2026-05-06-reality-checker-pre-release-smoke-test-RUN2.md`

### Checklist (~45 min total)

#### Étape 1 — Smoke test humain (~15 min)
- [ ] `cd A:/dev/winboost && python build.py` — produit `dist/WinBoost.exe`
- [ ] Lancer `dist/WinBoost.exe gui` — vérifier dashboard, dark theme, branding
- [ ] Tester wizard onboarding (3 étapes : bienvenue → profil → API key)
- [ ] Tester chat IA avec une vraie clé Anthropic : "nettoie mes temp"
- [ ] Tester `WinBoost.exe scan` en mode user vs admin sur une action `requires_admin: true` — confirmer le refus propre du SafetyEngine en mode user

#### Étape 2 — Passage repo public (~5 min)
- [ ] GitHub → Settings → Danger Zone → Change visibility → Public
- [ ] Confirmer le warning, taper `Antoine6958585/winboost`
- [ ] Vérifier que `LICENSE` apparaît dans la sidebar GitHub (preuve que MIT est reconnu)

#### Étape 3 — Tirer la Release v2.0.0 (~15 min)
- [ ] GitHub → Releases → Draft a new release
- [ ] Tag : **`v2.0.0`**, target : `main` (commit le plus récent)
- [ ] Title : `WinBoost v2.0.0 — AI Chat + Action Registry`
- [ ] Description (template prêt) :
  ```
  Le premier assistant Windows qui ne te ment pas.

  WinBoost combine 8 modules d'optimisation classiques avec un chat IA
  conversationnel pilotant un Action Registry de 150 actions cataloguées.

  ## Inclus
  - 🤖 Chat IA (Anthropic / OpenAI / Ollama, BYOK)
  - 📚 Action Registry de 150 actions YAML (privacy, perf, cleanup, dev tools, network, security, appearance, gaming, system)
  - 🛡️ 3 profils utilisateur (Safe / Power / Expert) avec filtrage SafetyEngine
  - 🧹 8 modules : temp, startup, RAM, disk, privacy, dev cache, services, system info
  - 🎨 Onboarding wizard, History viewer, Undo multi-action, Settings complet
  - ↩️ Backup automatique avant chaque action high/critical
  - 🔒 UAC sélectif (admin requis uniquement quand l'action l'exige)

  ## Téléchargement
  - `WinBoost.exe` — Windows 10/11 x64, standalone (23 Mo)

  ## Quality
  - 382 tests automatisés, 91 % de couverture (hors GUI)
  - 0 secret hardcodé, 0 eval/exec, audit ruff clean
  - MIT licensed, code source ouvert

  ## Note v2.0
  Les 150 actions YAML sont actuellement un **catalogue valide** ; leur
  exécution réelle (registry_set, service_disable, powershell, etc.) avec
  élévation UAC sélective est planifiée en v2.1. Le worker chat affiche
  honnêtement "Action enregistree dans le catalogue (execution reelle en
  v2.1)" — pas de faux succès. Les 8 modules d'optimisation classiques
  (temp/RAM/disk/etc.) fonctionnent en plein, eux.

  Built with Python 3.12 + CustomTkinter + Click + PyInstaller.
  ```
- [ ] Joindre `dist/WinBoost.exe` comme asset
- [ ] Cocher "Set as the latest release"
- [ ] Publier 🚀
- [ ] Vérifier que la page Release est bien accessible publiquement (incognito tab)

#### Étape 4 — Sync (~5 min)
- [ ] Me dire "Release v2.0.0 publiée" → je mets à jour `status.yaml` (T061 → done) et on enchaîne sur la Phase 11

### Risque connu
Faux positif Microsoft Defender / SmartScreen possible sur les `.exe` PyInstaller non signés.
- Mitigation immédiate : documenter dans le README + soumettre le binaire à https://www.microsoft.com/wdsi/filesubmission
- Mitigation long terme (post v2.1) : code signing avec certificat OV (~80 €/an)

---

## C. Enzo — Product Hunt draft (T062)

**Statut** : `not_started`
**Bloque** : pas la release, mais la traction publique post-launch

### Pré-requis
- T061 (Release v2.0.0) doit être tirée AVANT pour avoir un lien de téléchargement
- ⚠️ **Repo doit être public** au moment du Product Hunt (sinon les visiteurs tombent sur du vide)

### Checklist
- [ ] Décider avec Antoine du jour J du repo passe public (avant le PH ou en même temps)
- [ ] Créer un compte Product Hunt si pas déjà fait (`producthunt.com/signup`)
- [ ] Préparer les 4 visuels : 1 logo (240×240), 1 hero (1200×675), 2 screenshots (GUI + chat)
- [ ] Tagline (≤ 60 caractères) : ex. *"The Windows assistant that doesn't lie to you"*
- [ ] Description (≤ 260 caractères) : pitcher v1 + v2 + freemium en 3 phrases
- [ ] First comment (le maker pitch) : 5-7 lignes — pourquoi le projet existe, pourquoi c'est différent, BYO key
- [ ] Lister 3-5 hunters/makers à pinger en DM avant le launch (ne PAS spammer)
- [ ] Choisir le jour : **mardi ou mercredi** (meilleurs jours), 00:01 PST
- [ ] Topic principal : "Productivity" ou "Developer Tools"
- [ ] Topics additionnels : "Windows", "AI", "Open Source"
- [ ] Submit en draft 48h avant pour relire
- [ ] Le jour J : poster + relayer sur LinkedIn (Antoine) + X (Enzo)

### Estimation
~ 3-4 h de prépa + le jour J

---

---

## D. Antoine — Validation Phase 11 v2.1 (2026-05-06)

**Statut** : `pending_human_validation`
**Bloque** : passage en Phase 12 (v2.2 MCP Standalone)

### Contexte
Phase 11 techniquement complète : 6 tâches done (T063-T068), 610 tests green, 0 ruff error, 180 actions registry, +30 actions Windows-natives (luminosité, dark mode, focus assist, volume, bluetooth, DNS, IPv6, animations…), hotkey global Win+Espace + overlay, mode JSON CLI.

### Checklist validation (~30 min)

#### 1. Test in vivo de l'overlay (~15 min)
```powershell
cd A:/dev/winboost
pip install -e .
winboost overlay
```
Puis presser **Win+Espace** depuis ≥ 3 apps (Chrome, VS Code, Slack…) :
- [ ] L'overlay apparaît centré, transparent
- [ ] Le focus se met automatiquement sur le champ texte
- [ ] Taper "active le mode focus" + Enter → l'action sys_016 s'affiche
- [ ] Esc ferme l'overlay
- [ ] Si rien ne se passe → relancer dans un terminal **admin** (limitation `keyboard` package)

#### 2. Capture du GIF de démo (~10 min)
Instructions complètes dans `docs/assets/README.md`.
- [ ] Outil : ScreenToGif (gratuit, https://www.screentogif.com/)
- [ ] Scénario 5-8s : `winboost overlay` → bascule sur Chrome → Win+Espace → "active le mode focus" → Enter → Esc
- [ ] Cible : <2 Mo, 800px max width, 12-15 FPS
- [ ] Path final : `A:/dev/winboost/docs/assets/winboost-overlay-demo.gif`

#### 3. Commit du GIF + validation (~5 min)
- [ ] `git add docs/assets/winboost-overlay-demo.gif`
- [ ] `git commit -m "docs: add overlay demo GIF (T068 finalisation)"`
- [ ] `git push origin main`
- [ ] Me dire **"Phase 11 validée"** → je passe `phase_validated_by: antoine`, `current_phase: 12`, et on enchaîne sur la **v2.2 MCP Standalone** (refactor monorepo 3 packages)

### Sortie de cette phase
Une fois validée, on attaque la Phase 12 (T069-T075) : `winboost-core` + `winboost-gui` + `winboost-mcp` (PyPI), FastMCP, install Claude Desktop, soumissions registres MCP.

---

## Sortie de cette phase (legacy v2.0)

Quand T029, T061 et T062 sont `done` :
1. Mettre à jour `status.yaml` → `progress: 100`
2. Validation humaine de la phase 10 : `phase_validated_by: antoine`, `phase_validated_at: 2026-XX-XX`
3. Commit : `chore: validate phase 10, advance to phase 11 (GTM)`
4. Enclencher la **Phase 11 — GTM 3 couches** via l'agent `gtm-launcher` (cf. `_agents/business/gtm-launcher.md` et `_templates/common/gtm-framework.md`)
5. Ajouter la section `gtm:` dans `status.yaml`

---

> Ce fichier est mis à jour par Claude Code à chaque commit qui modifie l'état d'une de ces tâches.
> Les humains peuvent cocher les cases au fur et à mesure ; Claude resynchronisera `status.yaml`.
