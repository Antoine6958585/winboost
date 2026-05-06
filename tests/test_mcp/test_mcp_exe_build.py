"""Tests pour le binaire `winboost-mcp.exe` (T072 polish A — Phase 13 v2.4).

Ces tests valident que :

1. `winboost/mcp/__main__.py` existe et expose `main()` + `_force_utf8()`.
2. `_force_utf8()` ne crashe jamais — meme si `sys.stdin.reconfigure` est
   indisponible (cas des stdin/stdout custom non-TextIOWrapper).
3. `main()` peut etre appele avec `run_stdio` mocke et propage le bon code
   de sortie selon le scenario (succes, KeyboardInterrupt, exception fatale).
4. `build_mcp.py` existe a la racine, expose `build()` callable, et possede
   les hidden_imports + exclusions documentes pour respecter la cible de
   taille (10-15 Mo ideal, 25 Mo max).

ATTENTION : ces tests NE LANCENT PAS PyInstaller (build reel coute ~10-30 s
et n'est pas fiable en CI Windows headless). Le build reel est valide
manuellement via `python build_mcp.py` lors du release tagging.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Tests : winboost/mcp/__main__.py — existence et structure
# ---------------------------------------------------------------------------


class TestMcpMainModuleExists:
    """Verifie l'existence et la structure du module entry-point."""

    def test_main_module_file_exists(self) -> None:
        """Le fichier winboost/mcp/__main__.py doit exister."""
        path = REPO_ROOT / "winboost" / "mcp" / "__main__.py"
        assert path.exists(), f"__main__.py manquant : {path}"
        assert path.is_file()

    def test_main_module_imports_cleanly(self) -> None:
        """Le module doit s'importer sans deps lourdes (pas de fastmcp au load)."""
        # Si l'import echoue ici, c'est qu'on a importe fastmcp/run_stdio
        # au top-level — interdit (lazy import dans main()).
        from winboost.mcp import __main__ as entry  # noqa: PLC0415

        assert hasattr(entry, "main"), "main() doit etre defini"
        assert hasattr(entry, "_force_utf8"), "_force_utf8() doit etre defini"
        assert callable(entry.main)
        assert callable(entry._force_utf8)


# ---------------------------------------------------------------------------
# Tests : _force_utf8() — robustesse
# ---------------------------------------------------------------------------


class TestForceUtf8:
    """Le helper UTF-8 doit etre defensif : il ne crashe JAMAIS au boot."""

    def test_force_utf8_no_crash_on_normal_streams(self) -> None:
        """Sur des streams normaux (TextIOWrapper), reconfigure() est dispo."""
        from winboost.mcp.__main__ import _force_utf8  # noqa: PLC0415

        # Ne doit pas lever
        _force_utf8()

    def test_force_utf8_handles_missing_reconfigure(self) -> None:
        """Si stdin n'a pas reconfigure() (StringIO, mock), ne pas crasher."""
        from winboost.mcp.__main__ import _force_utf8  # noqa: PLC0415

        fake_stdin = io.StringIO()  # pas de .reconfigure()
        fake_stdout = io.StringIO()
        with patch.object(sys, "stdin", fake_stdin), patch.object(sys, "stdout", fake_stdout):
            _force_utf8()  # doit passer silencieusement

    def test_force_utf8_handles_value_error(self) -> None:
        """Si reconfigure() leve ValueError (encoding non supporte), absorber."""
        from winboost.mcp.__main__ import _force_utf8  # noqa: PLC0415

        broken = MagicMock()
        broken.reconfigure.side_effect = ValueError("encoding not supported")
        with patch.object(sys, "stdin", broken), patch.object(sys, "stdout", broken):
            # Ne doit pas remonter l'exception
            _force_utf8()

        # Verifie qu'on a bien tente le reconfigure
        assert broken.reconfigure.call_count >= 1

    def test_force_utf8_handles_os_error(self) -> None:
        """Si reconfigure() leve OSError (stream redirige bizarrement), absorber."""
        from winboost.mcp.__main__ import _force_utf8  # noqa: PLC0415

        broken = MagicMock()
        broken.reconfigure.side_effect = OSError("redirected")
        with patch.object(sys, "stdin", broken), patch.object(sys, "stdout", broken):
            _force_utf8()  # ne doit pas crasher

    def test_force_utf8_calls_with_correct_kwargs(self) -> None:
        """stdout doit etre reconfigure avec line_buffering=True."""
        from winboost.mcp.__main__ import _force_utf8  # noqa: PLC0415

        fake_stdin = MagicMock()
        fake_stdout = MagicMock()
        with patch.object(sys, "stdin", fake_stdin), patch.object(sys, "stdout", fake_stdout):
            _force_utf8()

        # stdin : reconfigure UTF-8
        fake_stdin.reconfigure.assert_called_once_with(encoding="utf-8")
        # stdout : reconfigure UTF-8 + line_buffering=True (defensif vs invariant 2)
        fake_stdout.reconfigure.assert_called_once_with(
            encoding="utf-8", line_buffering=True
        )


