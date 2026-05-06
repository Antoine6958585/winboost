# T072 — Verdict de compatibilite PyInstaller + MCP stdio

**Date** : 2026-05-06
**Agent** : Backend Architect (Spine)
**Tache** : Phase 12 / risque #1 du plan v2.x — POC empirique
**Source** : `A:/dev/winboost/tests/mcp_compat/`

---

## Verdict net

**GO sous conditions** (NO-GO partiel evite).

Le transport stdio JSON-RPC survit a PyInstaller onefile en console mode sur
Windows 11, **a condition de respecter trois invariants** documentes plus bas.
Le `winboost-mcp` peut etre ship comme `.exe` PyInstaller a la phase 12 (T069
+ T070), il n'y a PAS besoin de fallback "ship en package Python pur".

## Environnement de test

| Element | Version |
|---------|---------|
| OS | Windows 11 Pro 26200 |
| Python | 3.12 (CPython, x64) |
| PyInstaller | 6.20.0 |
| Mode build | `--onefile --console --clean --noconfirm` |
| Taille `.exe` | 7 135 Ko |
| Cold-start (5 runs) | min 297 ms / median 313 ms / max 328 ms |
| Throughput sequential | 50 req en 266 ms (~5.3 ms/req aller-retour) |

## Resultats des 4 commandes de validation

```text
$ pyinstaller --version
6.20.0

$ python tests/mcp_compat/poc_client.py
[client] mode=PYTHON
[client] req={'id': 1, 'method': 'echo', ...}  -> resp={'id': 1, 'result': {...}}
[client] req={'id': 2, 'method': 'add', ...}   -> resp={'id': 2, 'result': 42}
[client] req={'id': 3, 'method': 'unicode'}    -> resp={'id': 3, 'result': 'cafe + emoji rocket = succes'}
[PYTHON] 3/3 tests OK

$ python tests/mcp_compat/build_poc.py
[build] OK : A:\dev\winboost\dist\poc_mcp_server.exe (7135 Ko)

$ python tests/mcp_compat/poc_client.py --exe
[client] mode=EXE
[client] req={'id': 1, 'method': 'echo', ...}  -> resp={'id': 1, 'result': {...}}
[client] req={'id': 2, 'method': 'add', ...}   -> resp={'id': 2, 'result': 42}
[client] req={'id': 3, 'method': 'unicode'}    -> resp={'id': 3, 'result': 'cafe + emoji rocket = succes'}
[EXE] 3/3 tests OK
```

## Tests additionnels (au-dela du brief)

| Test | Resultat |
|------|----------|
| Unicode FR (accents) roundtrip | OK (32 chars in/out, identiques) |
| Unicode JP (kanji) roundtrip | OK (5 chars in/out, identiques) |
| Emoji 4-byte UTF-8 roundtrip | OK (2 chars in/out, identiques) |
| 50 requetes sequentielles | 50/50 OK, 266 ms total (5.32 ms/req) |
| Payload 10 KB | OK (10 000 chars in/out) |
| Payload 100 KB | OK (100 000 chars in/out) |
| Cold-start `.exe` | 297-328 ms (median 313 ms) |
| Mode `--windowed` (no console) | OK aussi (subprocess pipes survivent) |

## Les 3 invariants non negociables

Si on les casse, le verdict bascule en NO-GO partiel. Ils doivent etre codifies
dans le futur `winboost/mcp/server.py` (T070) **avant** la premiere release.

### 1. Reconfigurer stdin/stdout en UTF-8 au demarrage

```python
# OBLIGATOIRE : Windows utilise cp1252 par defaut sous PyInstaller console.
sys.stdin.reconfigure(encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
```

Sans ca, le moindre caractere non-ASCII (e accent, emoji, kanji) leve un
`UnicodeEncodeError` ou produit du mojibake silencieux. Le POC le fait
explicitement dans `_force_utf8()` — voir `poc_mcp_server.py:31`.

Note : sur Python 3.15+ (futur), le PEP 686 force UTF-8 par defaut. D'ici la,
on garde la reconfiguration explicite.

### 2. `sys.stdout.flush()` apres chaque ecriture

```python
sys.stdout.write(json.dumps(response) + "\n")
sys.stdout.flush()  # OBLIGATOIRE — sans ca, le bootloader PyInstaller
                    # peut bufferiser indefiniment et le client timeout
```

Le `line_buffering=True` de la reconfiguration n'est pas suffisant a 100% sous
PyInstaller (le bootloader peut interposer un buffer supplementaire). Le flush
manuel est defensive coding gratuit, on l'applique systematiquement.

### 3. Build en `--console` mode, pas `--windowed`

