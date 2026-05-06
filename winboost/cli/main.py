"""CLI WinBoost — Interface en ligne de commande (Click + Rich)."""

from __future__ import annotations

import json as _json

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from winboost.core.base_module import RiskLevel, ScanResult
from winboost.core.config import Config
from winboost.core.engine import Engine
from winboost.mcp.serializers import (
    route_result_to_dict as _route_result_to_dict,
)

console = Console()

# Couleurs par niveau de risque
RISK_COLORS = {
    RiskLevel.INFO: "blue",
    RiskLevel.LOW: "green",
    RiskLevel.MEDIUM: "yellow",
    RiskLevel.HIGH: "bright_red",
    RiskLevel.CRITICAL: "red",
}


def _create_engine() -> Engine:
    """Cree et initialise l'engine avec tous les modules."""
    config = Config()
    engine = Engine(config)
    engine.discover_modules()
    return engine


@click.group()
@click.version_option(version="2.0.0", prog_name="WinBoost")
def cli() -> None:
    """WinBoost — Le premier assistant Windows qui ne te ment pas."""


@cli.command()
@click.option("--module", "-m", default=None, help="Scanner un module specifique.")
def scan(module: str | None) -> None:
    """Scanner le systeme pour detecter les problemes."""
    engine = _create_engine()

    if not engine.modules:
        console.print("[red]Aucun module charge.[/red]")
        return

    if module:
        # Scan d'un seul module
        try:
            result = engine.scan_module(module)
        except ValueError as e:
            console.print(f"[red]{e}[/red]")
            return
        _display_scan_result(result)
    else:
        # Scan de tous les modules
        console.print(
            Panel(
                f"[bold]Scan de {len(engine.modules)} module(s)...[/bold]",
                title="WinBoost Scan",
                border_style="blue",
            )
        )
        results = engine.scan_all()
        for result in results.values():
            _display_scan_result(result)

        # Resume
        total = sum(r.issue_count for r in results.values())
        console.print(f"\n[bold]{total} probleme(s) detecte(s) au total.[/bold]")


@cli.command()
@click.option("--module", "-m", required=True, help="Module a corriger.")
@click.option("--yes", "-y", is_flag=True, help="Confirmer automatiquement.")
def fix(module: str, yes: bool) -> None:
    """Appliquer les corrections d'un module."""
    engine = _create_engine()

    try:
        scan_result = engine.scan_module(module)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        return

    if not scan_result.has_issues:
        console.print(f"[green]Module '{module}' : aucun probleme a corriger.[/green]")
        return

    # Preview
    preview = engine.preview_module(module, scan_result)
    console.print(Panel(preview, title=f"Preview — {module}", border_style="yellow"))

    # Confirmation
    if not yes and not click.confirm("Appliquer ces corrections ?"):
        console.print("[yellow]Annule.[/yellow]")
        return

    # Application
    fix_result = engine.fix_module(module, scan_result)

    if fix_result.success:
        console.print(f"[green]{fix_result.summary}[/green]")
    else:
        console.print(f"[red]Erreurs : {', '.join(fix_result.errors)}[/red]")

    if fix_result.skipped:
        console.print(f"[yellow]Ignores : {len(fix_result.skipped)} element(s)[/yellow]")


@cli.command()
def info() -> None:
    """Afficher les informations systeme."""
    engine = _create_engine()

    sysinfo = engine.get_module("system_info")
    if sysinfo is None:
        console.print("[red]Module system_info non disponible.[/red]")
        return

    result = sysinfo.scan()

    table = Table(title="Informations Systeme", border_style="blue")
    table.add_column("Element", style="bold")
    table.add_column("Detail")

    for issue in result.issues:
        # Extrait le label et la valeur depuis la description
        parts = issue.description.split(" : ", 1)
        label = parts[0] if len(parts) > 1 else issue.id
        detail = parts[1] if len(parts) > 1 else issue.description
        table.add_row(label, detail)

    console.print(table)


@cli.command(name="modules")
def list_modules() -> None:
    """Lister les modules disponibles."""
    engine = _create_engine()

    if not engine.modules:
        console.print("[yellow]Aucun module charge.[/yellow]")
        return

    table = Table(title="Modules WinBoost", border_style="blue")
    table.add_column("Nom", style="bold")
    table.add_column("Description")
    table.add_column("Risque")

    for mod in engine.modules.values():
        color = RISK_COLORS.get(mod.risk_level, "white")
        table.add_row(mod.name, mod.description, f"[{color}]{mod.risk_level.value}[/{color}]")

    console.print(table)


