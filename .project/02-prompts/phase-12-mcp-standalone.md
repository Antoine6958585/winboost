# Phase 12 — MCP Standalone Package (v2.2)

> Prompt d'invocation prêt à utiliser **après** que la phase 11 soit stable
> (T063 → T068 done, tests verts, hotkey validé sur 10 apps).
>
> Tâches couvertes : T069 → T075
> Effort estimé : 10-14 h dev
> Plan source : `C:/Users/Dezmen/.claude/plans/proud-weaving-walrus.md`

---

## Identité Spine

`A:/dev/spine/_agents/development/backend-architect.md`
*(ou Backend Architect en subagent_type natif)*

Cette phase est plus architecturale (refactor monorepo + nouveau package).
Préférer Backend Architect plutôt que Backend Developer.

## Contexte projet

Lis dans cet ordre :

1. `A:/dev/winboost/CLAUDE.md`
2. `A:/dev/winboost/status.yaml` (vérifier que phase 11 est `done`)
3. `A:/dev/winboost/.project/MASTER-PLAN.md`
4. `A:/dev/winboost/.project/06-agent-logs/2026-05-06-claude-code-plan-evolution-v2.1-v2.3.md`
5. Log de fin de phase 11 dans `06-agent-logs/`
6. `A:/dev/winboost/pyproject.toml` (structure actuelle)
7. `A:/dev/winboost/winboost/ai/action_router.py` (à wrapper en MCP)
8. `A:/dev/winboost/winboost/core/engine.py` (à wrapper en MCP)
9. **Documentation MCP officielle** via Context7 :
   - `mcp__context7__resolve-library-id` avec query "modelcontextprotocol python sdk"
   - Puis `mcp__context7__query-docs` pour FastMCP patterns

## Mission

Distribuer WinBoost massivement via le protocole MCP en faisant de
`winboost-mcp` un package PyPI léger, distinct de la GUI.

### T069 — Refactor monorepo 3 packages (~4 h)

Structure cible :

```
A:/dev/winboost/
├── packages/
│   ├── winboost-core/           # Logique métier partagée
│   │   ├── pyproject.toml       # Pure Python, peu de deps
│   │   ├── winboost_core/
│   │   │   ├── ai/              # ActionRouter, NLParser, SafetyEngine, cache, providers
│   │   │   ├── actions/         # YAML registry + loader + schema
│   │   │   ├── core/            # base_module, engine, config, backup, history
│   │   │   ├── modules/         # 8 modules existants
│   │   │   └── utils/           # helpers + windows_native.py
│   │   └── tests/
│   ├── winboost-gui/            # .exe payant (CustomTkinter + Pro features)
│   │   ├── pyproject.toml       # depends on winboost-core
│   │   ├── winboost_gui/
│   │   │   ├── ui/              # ChatPage, dashboard, hotkey_overlay
│   │   │   ├── cli/             # Click CLI
│   │   │   └── pilot/           # (vide pour l'instant, pour v2.3)
│   │   └── tests/
│   └── winboost-mcp/            # Package MCP standalone (PyPI gratuit)
│       ├── pyproject.toml       # depends on winboost-core + mcp
│       ├── winboost_mcp/
│       │   ├── server.py        # FastMCP server
│       │   ├── tools.py         # 5 tools définis
│       │   └── install.py       # Patcher Claude Desktop config
│       └── tests/
├── pyproject.toml               # Workspace root (poetry/uv workspace)
└── README.md                    # Pointe vers les 3 packages
```

**Stratégie** : utiliser `uv workspaces` ou `poetry` workspace. Pas de duplication
de code — toute la logique est dans `winboost-core`, les deux autres packages
le consomment.

**Critère de succès** : `pip install winboost-core` puis
`from winboost_core.ai import ActionRouter` doit fonctionner. La GUI et le MCP
ne doivent jamais avoir une copie locale d'un fichier de core.

### T070 — Implémentation FastMCP (~6 h)

Dans `packages/winboost-mcp/winboost_mcp/server.py` :

