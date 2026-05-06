# winboost.mcp — Serveur Model Context Protocol pour WinBoost

Sous-package optionnel qui expose WinBoost en tant que **serveur MCP**
consommable par Claude Desktop, Cursor, Claude Code et tout client MCP
compatible.

## Installation

L'extra `mcp` n'est pas installe par defaut (zero overhead pour les utilisateurs
GUI/CLI standards). Active-le avec :

```bash
pip install winboost[mcp]
```

Cela installe `fastmcp>=0.2`. Le sous-module `winboost.mcp` est alors
fonctionnel ; sans cet extra, l'import de `winboost.mcp.server` leve une
`ImportError` avec un message clair.

## Lancement

```bash
winboost mcp serve
# ou (alias retro-compat)
winboost mcp
```

Demarre le serveur FastMCP en transport **stdio** (mode standard Claude Desktop).
Aucune sortie sur stdout (reserve au protocole) — toutes les logs partent sur
stderr. `Ctrl+C` pour arreter.

## Installation Claude Desktop (T071)

WinBoost fournit deux commandes pour patcher automatiquement
`claude_desktop_config.json` :

```bash
# Installer (genere un token MCP local + ajoute l'entree winboost) :
winboost mcp install-claude-desktop

# Apercu sans modifier le fichier :
winboost mcp install-claude-desktop --dry-run

# Remplacer une entree existante :
winboost mcp install-claude-desktop --force

# Sortie JSON (scripting) :
winboost mcp install-claude-desktop --json

# Retirer l'entree winboost (autres servers preserves) :
winboost mcp uninstall-claude-desktop
```

L'install :

1. Genere (ou recharge) un token local dans :
   - Windows : `%APPDATA%/WinBoost/mcp_token.txt`
   - POSIX  : `~/.config/winboost/mcp_token.txt`
2. Cree un backup horodate du config existant
   (`claude_desktop_config.json.backup-YYYYMMDD-HHMMSS`)
3. Ajoute le bloc suivant dans `mcpServers` :

```json
{
  "mcpServers": {
    "winboost": {
      "command": "python",
      "args": ["-m", "winboost", "mcp"],
      "env": {
        "WINBOOST_MCP_TOKEN": "<token genere a l'install>"
      }
    }
  }
}
```

Path standard du config Claude Desktop :

| Plateforme | Chemin |
|------------|--------|
| Windows | `%APPDATA%/Claude/claude_desktop_config.json` |
| macOS  | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Linux  | `~/.config/Claude/claude_desktop_config.json` |

### Token MCP local

```bash
# Afficher le token actuel :
winboost mcp token

# Regenerer (en cas de fuite suspectee) :
winboost mcp token --reset
```

Note v2.2 : le transport stdio etant local par nature (pipes parent/child),
le token est principalement defensif. Il est expose via la variable
d'environnement `WINBOOST_MCP_TOKEN` et prepare la voie pour un futur
transport HTTP/SSE.

### Ship binaire dedie (v2.2.x)

Pour l'instant, `command: "python"` + `args: ["-m", "winboost", "mcp"]`
suppose que l'utilisateur a installe `winboost` via pip dans un environnement
accessible (`pip install winboost[mcp]`).

A terme (cf. `tests/mcp_compat/VERDICT.md`), un binaire `winboost-mcp.exe`
PyInstaller dedie (~7 Mo, cold-start ~300 ms) pourra remplacer cette ligne :

```json
{ "command": "winboost-mcp.exe" }
```

Les 3 invariants stdio sont valides empiriquement (UTF-8, flush, --console).

## Tools exposes

Les 5 tools couvrent l'ensemble des capacites WinBoost cote IA :

| Tool | Input | Output |
|------|-------|--------|
| `chat` | `query: str` | `{query, resolved_by, message, has_actions, actions[], blocked[]}` |
| `scan` | `module: str \| None` | `{modules: {...}, module_count, total_issues}` ou `ScanResultDict` |
| `apply` | `action_id: str` | `{success, message, action_id, rollback_id, status, history_entry_id}` |
| `list_actions` | `category: str \| None` | `{actions: [...], count, category}` |
| `undo` | `rollback_id: str` | `{success, message, rollback_id, files_restored, errors}` |

### Conventions d'erreur

Chaque tool retourne `{"error": str, "type": str}` plutot que de lever une
exception (qui ferait crasher l'appel cote MCP). `type` est le nom de classe
Python (`ValueError`, `KeyError`...).

### Comportement `apply`

L'execution reelle des YAML (registry_set, powershell, service_*) est
catalogue en v2.x — l'action est enregistree dans l'historique avec status
`catalogued` (idem GUI v2.0/v2.1). L'executor systeme branche les YAML est
prevu post-MCP standalone.

### Comportement `undo`

`rollback_id` correspond au `backup_id` retourne par les backups WinBoost
(cf. `winboost.core.backup.BackupManager`). Restaure les fichiers concernes et
trace dans l'historique avec `action_type="restore"`.

## Architecture

```
winboost/mcp/
  __init__.py         # exports create_server (lazy)
  server.py           # FastMCP + 5 tools + run_stdio()
  serializers.py      # routed_action_to_dict / scan_result_to_dict / ...
  README.md           # ce fichier
```

Aucun side-effect a l'import — instancier `create_server()` est obligatoire
pour materialiser le FastMCP et ses tools.

## Tests

```bash
python -m pytest tests/test_mcp/ -v
```

12+ tests couvrent : creation du serveur, signature des 5 tools, schema des
retours, cas d'erreur (query vide, module inconnu, action_id inconnu,
rollback_id inconnu, category invalide).