@cli.command()
@click.argument("query", nargs=-1, required=True)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    help="Sortie JSON pour scripting (pas de couleurs Rich, stdout = JSON pur).",
)
def chat(query: tuple[str, ...], json_output: bool) -> None:
    """Poser une question a l'assistant IA WinBoost.

    Mode JSON (`--json`) : la sortie stdout est un seul objet JSON valide
    parseable par `json.loads()`, conforme au schema suivant :

    \b
    {
      "query": str,                # requete utilisateur originale
      "resolved_by": str,          # "cache" | "llm" | "category_fallback" | "none"
      "message": str,              # message lisible (resume ou erreur)
      "has_actions": bool,         # true si au moins une action autorisee
      "actions": [                 # actions autorisees par le profil
        {
          "id": str,
          "name": str,
          "description": str,
          "category": str,
          "risk_level": str,       # "info" | "low" | "medium" | "high" | "critical"
          "requires_admin": bool,
          "reversible": bool,
          "verdict": {
            "allowed": bool,
            "requires_dry_run": bool,
            "requires_confirmation": bool,
            "reason": str | null
          }
        }
      ],
      "blocked": [ ... ]           # meme schema, actions bloquees par le profil
    }

    \b
    Exit codes :
      0 : succes (avec ou sans actions trouvees)
      1 : erreur (ex: query vide en mode --json)
    """
    from pathlib import Path

    from winboost.ai.action_router import ActionRouter

    query_str = " ".join(query).strip()

    # Cas query vide en mode JSON : sortie structuree + exit 1
    if json_output and not query_str:
        click.echo(_json.dumps({"error": "query is required"}, ensure_ascii=False))
        raise click.exceptions.Exit(1)

    actions_dir = Path(__file__).parent.parent / "actions"
    config = Config()
    router = ActionRouter(config=config, actions_dir=actions_dir)
    result = router.route(query_str)

    if json_output:
        # Mode scripting : aucune sortie Rich vers stdout
        payload = _route_result_to_dict(query_str, result)
        click.echo(_json.dumps(payload, ensure_ascii=False, indent=2))
        return

    # Mode interactif Rich (comportement v2.0 inchange)
    console.print(f"\n  [bold]Requete :[/bold] {query_str}\n")

    if not result.has_actions:
        console.print(f"  [yellow]{result.message}[/yellow]")
        return

    console.print(f"  [bold]{result.message}[/bold]  (via {result.resolved_by})\n")

    for routed in result.actions:
        risk_color = RISK_COLORS.get(
            routed.action.risk_level, "white"
        ) if hasattr(routed.action, 'risk_level') else "white"
        risk_val = routed.action.risk_level
        confirm = " [dry-run]" if routed.verdict.requires_dry_run else ""
        confirm += " [confirmation]" if routed.verdict.requires_confirmation else ""
        console.print(
            f"    [{risk_color}][{risk_val.upper()}][/{risk_color}] "
            f"{routed.action.name} — {routed.action.description}"
            f"[dim]{confirm}[/dim]"
        )

    if result.blocked:
        console.print(f"\n  [red]{len(result.blocked)} action(s) bloquee(s) :[/red]")
        for routed in result.blocked:
            console.print(f"    [red]x[/red] {routed.action.name} — {routed.verdict.reason}")


# Helpers de serialisation deplaces dans `winboost.mcp.serializers` (T070).
# L'alias `_route_result_to_dict` est importe en haut du fichier.


@cli.command()
def gui() -> None:
    """Lancer l'interface graphique WinBoost."""
    from winboost.gui.app import launch_gui
    launch_gui()


@cli.command()
def overlay() -> None:
    """Lancer l'overlay hotkey global (Ctrl+Alt+Espace -> requete texte rapide).

    L'overlay s'enregistre comme listener clavier global et reste en
    foreground. Presse Ctrl+Alt+Espace dans n'importe quelle application pour
    invoquer la mini-fenetre de requete. Ctrl+C dans la console pour arreter.

    Si le hotkey global ne peut pas s'enregistrer (admin requis ou package
    `keyboard` absent), un message clair est affiche et on retombe sur le
    bouton Chat de la GUI principale (`winboost gui`).
    """
    from winboost.gui.hotkey_overlay import run_overlay_foreground
    run_overlay_foreground()


