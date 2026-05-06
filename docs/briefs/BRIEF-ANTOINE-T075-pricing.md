# Brief Antoine — T075 : Pricing 9,99 EUR + Stripe + landing + email Pro

**Charge totale** : ~2-3h dev/admin + cycle de validation
**Objectif** : monétiser WinBoost v2.4.0 avant le post HN d'Enzo

---

## Contexte

WinBoost passe de outil dogfooding interne à produit public. Le pricing actuel (4,99 EUR/mois) est hérité d'un plan v1. La v2.x a livré bien plus de valeur (MCP, Computer Use, Diagnose, Native Actions) → alignement sur les concurrents (Cursor 20$, Claude Pro 20$) justifié.

Le BYOK Anthropic en Lab Mode protège l'unit economics : l'utilisateur paie sa propre facture API.

---

## Décisions à prendre AVANT de toucher Stripe (~30 min)

### Décision 1 — Nouveau prix

| Option | Pour | Contre |
|---|---|---|
| **9,99 EUR/mois** (recommandé) | Aligne Cursor/Claude Pro, finance distribution MCP, marge confortable | Saut de prix x2 |
| 7,99 EUR/mois | Plus accessible, gain moins violent | Sous-estime la valeur ajoutée v2.x |
| 12,99 EUR/mois | Premium positioning | Risque churn Pro existants |

**Recommandation** : **9,99 EUR/mois** + 89 EUR/an (économie 2 mois pour annuel). Cohérent avec le brief plan d'origine (`proud-weaving-walrus.md`).

### Décision 2 — Plan annuel

- Garde 79 EUR/an actuel ? (pour les Pro existants en migration)
- OU bump à 89-99 EUR/an pour les nouveaux ?

**Recommandation** : 89 EUR/an pour les nouveaux. Les Pro existants gardent 79 EUR/an legacy (cf. décision 4).

### Décision 3 — Tier "Lab" (Computer Use BYOK)

- Créer le tier **Lab** maintenant (9,99 EUR + BYOK Anthropic) ?
- OU attendre v2.5 / le post HN pour le lancer ?

**Recommandation** : **attendre v2.5**. Le Lab Mode existe déjà côté code (T076-T081), mais commercialement on n'en parle pas dans la première vague. On le pitche dans la v2.5 si la traction Computer Use se confirme post-HN.

### Décision 4 — Pro existants à 4,99 EUR

