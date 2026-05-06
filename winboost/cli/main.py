"""CLI WinBoost — Interface en ligne de commande (Click + Rich)."""

from __future__ import annotations

import json as _json
from typing import Any

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from winboost.core.base_module import RiskLevel, ScanResult
from winboost.core.config import Config
from winboost.core.engine import Engine

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


def _routed_action_to_dict(routed: Any) -> dict[str, Any]:
    """Serialise un RoutedAction (action + verdict) en dict JSON-compatible.

    Convertit explicitement Action et SafetyVerdict en types primitifs.
    `verdict.reason` devient `null` si chaine vide pour distinguer "pas de raison"
    de "raison vide".
    """
    action = routed.action
    verdict = routed.verdict
    return {
        "id": action.id,
        "name": action.name,
        "description": action.description,
        "category": action.category,
        "risk_level": action.risk_level,
        "requires_admin": bool(action.requires_admin),
        "reversible": bool(action.reversible),
        "verdict": {
            "allowed": bool(verdict.allowed),
            "requires_dry_run": bool(verdict.requires_dry_run),
            "requires_confirmation": bool(verdict.requires_confirmation),
            "reason": verdict.reason if verdict.reason else None,
        },
    }


def _route_result_to_dict(query: str, result: Any) -> dict[str, Any]:
    """Serialise un RouteResult en dict JSON-compatible (schema documente sur `chat`)."""
    return {
        "query": query,
        "resolved_by": result.resolved_by,
        "message": result.message,
        "has_actions": bool(result.has_actions),
        "actions": [_routed_action_to_dict(r) for r in result.actions],
        "blocked": [_routed_action_to_dict(r) for r in result.blocked],
    }


@cli.command()
def gui() -> None:
    """Lancer l'interface graphique WinBoost."""
    from winboost.gui.app import launch_gui
    launch_gui()


@cli.command()
def overlay() -> None:
    """Lancer l'overlay hotkey global (Win+Espace -> requete texte rapide).

    L'overlay s'enregistre comme listener clavier global et reste en
    foreground. Presse Win+Espace dans n'importe quelle application pour
    invoquer la mini-fenetre de requete. Ctrl+C dans la console pour arreter.

    Si le hotkey global ne peut pas s'enregistrer (admin requis ou package
    `keyboard` absent), un message clair est affiche et on retombe sur le
    bouton Chat de la GUI principale (`winboost gui`).
    """
    from winboost.gui.hotkey_overlay import run_overlay_foreground
    run_overlay_foreground()


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
