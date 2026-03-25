"""CLI WinBoost — Interface en ligne de commande (Click + Rich)."""

from __future__ import annotations

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
@click.version_option(version="0.1.0", prog_name="WinBoost")
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
    if not yes:
        if not click.confirm("Appliquer ces corrections ?"):
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
def gui() -> None:
    """Lancer l'interface graphique WinBoost."""
    from winboost.gui.app import launch_gui
    launch_gui()


def _display_scan_result(result: "ScanResult") -> None:
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