3 options :
- **A. Tarif legacy à vie** (recommandé) — fidélise + bouche-à-oreille positif. Coût marginal négligeable (peu d'utilisateurs).
- B. Migration forcée à 9,99 après 6 mois de préavis — rationnel mais risque de churn.
- C. Migration immédiate avec 30 jours de préavis — agressif, à éviter.

**Recommandation** : **Option A**. Email transparent : "Tu gardes 4,99 EUR/mois à vie. Merci d'avoir cru au projet."

---

## Action 1 — Stripe (~30 min)

### 1.1 Créer le nouveau produit

Stripe Dashboard → **Products** → **+ Add product** :
- **Name** : `WinBoost Pro`
- **Description** : `Windows AI assistant — full features, BYOK Anthropic optional, MIT-licensed`
- **Pricing model** : Recurring
- **Variant 1** : 9,99 EUR / month (price_id à noter)
- **Variant 2** : 89 EUR / year (price_id à noter)

### 1.2 Désactiver l'ancien produit (mais garder actif pour les Pro existants)

L'ancien produit "WinBoost Pro 4.99 EUR" doit :
- Rester **actif** pour les abonnements existants (ne pas churn)
- Devenir **invisible** sur la page checkout publique (archiver ou cacher)

Stripe : **Products** → ancien produit → **⋯** → **Archive** (ne crée pas de nouveau abonnement, ne casse pas les existants)

### 1.3 Webhook + Customer Portal

Vérifier que les webhooks Stripe pointent toujours vers ton backend (si t'en as un). Le Customer Portal doit permettre aux Pro existants de continuer à voir leur tarif legacy.

### 1.4 Test end-to-end

- Carte test Stripe : `4242 4242 4242 4242` / `12/34` / `123`
- Checkout sur le **nouveau** plan 9,99 → vérifier reçu + abonnement actif côté Stripe
- Annuler l'abonnement test
- Vérifier que les Pro existants ne sont pas impactés

---

## Action 2 — Landing page (~1h)

### 2.1 Section pricing

Refaire la section pricing avec 3 tiers :

| Free | Pro | Lab (à venir) |
|------|-----|---------------|
| 0 € | **9,99 EUR/mois** ou 89 EUR/an | 9,99 EUR + BYOK Anthropic |
| GUI WinBoost, 50 actions de base, chat IA local (cache + Ollama recommandé) | **180+ actions, profils Safe/Power/Expert, undo avancé, MCP server inclus, support email** | Pro + Computer Use Pilot Mode (BYOK) |
| Découverte, étudiants | Power users, devs solo | Experts, early adopters |
| Download | **Subscribe** | "Coming v2.5" |

### 2.2 Hero refresh

Mention v2.4 :
- "Diagnose Windows bugs in 10s"
- "Open-source MIT, MCP-native"
- "Used by [Antoine + Enzo + ?] daily"

### 2.3 Section MCP (nouvelle)

> ## Pilot from Claude Desktop
> Install WinBoost as an MCP server in Claude Desktop, Cursor, or Code, and let your AI use the 185 actions + diagnostic engine to fix your PC.
>
> ```bash
> pip install winboost[mcp]
> winboost mcp install-claude-desktop
> ```

### 2.4 FAQ — nouvelle question

> **Pourquoi 9,99 EUR maintenant et plus 4,99 EUR ?**
> WinBoost v2.x a livré le MCP server, le mode Pilot Computer Use, les 30 actions natives Windows, le diagnostic intelligent. C'est aligné sur Cursor (20 $) et Claude Pro (20 $) avec un positionnement plus accessible. Les utilisateurs qui ont souscrit en v1.x gardent leur tarif à vie.

---

## Action 3 — Email aux Pro existants (~30 min)

### 3.1 Choix du canal

**Brevo** (recommandé) — déjà dans la stack Antoine. Alternative : Stripe Email via Customer.io.

### 3.2 Liste des destinataires

Stripe → Customers → filtre "subscribed before 2026-05-06" → export CSV → import Brevo. Vérifier que tu n'oublies aucun Pro.

### 3.3 Template d'email

**Subject** : `WinBoost passe en v2.4 — ton tarif reste à 4,99 EUR/mois`

**Corps** :

> Salut [Prénom],
>
> WinBoost vient de livrer 4 releases en une journée (v2.0 → v2.4) avec :
>
> - Un serveur MCP pour piloter Windows depuis Claude Desktop / Cursor / Code
> - Un module diagnostic qui résout les bugs Windows en 10s (j'ai fixé ma manette PS5 + Rocket League en 2 min — testimonial dans les release notes)
> - 30 actions Windows-natives (luminosité, dark mode, focus, volume précis, bluetooth, DNS, ...)
> - Un onglet GUI Diagnose visuel et cliquable
> - Un mode "Lab" Computer Use BYOK (early access)
>
> En conséquence, le nouveau tarif Pro pour les **nouveaux abonnés** passe à **9,99 EUR/mois** (89 EUR/an), aligné sur Cursor / Claude Pro.
>
> **Toi, tu gardes ton tarif à 4,99 EUR/mois à vie**, tant que ton abonnement reste actif. Pas de migration forcée. Pas de petit caractère.
>
> Merci d'avoir cru au projet quand il était petit. Si tu veux jeter un œil aux nouveautés :
>
> - GitHub : https://github.com/Antoine6958585/winboost
> - Release v2.4.0 : https://github.com/Antoine6958585/winboost/releases/tag/v2.4.0
>
> Tu peux répondre à cet email si tu veux qu'on regarde un bug Windows qui te suit. C'est exactement ce que WinBoost est censé faire.
>
> Cheers,
> Antoine
>
> ---
> *Pour gérer ton abonnement : [Stripe Customer Portal link]*

### 3.4 Envoi

- Préviewe sur ton propre adresse d'abord
- Envoi par batch de 50 si > 100 destinataires (anti-spam)
- Track ouvertures + click-through dans Brevo

---

## Action 4 — Coordination avec Enzo pour le post HN (~30 min)

### 4.1 Brief Enzo

Transmettre le **`docs/briefs/BRIEF-ENZO-T074-post-HN.md`** (à côté de ce fichier) — tout y est documenté.

### 4.2 Décider du jour J ensemble

Critères :
- Ne pas poster avant que **toi** aies fini Stripe + landing + email Pro
- Mardi ou mercredi 8-10h ET = 14h-16h Paris
- Pas un jour de fête US (pas de 4 juillet, Thanksgiving, etc.)
- Idéalement la semaine prochaine

### 4.3 Synchro le matin du jour J

- Confirmer que la landing est bien à jour (les visiteurs HN vont aller voir)
- Vérifier que le `pip install winboost` marche depuis une machine fraîche
- Avoir Discord/Slack ouvert avec Enzo pour réagir aux questions HN ensemble

---

## Critères de succès

- ✅ Stripe nouveau plan opérationnel + checkout testé end-to-end
- ✅ Landing v2.4 publiée avec mention MCP + nouveaux prix
- ✅ Email envoyé aux Pro existants avec leur tarif legacy garanti
- ✅ Premier nouveau Pro signup à 9,99 EUR dans les 7 jours post-HN

---

## À ne **pas** faire

- ❌ Forcer la migration des Pro existants → churn garanti
- ❌ Lancer le Lab Mode commercialement (BYOK) sans avoir validé la traction sur le Pro standard
- ❌ Promettre Computer Use comme feature standard du Pro 9,99 (c'est BYOK Lab, pas Pro)
- ❌ Bump le prix encore plus haut sans avoir testé 9,99 sur 30 jours minimum

---

## Ressources

- Brief Enzo (post HN) : `docs/briefs/BRIEF-ENZO-T074-post-HN.md`
- Repo : https://github.com/Antoine6958585/winboost
- Plan business v2.x : `~/.claude/plans/proud-weaving-walrus.md`
- TODO-HUMAN.md global du projet : `TODO-HUMAN.md`
