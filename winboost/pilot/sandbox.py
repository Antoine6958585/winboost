"""Sandbox — zone d'ecran autorisee + safety limits pour le Pilot.

Le Sandbox encapsule **ce que le Pilot a le droit d'observer et de toucher**
sur l'ecran. Par defaut, il est restreint a la fenetre WinBoost active
(zone "winboost_window"). L'utilisateur peut elargir a une app specifique
ou au plein ecran, mais **toujours via une etape de confirmation explicite**
— jamais en un clic silencieux.

## Mode

- `winboost_window` (default) : seule la fenetre WinBoost est observable
- `application` : une app specifique designee par titre fenetre (HWND)
- `screen_region` : un rectangle libre defini par l'utilisateur
- `full_screen` : tout l'ecran (necessite `allow_full_screen=True` au
  constructeur, qui doit lui-meme avoir ete obtenu via une confirmation
  explicite cote UI — Sandbox ne fait que verifier le flag)

## Safety limits (applique a chaque check)

- coordonnees de clic doivent tomber dans `region`
- nombre de clics consecutifs sans re-confirmation utilisateur :
  default 5 (parametrable, `max_consecutive_actions`)
- compteur reset apres chaque confirmation explicite (`reset_consecutive`)

Une violation leve `SandboxViolationError` avec un message explicite. Le
Pilot doit catch et stopper la session — pas de fallback silencieux.

## Pourquoi c'est important

L'API Anthropic Computer Use peut proposer un clic **n'importe ou** sur
l'ecran. Sans Sandbox, l'agent peut cliquer sur un onglet sensible (banque,
mail), envoyer involontairement, supprimer un fichier... La Sandbox est la
**derniere ligne de defense** apres la confirmation visuelle utilisateur.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal

logger = logging.getLogger(__name__)

__all__ = [
    "Sandbox",
    "SandboxViolationError",
    "Region",
    "SandboxMode",
    "DEFAULT_MAX_CONSECUTIVE",
]

#: Plafond default d'actions consecutives sans re-confirmation utilisateur.
DEFAULT_MAX_CONSECUTIVE: int = 5

SandboxMode = Literal["winboost_window", "application", "screen_region", "full_screen"]


class SandboxViolationError(RuntimeError):
    """Levee quand une action proposee sort des limites de la sandbox.

    Le message decrit precisement la violation (coords hors zone,
    plafond consecutif depasse, mode interdit sans flag).
    """


@dataclass(frozen=True)
class Region:
    """Rectangle ecran (coords absolues, top-left origin).

    Attributes:
        x: position X du coin top-left.
        y: position Y du coin top-left.
        width: largeur en pixels.
        height: hauteur en pixels.
    """

    x: int
    y: int
    width: int
    height: int

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError(
                f"Region invalide : width={self.width}, height={self.height} "
                f"(doivent etre > 0)"
            )

    def contains(self, x: int, y: int) -> bool:
        """Indique si le point (x, y) tombe dans la region.

        On utilise des bornes inclusives au top-left, exclusives au
        bottom-right (convention pixel grid).
        """
        return (
            self.x <= x < self.x + self.width
            and self.y <= y < self.y + self.height
        )

    def as_tuple(self) -> tuple[int, int, int, int]:
        """Retourne (x, y, width, height)."""
        return (self.x, self.y, self.width, self.height)


@dataclass
class Sandbox:
    """Zone d'ecran autorisee + tracker d'actions consecutives.

    Attributes:
        mode: type de zone (cf. docstring module).
        region: rectangle effectif a controler.
        allow_full_screen: garde-fou explicite. Si False, mode='full_screen'
            leve une SandboxViolationError au prochain check.
        max_consecutive_actions: plafond avant re-confirmation forcee.
    """

    mode: SandboxMode = "winboost_window"
    region: Region = field(default_factory=lambda: Region(0, 0, 1, 1))
    allow_full_screen: bool = False
    max_consecutive_actions: int = DEFAULT_MAX_CONSECUTIVE
    _consecutive: int = field(default=0, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.max_consecutive_actions < 1:
            raise ValueError(
                f"max_consecutive_actions doit etre >= 1, recu {self.max_consecutive_actions}"
            )

        # Le mode full_screen est un cas tres sensible : on refuse meme
        # de construire une Sandbox sans le flag explicit. C'est une
        # double-barriere intentionnelle (ceinture + bretelles).
        if self.mode == "full_screen" and not self.allow_full_screen:
            raise SandboxViolationError(
                "Mode 'full_screen' refuse : `allow_full_screen=True` requis "
                "explicitement (la confirmation utilisateur doit etre passee "
                "AVANT la construction de la Sandbox)."
            )

    @property
    def consecutive_actions(self) -> int:
        """Nombre d'actions executees depuis la derniere re-confirmation."""
        return self._consecutive

    def reset_consecutive(self) -> None:
        """Reset du compteur — a appeler apres chaque re-confirmation user."""
        logger.debug("Sandbox: reset compteur consecutif (etait %d)", self._consecutive)
        self._consecutive = 0

    def check_click(self, x: int, y: int) -> None:
        """Valide qu'un clic est dans la zone autorisee.

        Raises:
            SandboxViolationError: si (x, y) hors region.
        """
        if not self.region.contains(x, y):
            raise SandboxViolationError(
                f"Clic refuse : ({x}, {y}) hors zone autorisee "
                f"(mode={self.mode}, region={self.region.as_tuple()}). "
                "L'utilisateur doit elargir la sandbox via Settings."
            )

    def check_can_act(self) -> None:
        """Verifie qu'on peut encore agir sans re-confirmation.

        Doit etre appelee AVANT chaque action. Si le plafond est atteint,
        leve SandboxViolationError — le Pilot doit alors demander une
        re-confirmation utilisateur, puis appeler `reset_consecutive`.
        """
        if self._consecutive >= self.max_consecutive_actions:
            raise SandboxViolationError(
                f"Plafond d'actions consecutives atteint "
                f"({self._consecutive}/{self.max_consecutive_actions}). "
                "Re-confirmation utilisateur requise avant de continuer."
            )

    def record_action(self) -> None:
        """Incremente le compteur apres une action reussie.

        A appeler APRES `check_can_act` + execution de l'action. C'est
        une operation explicite (pas auto-incremente dans check_click)
        pour permettre des dry-runs / previews qui ne consomment pas le
        budget consecutif.
        """
        self._consecutive += 1
        logger.debug(
            "Sandbox: action enregistree (%d/%d consecutives)",
            self._consecutive, self.max_consecutive_actions,
        )

    def describe(self) -> str:
        """Description humaine pour le UI / les logs."""
        return (
            f"Sandbox(mode={self.mode}, "
            f"region={self.region.as_tuple()}, "
            f"max_consecutive={self.max_consecutive_actions}, "
            f"current_consecutive={self._consecutive})"
        )