# ---------------------------------------------------------------------------
# Groupe `mcp` — serveur Model Context Protocol + outils d'install (T070, T071)
# ---------------------------------------------------------------------------
#
# Structure :
#   winboost mcp                       -> alias retro-compat de `mcp serve`
#   winboost mcp serve                 -> lance le serveur stdio (T070)
#   winboost mcp install-claude-desktop-> patch claude_desktop_config.json (T071)
#   winboost mcp uninstall-claude-desktop
#   winboost mcp token                 -> affiche le token actuel
#   winboost mcp token --reset         -> regenere le token


def _run_mcp_serve() -> None:
    """Implementation reelle de `winboost mcp serve` (factorisee pour rester
    appelable depuis l'alias retro-compat `winboost mcp`)."""
    try:
        from winboost.mcp.server import run_stdio
    except ImportError as exc:
        click.echo(f"[winboost mcp] {exc}", err=True)
        raise click.exceptions.Exit(1) from exc

    try:
        run_stdio()
    except ImportError as exc:
        click.echo(f"[winboost mcp] {exc}", err=True)
        raise click.exceptions.Exit(1) from exc
    except KeyboardInterrupt:
        click.echo("[winboost mcp] arret demande, bye.", err=True)


@cli.group(
    name="mcp",
    invoke_without_command=True,
)
@click.pass_context
def mcp_group(ctx: click.Context) -> None:
    """Groupe MCP — serveur stdio + integration Claude Desktop.

    \b
    Sous-commandes :
      serve                     Lance le serveur MCP stdio
      install-claude-desktop    Ajoute WinBoost a claude_desktop_config.json
      uninstall-claude-desktop  Retire WinBoost de claude_desktop_config.json
      token                     Affiche le token MCP local (option --reset)

    \b
    Retro-compat : `winboost mcp` (sans sous-commande) = `winboost mcp serve`.
    Necessite l'extra `mcp` pour `serve` :

    \b
        pip install winboost[mcp]
    """
    if ctx.invoked_subcommand is None:
        # Comportement retro-compat : `winboost mcp` -> `winboost mcp serve`.
        _run_mcp_serve()


@mcp_group.command(name="serve")
def mcp_serve_cmd() -> None:
    """Lancer le serveur MCP WinBoost (transport stdio).

    Expose 5 tools (chat, scan, apply, list_actions, undo) consommables par
    Claude Desktop, Cursor, Claude Code et tout client MCP compatible.

    stdout est reserve au protocole JSON-RPC ; les logs partent sur stderr.
    Ctrl+C pour arreter.
    """
    _run_mcp_serve()


@mcp_group.command(name="install-claude-desktop")
@click.option(
    "--dry-run",
    is_flag=True,
    help="N'ecrit rien — affiche le bloc JSON qui serait ajoute.",
)
@click.option(
    "--force",
    is_flag=True,
    help="Remplace l'entree winboost si elle existe deja.",
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    help="Sortie JSON pour scripting.",
)
def mcp_install_claude_desktop_cmd(
    dry_run: bool, force: bool, json_output: bool
) -> None:
    """Patcher `claude_desktop_config.json` pour y ajouter WinBoost.

    \b
    Le bloc ajoute :
      "winboost": {
        "command": "python",
        "args": ["-m", "winboost", "mcp"],
        "env": {"WINBOOST_MCP_TOKEN": "<token genere>"}
      }

    Cree un backup horodate du config existant (claude_desktop_config.json
    .backup-YYYYMMDD-HHMMSS) avant modification.
    """
    from winboost.mcp.install import install_winboost_to_claude_desktop

    try:
        result = install_winboost_to_claude_desktop(dry_run=dry_run, force=force)
    except (OSError, RuntimeError) as exc:
        if json_output:
            click.echo(_json.dumps({"error": str(exc), "type": exc.__class__.__name__}))
        else:
            click.echo(f"[winboost mcp install] {exc}", err=True)
        raise click.exceptions.Exit(1) from exc

    if json_output:
        click.echo(_json.dumps(result, ensure_ascii=False, indent=2))
        return

    action = result.get("action")
    if action == "dry_run":
        console.print("[yellow]Dry-run :[/yellow] aucun fichier ecrit.")
        console.print(f"  Config cible : [bold]{result['config_path']}[/bold]")
        console.print(f"  Token attendu : [bold]{result['token_path']}[/bold]")
        console.print("\n[bold]Bloc qui serait ajoute :[/bold]")
        console.print(_json.dumps(result["would_add"], indent=2, ensure_ascii=False))
    elif action == "skipped":
        console.print(
            f"[yellow]WinBoost deja installe[/yellow] dans {result['config_path']}. "
            f"Utilise [bold]--force[/bold] pour remplacer."
        )
    elif action == "installed":
        console.print("[green]OK[/green] WinBoost installe dans Claude Desktop.")
        console.print(f"  Config : [bold]{result['config_path']}[/bold]")
        console.print(f"  Token : [bold]{result['token_path']}[/bold]")
        if result.get("backup_path"):
            console.print(f"  Backup : [dim]{result['backup_path']}[/dim]")
        if result.get("replaced"):
            console.print("  [yellow]Entree existante remplacee.[/yellow]")
    else:
        click.echo(_json.dumps(result, ensure_ascii=False, indent=2))


