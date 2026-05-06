# Brief Enzo — T074 : Post HackerNews + Soumissions registres MCP

**Date** : à fixer avec Antoine (mardi/mercredi 8-10h ET recommandé)
**Charge totale** : ~3-4h prépa + jour J
**Objectif** : générer la première vague de traction sur WinBoost v2.4.0

---

## Contexte

WinBoost v2.4.0 est **public et stable**. 5 releases shippées en ~12h grâce au dogfooding intensif d'Antoine. Premier bug réel résolu (DualSense + Rocket League sur Epic Games) → **testimonial parfait** pour le post HN.

- Repo : https://github.com/Antoine6958585/winboost
- Latest release : https://github.com/Antoine6958585/winboost/releases/tag/v2.4.0
- 1172 tests automatisés, 185 actions, 12 commandes CLI, 8 onglets GUI, MIT licensed

---

## Action 1 — Validation pré-launch (~30 min)

### 1.1 Vérifier que `pip install` marche fresh sur Windows
```powershell
# Sur une machine Windows fresh OU une VM
pip install winboost
winboost --version  # doit afficher 2.4.0
winboost diagnose "test"  # doit lancer un diagnostic
winboost gui  # doit ouvrir la GUI
```

### 1.2 Vérifier `pip install winboost[mcp]` + Claude Desktop
```powershell
pip install winboost[mcp]
winboost mcp install-claude-desktop
# Redemarrer Claude Desktop
# Verifier que les 5 tools WinBoost apparaissent dans Settings -> MCP
```

Si ces 2 tests fail → STOP, on debug avant le post HN.

---

## Action 2 — Soumissions registres MCP (~1h)

### 2.1 smithery.ai
1. Va sur https://smithery.ai/submit
2. Remplis :
   - **Name** : `winboost`
   - **Title** : `WinBoost — Windows AI Assistant`
   - **Repo URL** : `https://github.com/Antoine6958585/winboost`
   - **Category** : "system-control" ou "windows-utilities"
   - **Description** (300 chars max) :
     > Windows system assistant exposing 185 native actions (registry, services, PowerShell, FS) + intelligent diagnostics (5 themes) via MCP. Detects + suggests fixes for Bluetooth, gaming, network, audio, display issues. Real execution with backup + rollback. MIT.
   - **Install command** : `pip install winboost[mcp] && winboost mcp install-claude-desktop`
   - **Tags** : windows, system, diagnostics, gaming, bluetooth, MCP, claude
3. Sauvegarde l'URL une fois soumis

### 2.2 anthropic.com/mcp (registre officiel)
1. Va sur https://anthropic.com/mcp ou la page officielle de soumission
2. Suivre le format de soumission documenté
3. Mettre les mêmes infos que smithery + insister sur le testimonial DualSense
4. Sauvegarde l'URL

### 2.3 GitHub topics (pour SEO)
Sur le repo GitHub → **About** (panneau droit) → **⚙️** → ajoute topics :
`mcp` `mcp-server` `windows` `claude-desktop` `cursor` `system-utilities` `diagnostics` `gaming` `bluetooth` `python` `ai`

---

## Action 3 — Préparation du post HN (~1h)

### 3.1 Visuels à préparer (15 min)

- **Screenshot 1** : Claude Desktop avec WinBoost listé dans la section MCP servers
- **Screenshot 2** : Le diagnostic CLI sur la query DualSense :
  ```
  winboost diagnose "ma manette bluetooth bug dans rocket league"
  ```
  Capture d'écran du rapport coloré (highlight la ligne `bluetooth_gamepad_mapping` qui détecte la DualSense mal mappée).
- **GIF court (3-5s)** : démo overlay Win+Espace OU démo onglet GUI Diagnose

### 3.2 Title HN (60 chars max)

Options en ordre de préférence :
1. ❤️ `Show HN: WinBoost — diagnose Windows bugs from Claude Desktop via MCP`
2. `Show HN: I built an MCP server that fixes my Windows bugs`
3. `Show HN: WinBoost — open-source Windows assistant + MCP for Claude`

### 3.3 Maker comment (le 1er commentaire après le post)

Template pré-rédigé (à adapter par Enzo) :

