"""Script de build WinBoost — genere l'executable .exe via PyInstaller."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Modules a inclure dans le build
HIDDEN_IMPORTS = [
    "winboost.modules.temp_cleaner",
    "winboost.modules.system_info",
    "winboost.modules.startup_manager",
    "winboost.modules.ram_optimizer",
    "winboost.modules.disk_analyzer",
    "winboost.modules.privacy_cleaner",
    "winboost.modules.dev_cache_cleaner",
    "winboost.modules.service_optimizer",
    "winboost.gui.app",
    "winboost.gui.dashboard",
    "winboost.gui.modules_page",
    "winboost.gui.chat_placeholder",
    "winboost.gui.theme",
    "winboost.core.backup",
    "winboost.core.history",
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
