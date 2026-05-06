"""Mini-serveur stdio JSON line-based — POC pour T072.

Pas de FastMCP, pas de protocole MCP complet. On teste seulement la couche
transport : est-ce qu'un binaire PyInstaller peut lire stdin et ecrire stdout
ligne par ligne en JSON sans corruption / blocage / encoding cassee ?

Protocole :
- Le client ecrit une ligne JSON sur stdin du serveur.
- Le serveur la lit, la traite, et ecrit une ligne JSON sur stdout.
- Une ligne par message, terminee par \\n.
- Encoding UTF-8 force des deux cotes.

Cas testes :
1. echo : renvoie le payload tel quel
2. add : additionne deux entiers
3. unicode : verifie que les caracteres non-ASCII traversent (e accent aigu, emoji)

Sortie d'erreur :
- toute exception est encapsulee en {"error": str(e)} sur stdout
- les logs internes vont sur stderr (pas sur stdout pour ne pas polluer le
  canal de transport)
"""

from __future__ import annotations

import json
import sys


def _force_utf8() -> None:
    """Force stdin/stdout en UTF-8 + line-buffered.

    Sur Windows, sys.stdout est en cp1252 par defaut sous PyInstaller console
    mode. Cela casse les chaines unicode. On reconfigure explicitement.

    Sur Python 3.7+, TextIOWrapper.reconfigure() est disponible.
    """
    try:
        # type: ignore[attr-defined] pour les sources qui ne reconnaissent
        # pas reconfigure (ajoute en 3.7).
        sys.stdin.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        # Si reconfigure n'est pas dispo (sources tres rares), on log mais on
        # continue. Ce sera un signal NO-GO partiel.
        sys.stderr.write("[server] WARN: stdio reconfigure failed\n")
        sys.stderr.flush()


def handle(request: dict) -> dict:
    """Traite une requete et retourne une reponse."""
    method = request.get("method")
    if method == "echo":
        return {"id": request.get("id"), "result": request.get("params")}
    if method == "add":
        params = request.get("params") or {}
        a = int(params.get("a", 0))
        b = int(params.get("b", 0))
        return {"id": request.get("id"), "result": a + b}
    if method == "unicode":
        # Renvoie une chaine unicode pour valider l'encoding sortant.
        return {
            "id": request.get("id"),
            "result": "cafe + emoji rocket = succes",
        }
    return {"id": request.get("id"), "error": f"unknown method: {method}"}


def main() -> int:
    _force_utf8()
    sys.stderr.write("[server] ready\n")
    sys.stderr.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as e:
            response = {"error": f"invalid json: {e}"}
        else:
            try:
                response = handle(request)
            except Exception as e:  # noqa: BLE001
                response = {"id": request.get("id"), "error": str(e)}

        # Ecriture + flush explicite. Sans flush, le bootloader PyInstaller
        # peut bufferiser indefiniment et le client timeout.
        sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
        sys.stdout.flush()

    sys.stderr.write("[server] stdin closed, exit\n")
    sys.stderr.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