> Maker here. WinBoost started as a Python utility to clean Windows temp files, but I kept hitting a wall: every Windows bug is a different rabbit hole on Reddit. So I built two layers:
>
> 1. A rules-based diagnostic engine (5 themes: bluetooth, gaming, network, audio, display) that scans the system in <10s and proposes a fix plan
> 2. An MCP server that exposes 185 actions + the diagnostic to Claude Desktop, Cursor, etc.
>
> First dogfooding day: my PS5 controller was bugging in Rocket League over Bluetooth on Epic Games. Steam Input was off. Windows Update had no Xbox driver. Ran `winboost diagnose "ma manette bluetooth bug"` → it identified my DualSense as mismapped (Sony doesn't expose XInput on the BT profile, well-known issue), suggested 3 fixes including DS4Windows. Worked in 2 minutes.
>
> The point isn't that I built something fancy. It's that this kind of bug is everywhere — controllers, printers, audio devices, dual monitors — and they all have the same shape: "system says it works, app says it doesn't, user has no idea". WinBoost names the cause + suggests the fix.
>
> Tech stack: Python 3.12, CustomTkinter, Click, FastMCP, PyInstaller. MIT licensed. BYOK Anthropic for Computer Use mode (optional Lab tier).
>
> Roadmap is in the README + agent-logs in `.project/06-agent-logs/` (we use AI agents extensively for development, fully documented).
>
> Happy to discuss tech choices, false positives in diagnostics, or unit-economics of bundling MCP server with a Pro tier.

### 3.4 Timing recommandé

- **Jour J** : mardi ou mercredi (meilleurs jours HN)
- **Heure** : 8h-10h ET (= 14h-16h Paris) — pic de traffic US
- **Préparer 5-7 réponses** anticipées aux questions probables :
  - "Why not just use PowerShell scripts?" (réponse : NL parsing + safety + diagnostics rules-based + MCP)
  - "Computer Use is dangerous" (réponse : BYOK obligatoire + RGPD opt-in + plafond + confirmation à chaque action)
  - "Privacy?" (réponse : Ollama local pour le NL, 70% cache local, BYOK pour le reste)
  - "How does it compare to Wox/PowerToys Run?" (réponse : ces 2 sont des launchers, WinBoost est un système de fix automatisé + diagnostic)
  - "Why MCP?" (réponse : agents AI vont être partout, autant exposer un PC contrôle à eux quand l'utilisateur le veut)

---

## Action 4 — Communication coordonnée (jour J, ~1h)

### 4.1 Tweet Enzo (X)
```
Just shipped WinBoost v2.4.0 + MCP server.

Built it because every "controller doesn't work in BT" / "printer doesn't print" / "second screen is fuzzy" Windows bug eats my time on Reddit.

Open-source MIT, BYOK, 185 actions, 5 diagnostic themes, exposed as MCP for Claude Desktop.

[lien HN]
```

### 4.2 Post LinkedIn Antoine
À écrire par Antoine — angle "we built an open-source Windows assistant during our dogfooding".

### 4.3 Coordination

- Enzo poste sur HN à H+0
- Antoine relaye sur LinkedIn à H+30
- Enzo retweet le post LinkedIn d'Antoine à H+45
- Enzo poste sur Reddit r/Anthropic OU r/ClaudeAI avec un lien vers le post HN à H+1h (à valider avec Antoine d'abord — beaucoup de subreddits interdisent les autopromos)

---

## Action 5 — Monitoring post-launch (~1h sur 24h)

- Réponds aux 10 premiers commentaires HN dans les 30 min (boost ranking)
- Si quelqu'un signale un bug → ouvre une issue GitHub immédiatement
- Si quelqu'un demande une feature → "noted" + tag dans status.yaml comme `discovered_during_hn`
- À H+24, retour à Antoine + claude-code avec : nb stars gagnées, top-3 commentaires, top-3 critiques

---

## Critères de succès

- ≥ 100 stars GitHub à H+48
- ≥ 10 commentaires constructifs sur HN (pas du fluff)
- ≥ 1 mention dans une newsletter MCP / Claude
- Si ≥ 500 stars + ≥ 50 demandes Computer Use → **trigger v2.5 features**

## Ressources

- Repo : https://github.com/Antoine6958585/winboost
- Release notes v2.4.0 : https://github.com/Antoine6958585/winboost/releases/tag/v2.4.0
- Doc MCP : `winboost/mcp/README.md`
- Verdict T072 PyInstaller : `tests/mcp_compat/VERDICT.md`
- Brief Antoine T075 (pricing) : `docs/briefs/BRIEF-ANTOINE-T075-pricing.md`
