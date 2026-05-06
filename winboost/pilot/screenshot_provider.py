"""Screenshot Provider — capture concrete via Pillow ImageGrab (Windows).

Fournit l'implementation reelle du `ScreenshotProvider` Protocol declare
dans `anthropic_pilot.py`. Utilise `PIL.ImageGrab` pour capturer la zone
d'ecran autorisee par la `Sandbox` :

- `winboost_window` (default) -> sandbox.region
- `application`              -> sandbox.region (resolue cote GUI via win32gui)
- `screen_region`            -> sandbox.region
- `full_screen`              -> tout l'ecran si sandbox.allow_full_screen=True

Imports lourds (Pillow) restent **lazy** : le module ne charge `PIL` que
lors de l'appel a `make_screenshot_provider()`. Permet a un utilisateur
qui n'a pas installe l'extra `[pilot]` de `from winboost.pilot import ...`
sans erreur — l'erreur ne survient que s'il **utilise** le pilot.

## Garde-fous

- `sandbox.mode == 'full_screen'` + `allow_full_screen=False` -> PilotError
  (la Sandbox elle-meme refuse deja, on revalidate ici par defense-en-profondeur).
- Capture > 500ms -> log warning (pas d'erreur, c'est juste un signal).
- Capture vide (0 bytes) ou non-PNG -> PilotError.

## Multi-ecrans + DPI

Sur Windows HiDPI, `ImageGrab.grab()` retourne par defaut les pixels logiques
de l'ecran principal. On passe systematiquement `all_screens=True` pour
gerer les configs multi-ecrans (ecran secondaire avec coords negatives ou
au-dela de la largeur primaire).

Les coords du sandbox.region sont **absolues** (top-left = (0, 0) de
l'ecran primaire). Si l'utilisateur a un ecran secondaire a gauche, les
coords peuvent etre negatives — `all_screens=True` les supporte.
"""

from __future__ import annotations

import logging
import time
from io import BytesIO
from typing import TYPE_CHECKING

from winboost.pilot.anthropic_pilot import PilotError, ScreenshotProvider
from winboost.pilot.sandbox import Sandbox

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

__all__ = [
    "make_screenshot_provider",
    "PNG_MAGIC",
    "SLOW_CAPTURE_WARN_MS",
]

#: Magic bytes d'un fichier PNG valide (8 octets de header).
PNG_MAGIC: bytes = b"\x89PNG\r\n\x1a\n"

#: Seuil au-dela duquel on log un warning de performance (ms).
SLOW_CAPTURE_WARN_MS: int = 500


def make_screenshot_provider() -> ScreenshotProvider:
    """Construit un `ScreenshotProvider` Pillow pret a l'emploi.

    Le provider retourne les bytes PNG de la zone definie par la Sandbox.

    Raises:
        ImportError: si Pillow n'est pas installe (extra `[pilot]` manquant).

    Returns:
        Callable conforme `ScreenshotProvider` Protocol.
    """
    try:
        from PIL import ImageGrab  # noqa: F401  # pragma: no cover - import test
    except ImportError as exc:
        raise ImportError(
            "Pillow requis pour le screenshot_provider. "
            "Installe l'extra : `pip install winboost[pilot]`. "
            "Sans cela, le Pilot Mode ne peut pas capturer l'ecran."
        ) from exc

    return _capture_with_pillow


def _capture_with_pillow(sandbox: Sandbox) -> bytes:
    """Implementation concrete : capture la zone autorisee via PIL.ImageGrab.

    Args:
        sandbox: Sandbox decrivant ce qui peut etre capture (mode + region).

    Returns:
        bytes PNG (header 0x89 0x50 0x4E 0x47 ...).

    Raises:
        PilotError: si la capture echoue ou produit des bytes invalides.
    """
    # Defense en profondeur : Sandbox refuse deja la construction sans flag,
    # mais on revalidate ici au cas ou un caller bricole l'attribut directement.
    if sandbox.mode == "full_screen" and not sandbox.allow_full_screen:
        raise PilotError(
            "Capture full_screen refusee : sandbox.allow_full_screen=False. "
            "L'utilisateur doit confirmer explicitement le mode full_screen "
            "via Settings avant qu'une capture totale soit autorisee."
        )

    # Lazy-import a chaque appel : permet de patcher PIL.ImageGrab dans les tests
    # via `mocker.patch("winboost.pilot.screenshot_provider.ImageGrab")` apres
    # `make_screenshot_provider()` retourne le callable.
    from PIL import ImageGrab

    bbox = _resolve_bbox(sandbox)
    start = time.perf_counter()

    try:
        # all_screens=True gere les configs multi-ecrans + coords negatives.
        # Sur certaines versions PIL anciennes (< 9.2), all_screens n'existe
        # pas — on tente avec, on retombe sans en cas de TypeError.
        try:
            image = ImageGrab.grab(bbox=bbox, all_screens=True)
        except TypeError:
            # Pillow < 9.2 : signature sans all_screens.
            image = ImageGrab.grab(bbox=bbox)
    except Exception as exc:  # noqa: BLE001 - on relabel en PilotError
        raise PilotError(
            f"Echec de la capture d'ecran (mode={sandbox.mode}, bbox={bbox}) : "
            f"{type(exc).__name__}: {exc}"
        ) from exc

    elapsed_ms = (time.perf_counter() - start) * 1000.0
    if elapsed_ms > SLOW_CAPTURE_WARN_MS:
        logger.warning(
            "Capture d'ecran lente : %.0fms (seuil=%dms, mode=%s, bbox=%s). "
            "Une lenteur persistante peut etre due a un GPU integre lent ou "
            "un ecran HDR.",
            elapsed_ms,
            SLOW_CAPTURE_WARN_MS,
            sandbox.mode,
            bbox,
        )
    else:
        logger.debug(
            "Capture d'ecran : %.0fms (mode=%s, bbox=%s)",
            elapsed_ms,
            sandbox.mode,
            bbox,
        )

    # Convertit l'image en PNG bytes (compression standard, pas de perte).
    buffer = BytesIO()
    try:
        image.save(buffer, format="PNG")
    except Exception as exc:  # noqa: BLE001
        raise PilotError(
            f"Echec d'encodage PNG du screenshot : {type(exc).__name__}: {exc}"
        ) from exc

    data = buffer.getvalue()

    # Validation des bytes produits : header PNG + non-vide.
    if not data:
        raise PilotError(
            "Capture d'ecran a produit 0 bytes — buffer vide. "
            "Probable bug Pillow, GPU driver instable, ou session RDP/console "
            "sans framebuffer accessible."
        )

    if not data.startswith(PNG_MAGIC):
        raise PilotError(
            f"Capture d'ecran invalide : header PNG attendu {PNG_MAGIC.hex()}, "
            f"recu {data[:8].hex()}. Probable corruption."
        )

    return data


def _resolve_bbox(sandbox: Sandbox) -> tuple[int, int, int, int] | None:
    """Convertit la Sandbox en bbox `(left, top, right, bottom)` pour ImageGrab.

    - `full_screen` -> None (capture tout l'ecran via PIL).
    - autres modes  -> rectangle absolu derive de `sandbox.region`.

    Args:
        sandbox: Sandbox source.

    Returns:
        Tuple `(left, top, right, bottom)` ou None pour "full_screen".
    """
    if sandbox.mode == "full_screen":
        # ImageGrab.grab(bbox=None) -> capture l'ecran complet (ou tous les
        # ecrans avec all_screens=True).
        return None

    region = sandbox.region
    left = region.x
    top = region.y
    right = region.x + region.width
    bottom = region.y + region.height
    return (left, top, right, bottom)
