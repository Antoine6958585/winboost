"""Client subprocess pour le POC stdio T072.

Lance le serveur (script Python OU binaire .exe) en subprocess, envoie 3
requetes JSON sur stdin, lit 3 reponses sur stdout, et compare le resultat
avec ce qui est attendu.

Usage :
    python tests/mcp_compat/poc_client.py            # mode Python pur
    python tests/mcp_compat/poc_client.py --exe      # mode binaire .exe

Sortie : exit 0 si tous les tests passent, exit 1 sinon. Detail sur stdout.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SERVER_SCRIPT = REPO_ROOT / "tests" / "mcp_compat" / "poc_mcp_server.py"
SERVER_EXE = REPO_ROOT / "dist" / "poc_mcp_server.exe"

REQUESTS = [
    {"id": 1, "method": "echo", "params": {"hello": "world"}},
    {"id": 2, "method": "add", "params": {"a": 7, "b": 35}},
    {"id": 3, "method": "unicode"},
]
EXPECTED = [
    {"id": 1, "result": {"hello": "world"}},
    {"id": 2, "result": 42},
    {"id": 3, "result": "cafe + emoji rocket = succes"},
]

TIMEOUT_SECONDS = 15.0


def build_command(use_exe: bool) -> list[str]:
    """Construit la commande de lancement du serveur (script ou .exe)."""
    if use_exe:
        if not SERVER_EXE.exists():
            raise FileNotFoundError(
                f"Binaire serveur introuvable : {SERVER_EXE}. "
                "Lance d'abord `python tests/mcp_compat/build_poc.py`."
            )
        return [str(SERVER_EXE)]
    if not SERVER_SCRIPT.exists():
        raise FileNotFoundError(f"Script serveur introuvable : {SERVER_SCRIPT}")
    return [sys.executable, str(SERVER_SCRIPT)]


def run_session(use_exe: bool) -> tuple[bool, str]:
    """Lance le serveur, envoie les requetes, lit les reponses.

    Retourne (succes, message). Le message contient un resume textuel.
    """
    cmd = build_command(use_exe)
    label = "EXE" if use_exe else "PYTHON"
    print(f"[client] mode={label} cmd={cmd}")

    # bufsize=1 = line-buffered cote client.
    # text=True + encoding utf-8 = on lit/ecrit des str, pas des bytes.
    # creationflags=0 sur non-Windows, on garde stderr pour le diagnostic.
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        bufsize=1,
    )

    start = time.monotonic()
    responses: list[dict] = []
    try:
        for req in REQUESTS:
            line = json.dumps(req, ensure_ascii=False) + "\n"
            assert proc.stdin is not None
            proc.stdin.write(line)
            proc.stdin.flush()

            assert proc.stdout is not None
            raw = proc.stdout.readline()
            elapsed = time.monotonic() - start
            if not raw:
                return False, (
                    f"[{label}] reponse vide pour req={req} apres {elapsed:.2f}s "
                    "(stdout ferme ou serveur crashe)"
                )
            if elapsed > TIMEOUT_SECONDS:
                return False, f"[{label}] timeout > {TIMEOUT_SECONDS}s"

            try:
                resp = json.loads(raw)
            except json.JSONDecodeError as e:
                return False, f"[{label}] reponse non-JSON: {raw!r} ({e})"
            responses.append(resp)
            print(f"[client] req={req}  ->  resp={resp}")

        # Ferme stdin pour signaler EOF au serveur, puis attend la sortie.
        assert proc.stdin is not None
        proc.stdin.close()
        try:
            proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            return False, f"[{label}] le serveur ne s'est pas arrete proprement apres EOF"

    finally:
        if proc.poll() is None:
            proc.kill()
        # Drain stderr pour le rapport.
        try:
            stderr_out = proc.stderr.read() if proc.stderr else ""
        except Exception:  # noqa: BLE001
            stderr_out = "<stderr non lisible>"
        if stderr_out:
            print(f"[client] stderr du serveur :\n{stderr_out.rstrip()}")

    # Comparaison.
    failures: list[str] = []
    for got, want in zip(responses, EXPECTED, strict=False):
        if got != want:
            failures.append(f"  mismatch: got={got} want={want}")

    if failures:
        return False, f"[{label}] {len(failures)} test(s) en echec:\n" + "\n".join(failures)
    return True, f"[{label}] 3/3 tests OK"


def main() -> int:
    parser = argparse.ArgumentParser(description="Client POC stdio T072")
    parser.add_argument(
        "--exe",
        action="store_true",
        help="Utilise dist/poc_mcp_server.exe au lieu du script Python",
    )
    args = parser.parse_args()

    ok, message = run_session(use_exe=args.exe)
    print(message)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
