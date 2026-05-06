# TODO-HUMAN — WinBoost

> Tâches qui ne peuvent **PAS** être faites par Claude Code et qui bloquent la sortie publique.
> À jour au **2026-05-06**.

---

## A. Antoine — GitHub Release v1.0.0 (T029)

**Statut** : `not_started`
**Bloque** : visibilité publique de la v1, prérequis avant Product Hunt

### Pré-requis (déjà fait)
- ✅ Build `.exe` v1 produit (`build.py`)
- ✅ README v1 complet
- ✅ Tests E2E v1 (172 tests)
- ✅ Tag v1.0 mergé sur `main` (commit `38e0de4 feat: phase 5`)

### Checklist
- [ ] Vérifier que le `.exe` v1 lance correctement sur une machine Windows 11 propre (test smoke ~5 min)
- [ ] Sur GitHub : Releases → Draft a new release
- [ ] Tag : `v1.0.0`, target : `main`
- [ ] Title : `WinBoost v1.0.0 — Modules + CLI + GUI`
- [ ] Description (template) :
  ```
  Première version stable de WinBoost.

  ## Inclus
  - 8 modules d'optimisation (temp, startup, RAM, disk, privacy, dev cache, services, system info)
  - CLI Click (`winboost scan`, `winboost fix`, `winboost info`)
  - GUI CustomTkinter dark theme
  - Backup automatique + undo + history SQLite
  - 172 tests, 81 % de couverture (hors GUI)

  ## Téléchargement
  - `winboost-v1.0.0.exe` (Windows 10/11 x64, standalone)

  ## Notes
  - Repo privé pour l'instant — release accessible via lien direct
  - Pas de Product Hunt sur cette version, focus v2

  Built with Python 3.12 + PyInstaller.
  ```
- [ ] Joindre le `.exe` v1 comme asset (≈ généré par `python build.py`)
- [ ] Cocher "Set as the latest release" si pas de v2 publiée encore, sinon laisser v2 latest
- [ ] Publier
- [ ] Mettre à jour `status.yaml` : T029 → `done`

### Estimation
~ 30 min (smoke test compris)

---

## B. Antoine — GitHub Release v2.0.0 (T061)

**Statut** : `not_started`
**Bloque** : visibilité publique de la v2, prérequis Product Hunt (T062)

### Pré-requis (déjà fait)
- ✅ Build `.exe` v2 produit (hidden imports + YAML data files)
- ✅ README v2 complet (features, profils, chat, architecture)
- ✅ Tests E2E v2 (27 nouveaux + 320 total)
- ✅ Tag v2.0 mergé sur `main` (commit `9b6bec1 feat: phase 10`)

### Checklist
- [ ] Vérifier que le `.exe` v2 lance correctement sur Windows 11 propre
- [ ] Tester le wizard d'onboarding (3 étapes)
- [ ] Tester un appel chat avec une vraie clé Anthropic (ex : "nettoie mes temp")
- [ ] Sur GitHub : Releases → Draft a new release
- [ ] Tag : `v2.0.0`, target : `main`
- [ ] Title : `WinBoost v2.0.0 — AI Chat + Action Registry`
- [ ] Description (template) :
  ```
  Nouvelle version majeure : WinBoost devient conversationnel.

  ## Nouveautés
  - 🤖 Chat IA (Anthropic / OpenAI / Ollama)
  - 📚 Action Registry de 150 actions YAML (privacy, perf, cleanup, dev tools, network, security, appearance, gaming, system)
  - 🛡️ 3 profils utilisateur (Safe / Power / Expert)
  - 🎨 Onboarding wizard (3 étapes)
  - 📜 History viewer (timeline des actions passées)
  - ↩️ Undo multi-action avancé
  - ⚙️ Settings UI complet

  ## Hérité de v1.0
  - 8 modules d'optimisation
  - CLI + GUI
  - Backup + undo

  ## Téléchargement
  - `winboost-v2.0.0.exe` (Windows 10/11 x64, standalone)

  ## Documentation
  - README dans le repo
  - 320 tests automatisés

  Built with Python 3.12 + PyInstaller.
  ```
- [ ] Joindre le `.exe` v2 comme asset
- [ ] Cocher "Set as the latest release"
- [ ] Publier
- [ ] Mettre à jour `status.yaml` : T061 → `done`

### Estimation
~ 45 min (smoke test étendu compris)

### Risque connu
Faux positif antivirus possible (Microsoft Defender) sur les `.exe` PyInstaller.
→ Si détecté : soumettre le binaire à Microsoft via https://www.microsoft.com/wdsi/filesubmission

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

## Sortie de cette phase

Quand T029, T061 et T062 sont `done` :
1. Mettre à jour `status.yaml` → `progress: 100`
2. Validation humaine de la phase 10 : `phase_validated_by: antoine`, `phase_validated_at: 2026-XX-XX`
3. Commit : `chore: validate phase 10, advance to phase 11 (GTM)`
4. Enclencher la **Phase 11 — GTM 3 couches** via l'agent `gtm-launcher` (cf. `_agents/business/gtm-launcher.md` et `_templates/common/gtm-framework.md`)
5. Ajouter la section `gtm:` dans `status.yaml`

---

> Ce fichier est mis à jour par Claude Code à chaque commit qui modifie l'état d'une de ces tâches.
> Les humains peuvent cocher les cases au fur et à mesure ; Claude resynchronisera `status.yaml`.