# ---------------------------------------------------------------------------
# Tests : main() — orchestration et codes de sortie
# ---------------------------------------------------------------------------


class TestMainEntryPoint:
    """main() est l'entry du .exe — doit retourner un int et propre."""

    def test_main_calls_run_stdio_and_returns_zero(self) -> None:
        """Cas nominal : run_stdio termine sans exception -> code 0."""
        # Mock le module server pour eviter d'importer fastmcp en CI
        fake_run_stdio = MagicMock(return_value=None)
        with patch.dict(sys.modules, {"winboost.mcp.server": MagicMock(run_stdio=fake_run_stdio)}):
            from winboost.mcp.__main__ import main  # noqa: PLC0415

            code = main()

        assert code == 0
        fake_run_stdio.assert_called_once()

    def test_main_handles_keyboard_interrupt_cleanly(self) -> None:
        """Ctrl+C / SIGINT : sortie propre code 0 (pas un echec)."""
        fake_run_stdio = MagicMock(side_effect=KeyboardInterrupt())
        with patch.dict(sys.modules, {"winboost.mcp.server": MagicMock(run_stdio=fake_run_stdio)}):
            from winboost.mcp.__main__ import main  # noqa: PLC0415

            code = main()

        assert code == 0, "Ctrl+C doit retourner 0, pas un code d'erreur"

    def test_main_returns_one_on_fatal_exception(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Exception non geree : code 1 + message lisible sur stderr."""
        fake_run_stdio = MagicMock(side_effect=RuntimeError("boom"))
        with patch.dict(sys.modules, {"winboost.mcp.server": MagicMock(run_stdio=fake_run_stdio)}):
            from winboost.mcp.__main__ import main  # noqa: PLC0415

            code = main()

        assert code == 1
        captured = capsys.readouterr()
        assert "boom" in captured.err
        assert "winboost-mcp" in captured.err
        # CRITIQUE : rien sur stdout (reserve au protocole JSON-RPC)
        assert captured.out == ""

    def test_main_handles_import_error_for_missing_fastmcp(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Si fastmcp manque, run_stdio leve ImportError -> code 1 + stderr."""
        fake_run_stdio = MagicMock(
            side_effect=ImportError("Le module MCP necessite pip install winboost[mcp]")
        )
        with patch.dict(sys.modules, {"winboost.mcp.server": MagicMock(run_stdio=fake_run_stdio)}):
            from winboost.mcp.__main__ import main  # noqa: PLC0415

            code = main()

        assert code == 1
        captured = capsys.readouterr()
        assert "winboost[mcp]" in captured.err
        # Important : aucune fuite sur stdout
        assert captured.out == ""

    def test_main_calls_force_utf8_before_run_stdio(self) -> None:
        """L'ordre est critique : reconfigurer UTF-8 AVANT de lire stdin."""
        call_order: list[str] = []

        def _track_utf8() -> None:
            call_order.append("force_utf8")

        def _track_run() -> None:
            call_order.append("run_stdio")

        fake_server = MagicMock(run_stdio=MagicMock(side_effect=_track_run))
        with patch.dict(sys.modules, {"winboost.mcp.server": fake_server}):
            from winboost.mcp import __main__ as entry  # noqa: PLC0415

            with patch.object(entry, "_force_utf8", side_effect=_track_utf8):
                entry.main()

        assert call_order == ["force_utf8", "run_stdio"], (
            f"Ordre incorrect : {call_order}. _force_utf8() doit etre appele "
            "avant run_stdio() (cf. invariant 1 du verdict T072)."
        )


# ---------------------------------------------------------------------------
# Tests : build_mcp.py — existence, callable, structure
# ---------------------------------------------------------------------------


class TestBuildMcpScript:
    """Le script build_mcp.py doit etre callable et bien structure."""

    def test_build_mcp_file_exists_at_root(self) -> None:
        """build_mcp.py doit etre a la racine du projet, a cote de build.py."""
        path = REPO_ROOT / "build_mcp.py"
        assert path.exists(), f"build_mcp.py manquant : {path}"
        assert path.is_file()

    def test_build_mcp_does_not_modify_build_py(self) -> None:
        """build.py et build_mcp.py doivent cohabiter sans modifier l'un l'autre."""
        build_py = REPO_ROOT / "build.py"
        build_mcp_py = REPO_ROOT / "build_mcp.py"
        assert build_py.exists(), "build.py existant ne doit pas etre supprime"
        assert build_mcp_py.exists(), "build_mcp.py doit exister en parallele"
        # Ils sont des fichiers distincts
        assert build_py.read_text(encoding="utf-8") != build_mcp_py.read_text(encoding="utf-8")

    def test_build_mcp_module_imports(self) -> None:
        """build_mcp.py doit s'importer sans deps lourdes au top-level."""
        # On charge le module via importlib pour eviter de polluer sys.modules
        # avec un nom non-namespace. spec_from_file_location prend en charge ca.
        import importlib.util  # noqa: PLC0415

        spec = importlib.util.spec_from_file_location(
            "build_mcp_module", REPO_ROOT / "build_mcp.py"
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        assert hasattr(module, "build"), "build_mcp.py doit exposer build()"
        assert callable(module.build)
        # main() est un alias public optionnel mais documente
        assert hasattr(module, "main"), "build_mcp.py doit exposer main()"
        assert callable(module.main)

    def test_build_mcp_has_minimal_hidden_imports(self) -> None:
        """HIDDEN_IMPORTS doit contenir winboost.mcp.* et winboost.actions.*."""
        import importlib.util  # noqa: PLC0415

        spec = importlib.util.spec_from_file_location(
            "build_mcp_module2", REPO_ROOT / "build_mcp.py"
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        hidden = getattr(module, "HIDDEN_IMPORTS", None)
        assert hidden is not None, "HIDDEN_IMPORTS doit etre defini"
        assert isinstance(hidden, list)

        # Les modules CRITIQUES doivent etre presents
        required = [
            "winboost.mcp.server",
            "winboost.mcp.serializers",
            "winboost.actions.loader",
            "winboost.ai.action_router",
            "winboost.core.engine",
            "winboost.core.executor",
            "fastmcp",
        ]
        for mod in required:
            assert mod in hidden, f"hidden_import manquant : {mod}"

    def test_build_mcp_excludes_gui_stack(self) -> None:
        """EXCLUDED_MODULES doit exclure tkinter/customtkinter/PIL/pyautogui."""
        import importlib.util  # noqa: PLC0415

        spec = importlib.util.spec_from_file_location(
            "build_mcp_module3", REPO_ROOT / "build_mcp.py"
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        excluded = getattr(module, "EXCLUDED_MODULES", None)
        assert excluded is not None, "EXCLUDED_MODULES doit etre defini"
        assert isinstance(excluded, list)

        # Ces exclusions sont la raison d'etre du binaire separe
        gui_stack_to_exclude = [
            "tkinter",
            "customtkinter",
            "PIL",
            "pyautogui",
            "winboost.gui",
            "winboost.pilot",
        ]
        for mod in gui_stack_to_exclude:
            assert mod in excluded, (
                f"EXCLUDED_MODULES doit contenir '{mod}' "
                "(sinon le binaire MCP grossit inutilement)"
            )

    def test_build_mcp_does_not_run_pyinstaller_on_import(self) -> None:
        """Importer build_mcp.py ne doit JAMAIS lancer PyInstaller.

        Garantit qu'on peut tester la structure sans build reel (10-30s).
        """
        # Si subprocess.run etait appele a l'import, ce test prendrait
        # plusieurs secondes. On verifie qu'on importe vite.
        import importlib.util  # noqa: PLC0415
        import time  # noqa: PLC0415

        start = time.monotonic()
        spec = importlib.util.spec_from_file_location(
            "build_mcp_module4", REPO_ROOT / "build_mcp.py"
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        elapsed = time.monotonic() - start

        assert elapsed < 2.0, (
            f"L'import de build_mcp.py a pris {elapsed:.2f}s — il y a probablement "
            "un side-effect (PyInstaller, build) au top-level a deplacer dans build()."
        )