Empiriquement, `--windowed` (alias `--noconsole`) a aussi fonctionne sur ce
test (subprocess.Popen cree les pipes peu importe le mode du child). MAIS la
documentation PyInstaller indique que `--windowed` redirige `sys.stdout` vers
NUL **en l'absence d'un parent process pipe**. Si un user lance le `.exe`
directement en double-clic, les writes vont dans le vide.

Pour MCP, le client (Claude Desktop, mcp-cli) cree TOUJOURS le pipe avant de
lancer le serveur, donc `--windowed` marcherait — mais on perd les diagnostics
manuels (un dev qui veut tester le serveur a la main).

**Recommandation** : ship en `--console` pour MCP. Le cout est cosmetique
(une fenetre console clignote au demarrage si lance hors d'un client) et la
robustesse de debug est largement superieure.

## Pourquoi ce risque etait dans le plan v2.x

Le risque #1 du plan etait : "PyInstaller capture parfois stdout/stdin de
maniere qui casse le protocole stdio JSON-RPC". Origine du folklore :

1. **Mode `--windowed` historique** : sur PyInstaller < 5.x, `--windowed`
   redirigeait stdout vers NUL meme avec un parent pipe sur certaines builds
   Windows 7/8. Reglé en 5.x+.
2. **Encoding cp1252** : tres reel, casse silencieusement les chaines
   unicode si on ne reconfigure pas. C'est le piege #1.
3. **Buffering du bootloader** : reel sur PyInstaller < 4.x, considerablement
   ameliore depuis. Le flush manuel reste recommande.

Sur PyInstaller 6.20.0 + Python 3.12 + Windows 11, les 3 problemes sont
maitrisables via les invariants ci-dessus.

## Implications pour la phase 12

### T069 (refactor monorepo 3 packages) — INCHANGE

Le refactor reste valide. `winboost-mcp` peut etre un sous-package qui produit
son propre `.exe` PyInstaller, ou etre embarque dans le `WinBoost.exe` GUI
existant via une commande dediee (`winboost mcp serve --stdio`).

### T070 (FastMCP) — DEUX OPTIONS COMPATIBLES

Option A — `winboost-mcp.exe` separe (preferee) :
- Spec PyInstaller minimal (5-10 Mo, FastMCP + dep stdio uniquement)
- Reference dans `claude_desktop_config.json` : `command: "winboost-mcp.exe"`
- Cold-start ~300 ms (acceptable, MCP server long-lived)

Option B — `WinBoost.exe mcp serve --stdio` (sous-commande) :
- Reutilise le binaire GUI existant (54 Mo)
- Cold-start ~600-800 ms estime (dep customtkinter, pyyaml, etc.)
- Plus simple a deployer (un seul binaire)
- Penalty : le user qui veut juste le MCP doit telecharger 54 Mo

**Recommandation : Option A pour la release v2.2**. La taille des deux
binaires (GUI + MCP) reste sous 70 Mo combines, et la separation rend les
mises a jour MCP independantes du cycle GUI.

### T071 (auth token + install-claude-desktop)

Pas affecte par ce verdict. La commande `install-claude-desktop` doit
generer un block JSON pour `claude_desktop_config.json` qui pointe vers
`winboost-mcp.exe` avec le token en variable d'environnement.

### T072 — DONE

Cette tache est completee. Verdict GO sous conditions, livrables produits
et testes. Status a passer a `done` dans status.yaml.

### T073 (25+ tests d'integration MCP)

Inclure obligatoirement :
- 1 test "le serveur lance via subprocess + .exe survit a 100 req" (regression)
- 1 test "unicode roundtrip via .exe" (regression)
- 1 test "le serveur respecte le flush apres chaque write"
- 1 test "le serveur reconfigure bien stdio en UTF-8 au boot"

## Cleanup

Les artefacts de build (`dist/poc_mcp_server.exe`, `build/poc_mcp_server/`,
`poc_mcp_server.spec`) ont ete generes pendant le POC. Ils sont supprimes via
`python tests/mcp_compat/build_poc.py --cleanup`. Seul `tests/mcp_compat/`
reste dans le repo (le POC est conserve comme regression test reproductible).

## Reproduire ce POC

```bash
cd A:/dev/winboost
python tests/mcp_compat/poc_client.py            # mode Python (sanity check)
python tests/mcp_compat/build_poc.py             # build le .exe
python tests/mcp_compat/poc_client.py --exe      # mode .exe (le test critique)
python tests/mcp_compat/build_poc.py --cleanup   # supprime les artefacts
```

Duree totale : ~30 secondes (build PyInstaller ~10s, tests ~3s).