@mcp_group.command(name="uninstall-claude-desktop")
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    help="Sortie JSON pour scripting.",
)
def mcp_uninstall_claude_desktop_cmd(json_output: bool) -> None:
    """Retirer l'entree `winboost` de `claude_desktop_config.json`.

    Les autres serveurs MCP et le reste du config sont preserves.
    Cree un backup horodate avant modification.
    """
    from winboost.mcp.install import uninstall_winboost_from_claude_desktop

    try:
        result = uninstall_winboost_from_claude_desktop()
    except (OSError, RuntimeError) as exc:
        if json_output:
            click.echo(_json.dumps({"error": str(exc), "type": exc.__class__.__name__}))
        else:
            click.echo(f"[winboost mcp uninstall] {exc}", err=True)
        raise click.exceptions.Exit(1) from exc

    if json_output:
        click.echo(_json.dumps(result, ensure_ascii=False, indent=2))
        return

    action = result.get("action")
    if action == "not_installed":
        console.print(f"[yellow]WinBoost n'est pas installe.[/yellow] ({result.get('reason')})")
    elif action == "uninstalled":
        console.print("[green]OK[/green] WinBoost retire de Claude Desktop.")
        console.print(f"  Config : [bold]{result['config_path']}[/bold]")
        console.print(f"  Backup : [dim]{result['backup_path']}[/dim]")
    else:
        click.echo(_json.dumps(result, ensure_ascii=False, indent=2))


@mcp_group.command(name="token")
@click.option(
    "--reset",
    "reset",
    is_flag=True,
    help="Force la regeneration du token (en cas de fuite suspectee).",
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    help="Sortie JSON pour scripting.",
)
def mcp_token_cmd(reset: bool, json_output: bool) -> None:
    """Afficher le token MCP local (ou le regenerer avec --reset).

    Le token est stocke dans :
      - Windows : %APPDATA%/WinBoost/mcp_token.txt
      - POSIX   : ~/.config/winboost/mcp_token.txt
    """
    from winboost.mcp.auth import (
        get_token_path,
        load_or_generate_token,
    )
    from winboost.mcp.auth import (
        reset_token as _reset_token,
    )

    try:
        token = _reset_token() if reset else load_or_generate_token()
    except OSError as exc:
        if json_output:
            click.echo(_json.dumps({"error": str(exc), "type": exc.__class__.__name__}))
        else:
            click.echo(f"[winboost mcp token] {exc}", err=True)
        raise click.exceptions.Exit(1) from exc

    payload = {
        "token": token,
        "token_path": str(get_token_path()),
        "regenerated": bool(reset),
    }
    if json_output:
        click.echo(_json.dumps(payload, ensure_ascii=False, indent=2))
        return

    if reset:
        console.print("[green]Token regenere.[/green]")
    console.print(f"  Token : [bold]{token}[/bold]")
    console.print(f"  Fichier : [dim]{payload['token_path']}[/dim]")


def _display_scan_result(result: ScanResult) -> None:
    """Affiche un ScanResult de maniere formatee."""
    if not result.has_issues:
        console.print(f"  [green][OK][/green] {result.module_name} — Aucun probleme")
        return

    console.print(f"\n  [bold]{result.module_name}[/bold] — {result.summary}")
    for issue in result.issues:
        color = RISK_COLORS.get(issue.risk_level, "white")
        marker = "[*]" if issue.auto_fixable else "[ ]"
        console.print(f"    [{color}]{marker}[/{color}] {issue.description}")


if __name__ == "__main__":
    cli()
