"""Script de build WinBoost — genere l'executable .exe via PyInstaller."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Modules a inclure dans le build
HIDDEN_IMPORTS = [
    # Modules systeme
    "winboost.modules.temp_cleaner",
    "winboost.modules.system_info",
    "winboost.modules.startup_manager",
    "winboost.modules.ram_optimizer",
    "winboost.modules.disk_analyzer",
    "winboost.modules.privacy_cleaner",
    "winboost.modules.dev_cache_cleaner",
    "winboost.modules.service_optimizer",
    # GUI
    "winboost.gui.app",
    "winboost.gui.dashboard",
    "winboost.gui.modules_page",
    "winboost.gui.chat",
    "winboost.gui.chat_placeholder",
    "winboost.gui.history_page",
    "winboost.gui.settings_page",
    "winboost.gui.onboarding",
    "winboost.gui.theme",
    "winboost.gui.diagnose_page",  # v2.3 nouvel onglet Diagnose
    "winboost.gui.hotkey_overlay",  # v2.1 overlay Ctrl+Alt+Espace
    # Core
    "winboost.core.backup",
    "winboost.core.history",
    "winboost.core.config",
    "winboost.core.executor",  # v2.3 executor reel des actions YAML
    # AI Engine
    "winboost.ai.nl_parser",
    "winboost.ai.action_router",
    "winboost.ai.safety_engine",
    "winboost.ai.cache",
    "winboost.ai.providers.base",
    "winboost.ai.providers.anthropic_provider",
    "winboost.ai.providers.openai_provider",
    "winboost.ai.providers.ollama_provider",
    # Actions
    "winboost.actions.loader",
    "winboost.actions.schema",
    # Diagnose v2.3
    "winboost.diagnose.runner",
    "winboost.diagnose.checks",
    "winboost.diagnose.themes.bluetooth",
    "winboost.diagnose.themes.gaming",
    "winboost.diagnose.themes.network",
    "winboost.diagnose.themes.audio",
    "winboost.diagnose.themes.display",
    # Utils v2.1
    "winboost.utils.windows_native",
    "winboost.utils.admin",
    # Note : winboost.mcp.* et winboost.pilot.* NON inclus volontairement
    # (extras optionnels via `pip install winboost[mcp]` / `winboost[pilot]`).
    # Le .exe GUI principal reste lean pour eviter +10 Mo de deps optionnelles.
]


def build() -> None:
    """Lance le build PyInstaller en mode one-file."""
    root = Path(__file__).parent

    print("=" * 60)
    print("WinBoost — Build .exe")
    print("=" * 60)

    # Verifie PyInstaller
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller non installe. Installation...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller>=6.0"])

    # Construit la commande
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--clean",
        "--noconfirm",
        "--name", "WinBoost",
        "--console",
    ]

    # Icone si disponible
    icon = root / "assets" / "icon.ico"
    if icon.exists():
        cmd.extend(["--icon", str(icon)])

    # Hidden imports
    for mod in HIDDEN_IMPORTS:
        cmd.extend(["--hidden-import", mod])

    # Data files (actions YAML)
    actions_dir = root / "winboost" / "actions"
    for category_dir in sorted(actions_dir.iterdir()):
        if category_dir.is_dir() and not category_dir.name.startswith("_"):
            for yaml_file in category_dir.glob("*.yaml"):
                dest = f"winboost/actions/{category_dir.name}"
                cmd.extend(["--add-data", f"{yaml_file};{dest}"])

    # Exclusions
    for exc in ["pytest", "pytest_mock", "pytest_cov", "ruff"]:
        cmd.extend(["--exclude-module", exc])

    # Entrypoint
    cmd.append(str(root / "winboost" / "cli" / "main.py"))

    print(f"\nCommande : {' '.join(cmd)}\n")
    result = subprocess.run(cmd, cwd=str(root))

    if result.returncode == 0:
        exe_path = root / "dist" / "WinBoost.exe"
        if exe_path.exists():
            size_mb = exe_path.stat().st_size / (1024 * 1024)
            print(f"\nBuild OK : {exe_path} ({size_mb:.1f} Mo)")
        else:
            print("\nBuild termine mais .exe introuvable dans dist/")
    else:
        print(f"\nBuild echoue (code {result.returncode})")
        sys.exit(1)


if __name__ == "__main__":
    build()