```python
# Squelette à compléter
from mcp.server import FastMCP
from winboost_core.ai import ActionRouter
from winboost_core.core import Engine, Config

server = FastMCP("winboost")

@server.tool()
def winboost_chat(query: str, dry_run: bool = True) -> dict:
    """Route une requête naturelle vers les actions WinBoost (avec dry-run par défaut)."""
    router = ActionRouter(...)
    result = router.route(query)
    return result.to_dict()

@server.tool()
def winboost_scan(module: str | None = None) -> dict:
    """Scan un module spécifique ou tous les modules."""
    ...

@server.tool()
def winboost_apply(action_id: str, dry_run: bool = False) -> dict:
    """Applique une action avec passage obligatoire par SafetyEngine."""
    ...

@server.tool()
def winboost_list_actions(category: str | None = None) -> list[dict]:
    """Liste les actions disponibles (filtrables par catégorie)."""
    ...

@server.tool()
def winboost_undo(last_n: int = 1) -> dict:
    """Annule les N dernières actions via UndoManager."""
    ...

if __name__ == "__main__":
    server.run(transport="stdio")
```

**Auth** : token local généré au premier lancement, stocké dans
`%APPDATA%/winboost/mcp_token`. Lu par le serveur MCP au démarrage. Pas d'auth
nécessaire en stdio (process-local), mais préparer pour streamable-http futur.

### T071 — Commande `winboost-mcp install-claude-desktop` (~1 h)

Script qui :
1. Lit `%APPDATA%/Claude/claude_desktop_config.json`
2. Patche la section `mcpServers` :
   ```json
   {
     "mcpServers": {
       "winboost": {
         "command": "winboost-mcp",
         "args": ["serve"],
         "env": {}
       }
     }
   }
   ```
3. Demande confirmation avant écriture
4. Affiche le message "Restart Claude Desktop to load WinBoost MCP"

### T072 — Test compatibilité PyInstaller-stdio (~1 h)

**Risque #1 du challenge** : PyInstaller buffer stdin/stdout, MCP attend du
JSON-RPC unbuffered. À tester *tôt*.

- Builder un binaire de test avec `pyinstaller --onefile winboost_mcp/server.py`
- Lancer Claude Desktop avec ce binaire au lieu du Python pur
- Vérifier que les tools sont listés et invocables
- Si KO : fallback documenté = ship `winboost-mcp` comme package Python pur (pas de .exe), l'utilisateur installe via `pip install winboost-mcp`

### T073 — 25+ tests d'intégration MCP (~2 h)

- Mock client MCP qui se connecte au serveur en stdio
- 1 test par tool (5 tools)
- Tests de propagation des erreurs (action invalide, profil incompatible)
- Test que SafetyEngine bloque bien les actions hors profil
- Test du `winboost-mcp install-claude-desktop` (avec fixture de config Claude Desktop)

### T074 — Distribution (~2 h, par Enzo)

- Soumission `smithery.ai` (registre MCP communautaire)
- Soumission `anthropic.com/mcp` (registre officiel) si listing communautaire ouvert
- Post HackerNews : "First Windows-system MCP server (open source)"
- README dédié dans `packages/winboost-mcp/README.md` avec démo GIF

### T075 — Pricing Pro 4,99 € → 9,99 € (par Antoine)

- Mise à jour Stripe : nouveau prix par défaut, période de transition pour les Pro existants
- Email aux Pro existants : annonce + grandfather price 4,99 € pendant 6 mois
- Mise à jour landing page (à créer si pas encore faite)
- Communication Product Hunt update : "Pro now includes WinBoost MCP for Claude Desktop / Cursor / Code"

## Livrable obligatoire

Log dans :
```
A:/dev/winboost/.project/06-agent-logs/{DATE}-{agent}-phase-12-mcp-standalone.md
```

Contient :
- Résumé du refactor (couverture des tests avant/après)
- Verdict compatibilité PyInstaller-stdio (CRITICAL)
- Métriques : nb tools MCP, taille du package `winboost-mcp` (.tar.gz et wheel)
- Listage sur registres MCP (URLs)
- Verdict : prêt pour évaluer phase 13 ou pas ?

Mise à jour `status.yaml` : T069 → T075 en `done`. Commit + push.

## Non-négociable

- Aucune duplication de code entre les 3 packages
- Toute action exécutée via MCP DOIT passer par SafetyEngine
- Si test PyInstaller-stdio échoue : ne pas ship un .exe MCP cassé, fallback documenté
- Les 5 tools MCP doivent être documentés dans le README avec exemples d'invocation depuis Claude Desktop
- Pas de credentials / token committés dans le repo
