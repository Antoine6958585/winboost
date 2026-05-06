"""Confirmation UI — preview screenshot annote + confirm/cancel.

Affiche un screenshot capture par le Pilot avec un rectangle annote sur
la zone que Claude propose de toucher (clic, type, scroll, key...). L'user
doit explicitement valider chaque action avant execution.

## Architecture

Cette classe est volontairement *headless-friendly* : elle expose un
`Confirmer` callable injectable. La GUI Tk est une simple implementation
de reference (`TkConfirmer`), mais le Pilot peut etre teste avec un
confirmer mocke en tests unitaires (cf. `tests/test_pilot/test_pilot.py`).

Pillow est utilise UNIQUEMENT pour annoter les screenshots (rectangle
rouge + label). Pas de depandance Tk dans ce module — Tk est dans le
sous-module GUI.

## Flow utilisateur

1. Pilot capture screenshot S
2. Anthropic Computer Use propose action A (ex: clic en (456, 234))
3. Pilot appelle `annotate(S, A)` -> screenshot annote PNG
4. Pilot appelle `confirmer.ask(action=A, screenshot=annotated)` :
   - True  -> action executee
   - False -> action skippee
   - 'allow_n' -> action executee + N suivantes sans re-confirm (max 5)
5. Loop jusqu'a fin de mission ou abort

## Pourquoi pas Tk ici

Tk c'est lourd, ca ouvre une fenetre, et ca bloque les tests CI headless.
Cette couche reste pure-Pillow ; la GUI viendra dans `winboost/gui/pilot.py`
en v2.3 finale (hors scope ce livrable, c'est T081).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Literal, Protocol

logger = logging.getLogger(__name__)

__all__ = [
    "ConfirmationManager",
    "ProposedAction",
    "ConfirmationDecision",
    "ConfirmCallback",
    "build_default_confirmer",
]

#: Decision utilisateur :
#: - "confirm" : executer cette action et re-demander pour la suivante
#: - "cancel"  : ne pas executer cette action et arreter le loop
#: - "skip"    : ne pas executer mais continuer le loop
#: - "allow_batch" : executer cette action + jusqu'a N suivantes sans re-confirm
ConfirmationDecision = Literal["confirm", "cancel", "skip", "allow_batch"]


@dataclass(frozen=True)
class ProposedAction:
    """Une action proposee par Claude Computer Use.

    Le format suit grossierement le tool `computer` Anthropic :
    https://docs.anthropic.com/claude/docs/computer-use

    Attributes:
        kind: type d'action ('click', 'type', 'key', 'scroll', 'screenshot',
            'move', 'wait', 'cursor_position', etc.)
        x: coord X (pour click/move/scroll), None sinon.
        y: coord Y (pour click/move/scroll), None sinon.
        text: texte (pour type), None sinon.
        key: nom de touche (pour key), None sinon.
        scroll_direction: 'up'/'down'/'left'/'right' (pour scroll), None sinon.
        scroll_amount: nombre de "ticks" de scroll, None sinon.
        rationale: justification donnee par Claude (string libre).
    """

    kind: str
    x: int | None = None
    y: int | None = None
    text: str | None = None
    key: str | None = None
    scroll_direction: str | None = None
    scroll_amount: int | None = None
    rationale: str = ""

    def short_label(self) -> str:
        """Label court pour affichage (ex: 'click(456, 234)')."""
        if self.kind == "click" and self.x is not None and self.y is not None:
            return f"click({self.x}, {self.y})"
        if self.kind == "type" and self.text:
            preview = self.text if len(self.text) <= 40 else self.text[:37] + "..."
            return f"type({preview!r})"
        if self.kind == "key" and self.key:
            return f"key({self.key})"
        if self.kind == "scroll":
            return f"scroll({self.scroll_direction}, n={self.scroll_amount})"
        return self.kind


class ConfirmCallback(Protocol):
    """Callback de confirmation utilisateur.

    Signature :
        (action, screenshot_bytes_or_path) -> ConfirmationDecision
    """

    def __call__(
        self,
        action: ProposedAction,
        screenshot: bytes | Path,
    ) -> ConfirmationDecision: ...


class ConfirmationManager:
    """Annotateur de screenshot + dispatcher vers un confirmer.

    Args:
        confirmer: callable conforme `ConfirmCallback`. Si None, utilise
            `build_default_confirmer()` qui leve NotImplementedError —
            l'integration GUI Tk est hors scope du module pilot, c'est
            la responsabilite de la couche `winboost/gui/pilot.py`.
        annotate_color: couleur RGBA du rectangle d'annotation.
        annotate_width: epaisseur du trait du rectangle (px).
    """

    def __init__(
        self,
        confirmer: ConfirmCallback | None = None,
        annotate_color: tuple[int, int, int, int] = (255, 0, 0, 220),
        annotate_width: int = 4,
    ) -> None:
        self._confirmer: ConfirmCallback = confirmer or build_default_confirmer()
        self._annotate_color = annotate_color
        self._annotate_width = annotate_width

    def annotate(
        self,
        screenshot: bytes,
        action: ProposedAction,
        target_size: int = 60,
    ) -> bytes:
        """Annote un screenshot PNG avec un rectangle sur la zone d'action.

        Args:
            screenshot: bytes PNG/JPEG du screenshot brut.
            action: action proposee par Claude (utilise x/y si presentes).
            target_size: cote du rectangle dessine autour de (x, y), px.

        Returns:
            bytes PNG du screenshot annote. Si action n'a pas de coords,
            retourne le screenshot original tel quel.
        """
        if action.x is None or action.y is None:
            return screenshot

        try:
            from PIL import Image, ImageDraw  # type: ignore[import-not-found]
        except ImportError as e:
            logger.warning("Pillow indisponible, annotation skippee : %s", e)
            return screenshot

        try:
            img = Image.open(BytesIO(screenshot)).convert("RGBA")
        except Exception as e:  # noqa: BLE001 - any decode error
            logger.warning("Image illisible, annotation skippee : %s", e)
            return screenshot

        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        half = target_size // 2
        bbox = (
            max(0, action.x - half),
            max(0, action.y - half),
            min(img.size[0] - 1, action.x + half),
            min(img.size[1] - 1, action.y + half),
        )
        draw.rectangle(bbox, outline=self._annotate_color, width=self._annotate_width)

        # Label texte juste au-dessus du rectangle (best-effort, sans
        # font asset embarque -- Pillow charge la default font tout seul).
        label = action.short_label()
        text_xy = (bbox[0], max(0, bbox[1] - 18))
        with _SuppressTextErrors():
            draw.text(text_xy, label, fill=self._annotate_color)

        merged = Image.alpha_composite(img, overlay)
        out = BytesIO()
        merged.convert("RGB").save(out, format="PNG")
        return out.getvalue()

    def ask(self, action: ProposedAction, screenshot: bytes) -> ConfirmationDecision:
        """Dispatche au confirmer apres annotation."""
        annotated = self.annotate(screenshot, action)
        decision = self._confirmer(action, annotated)
        if decision not in {"confirm", "cancel", "skip", "allow_batch"}:
            logger.warning(
                "ConfirmCallback a renvoye %r (invalide), interprete comme 'cancel'.",
                decision,
            )
            return "cancel"
        return decision


# --- Default confirmer ---------------------------------------------------


class _NotImplementedConfirmer:
    """Confirmer par defaut : leve NotImplementedError.

    Force le caller a fournir une implementation explicite (GUI Tk en
    production, mock en tests). Pas de "yes-by-default" possible — c'est
    une garantie de securite : le Pilot ne peut jamais executer sans
    qu'un confirmer reel ait ete branche.
    """

    def __call__(
        self,
        action: ProposedAction,
        screenshot: bytes | Path,  # noqa: ARG002
    ) -> ConfirmationDecision:
        raise NotImplementedError(
            "Aucun confirmer fourni a ConfirmationManager. Le Pilot ne peut pas "
            "executer sans confirmation utilisateur explicite. Implemente un "
            "ConfirmCallback (cf. winboost/gui/pilot.py en v2.3 ou un mock en tests)."
        )


def build_default_confirmer() -> ConfirmCallback:
    """Retourne le confirmer par defaut (leve NotImplementedError).

    C'est un *cul-de-sac* intentionnel : on veut que oublier de cabler
    un confirmer fasse exploser le code, pas qu'il yes-aliase tout.
    """
    return _NotImplementedConfirmer()


# --- Internals -----------------------------------------------------------


class _SuppressTextErrors:
    """Context manager : avale les erreurs de draw.text (font absente etc.)."""

    def __enter__(self) -> _SuppressTextErrors:
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:  # type: ignore[no-untyped-def]
        if exc_type is not None:
            logger.debug("Annotation texte skippee : %r", exc)
        return True


# --- Helper for tests ----------------------------------------------------


def make_yes_confirmer() -> ConfirmCallback:
    """Helper pour les tests : confirmer qui dit toujours 'confirm'.

    Ne JAMAIS utiliser en production -- c'est seulement pour les tests
    qui verifient le flow d'execution sans simulation utilisateur.
    """
    def _confirmer(
        action: ProposedAction,  # noqa: ARG001
        screenshot: bytes | Path,  # noqa: ARG001
    ) -> ConfirmationDecision:
        return "confirm"
    return _confirmer


def make_scripted_confirmer(
    decisions: list[ConfirmationDecision],
) -> ConfirmCallback:
    """Helper pour les tests : retourne les decisions dans l'ordre.

    Apres epuisement, retourne 'cancel' (force la fin du loop). Permet de
    scripter des scenarios complexes : ['confirm', 'confirm', 'cancel'].
    """
    iterator = iter(decisions)

    def _confirmer(
        action: ProposedAction,  # noqa: ARG001
        screenshot: bytes | Path,  # noqa: ARG001
    ) -> ConfirmationDecision:
        try:
            return next(iterator)
        except StopIteration:
            return "cancel"
    return _confirmer


# Type alias alternatif pour code qui prefere fonction nue
ConfirmFn = Callable[[ProposedAction, "bytes | Path"], ConfirmationDecision]
