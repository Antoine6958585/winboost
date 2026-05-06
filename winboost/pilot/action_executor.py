"""Action Executor — execution concrete des actions Pilot via pyautogui.

Fournit l'implementation reelle du `ActionExecutor` Protocol declare dans
`anthropic_pilot.py`. Mappe une `ProposedAction` (dataclass abstraite) vers
les appels pyautogui correspondants :

| ProposedAction.kind | pyautogui appel                           |
|---------------------|-------------------------------------------|
| click               | pyautogui.click(x, y)                     |
| double_click        | pyautogui.doubleClick(x, y)               |
| right_click         | pyautogui.rightClick(x, y)                |
| type                | pyautogui.write(text, interval=...)       |
| key                 | pyautogui.press(key) ou pyautogui.hotkey  |
| scroll              | pyautogui.scroll(amount * direction_sign) |
| move                | pyautogui.moveTo(x, y, duration=...)      |
| wait                | time.sleep(scroll_amount or 1.0)          |
| screenshot          | noop (gere par screenshot_provider)       |
| cursor_position     | noop (read-only, lu par Anthropic via SS) |

## Garde-fous

1. **Sandbox-bound** : si `action.x/y` est present et hors `sandbox.region`,
   on leve `PilotError(out_of_bounds)` AVANT tout appel pyautogui.
2. **Failsafe pyautogui** : on garde `pyautogui.FAILSAFE = True` (default).
   L'utilisateur peut interrompre en bougeant la souris en haut-gauche
   (corner trigger). Si declenche -> `PilotError(failsafe_triggered)` avec
   message clair.
3. **Kind inconnu** -> `PilotError(unsupported_action)`.
4. **Rationale logging** : avant chaque action, on log
   `action.rationale` (audit + debug).

## Important

L'executor **ne consomme PAS** le compteur Sandbox.consecutive_actions.
C'est l'AnthropicPilot qui appelle `sandbox.record_action()` apres une
execution reussie. Cela permet de garder l'executor "pur" (un appel = une
action), et laisse au Pilot la responsabilite du sequencement.

## Imports lazy

`pyautogui` n'est charge qu'au premier appel a `make_action_executor()`.
Permet a un utilisateur sans extra `[pilot]` de `from winboost.pilot import ...`
sans faire crasher l'import.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from winboost.pilot.anthropic_pilot import ActionExecutor, PilotError
from winboost.pilot.confirmation_ui import ProposedAction
from winboost.pilot.sandbox import Sandbox

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

__all__ = [
    "make_action_executor",
    "DEFAULT_TYPE_INTERVAL",
    "DEFAULT_MOVE_DURATION",
    "SUPPORTED_KINDS",
]

#: Intervalle entre frappes clavier pour `type` (s). 0.02 = 50 cps environ.
DEFAULT_TYPE_INTERVAL: float = 0.02

#: Duree d'animation du curseur pour `move` (s). Trop court = instable.
DEFAULT_MOVE_DURATION: float = 0.1

#: Default delay si `wait` n'a pas de scroll_amount.
DEFAULT_WAIT_SECONDS: float = 1.0

#: Kinds supportes (verites d'or pour erreur "unsupported_action").
SUPPORTED_KINDS: frozenset[str] = frozenset(
    {
        "click",
        "double_click",
        "right_click",
        "type",
        "key",
        "scroll",
        "move",
        "wait",
        "screenshot",
        "cursor_position",
    }
)

#: Kinds qui sont des noops (read-only ou geres ailleurs). Pas d'appel pyautogui.
NOOP_KINDS: frozenset[str] = frozenset({"screenshot", "cursor_position"})

#: Kinds qui exigent x ET y dans `sandbox.region`.
COORD_REQUIRED_KINDS: frozenset[str] = frozenset(
    {"click", "double_click", "right_click", "move", "scroll"}
)


def make_action_executor(
    sandbox: Sandbox,
    *,
    type_interval: float = DEFAULT_TYPE_INTERVAL,
    move_duration: float = DEFAULT_MOVE_DURATION,
) -> ActionExecutor:
    """Construit un `ActionExecutor` pyautogui pret a l'emploi.

    Args:
        sandbox: Sandbox utilisee pour valider chaque coord avant clic.
            L'executor ne touche PAS au compteur consecutif (c'est le role
            du AnthropicPilot).
        type_interval: delai entre 2 frappes clavier (s). 0.02 par default.
        move_duration: duree d'animation pour les `move`/`click` avec mouse
            travel (s). 0.1 par default.

    Raises:
        ImportError: si pyautogui n'est pas installe.

    Returns:
        Callable conforme `ActionExecutor` Protocol.
    """
    try:
        import pyautogui  # noqa: F401  # pragma: no cover - import test
    except ImportError as exc:
        raise ImportError(
            "pyautogui requis pour l'action_executor. "
            "Installe l'extra : `pip install winboost[pilot]`. "
            "Sans cela, le Pilot Mode peut capturer l'ecran mais pas agir."
        ) from exc

    def _execute(action: ProposedAction) -> None:
        _execute_action(
            action,
            sandbox=sandbox,
            type_interval=type_interval,
            move_duration=move_duration,
        )

    return _execute


def _execute_action(
    action: ProposedAction,
    *,
    sandbox: Sandbox,
    type_interval: float,
    move_duration: float,
) -> None:
    """Dispatch vers l'appel pyautogui correspondant au `kind` de l'action.

    Raises:
        PilotError: out_of_bounds, unsupported_action, failsafe_triggered.
    """
    # Audit / debug : on log avant tout, meme si l'action echoue ensuite.
    if action.rationale:
        logger.info(
            "Pilot execute %s: %s",
            action.short_label(),
            action.rationale,
        )
    else:
        logger.info("Pilot execute %s", action.short_label())

    kind = action.kind

    # 1. Validation kind (avant tout import lourd / appel pyautogui).
    if kind not in SUPPORTED_KINDS:
        raise PilotError(
            f"unsupported_action: kind={kind!r} non supporte. "
            f"Kinds valides : {sorted(SUPPORTED_KINDS)}"
        )

    # 2. Noops : pas d'effet de bord, pas d'erreur.
    if kind in NOOP_KINDS:
        logger.debug("Pilot noop kind=%s (gere par screenshot_provider)", kind)
        return

    # 3. Wait : pas de coord, pas pyautogui.
    if kind == "wait":
        delay = float(action.scroll_amount) if action.scroll_amount else DEFAULT_WAIT_SECONDS
        logger.debug("Pilot wait %.2fs", delay)
        time.sleep(delay)
        return

    # 4. Validation coords pour les actions positionnelles.
    if kind in COORD_REQUIRED_KINDS:
        if action.x is None or action.y is None:
            raise PilotError(
                f"out_of_bounds: action {kind!r} sans coordonnees (x={action.x}, "
                f"y={action.y}). Requiert x et y non-None."
            )
        if not sandbox.region.contains(action.x, action.y):
            raise PilotError(
                f"out_of_bounds: clic refuse ({action.x}, {action.y}) hors zone "
                f"sandbox (mode={sandbox.mode}, region={sandbox.region.as_tuple()}). "
                "Action NON executee."
            )

    # 5. Lazy-import pyautogui ici (les tests patchent ce point).
    import pyautogui

    try:
        if kind == "click":
            pyautogui.click(action.x, action.y)

        elif kind == "double_click":
            pyautogui.doubleClick(action.x, action.y)

        elif kind == "right_click":
            pyautogui.rightClick(action.x, action.y)

        elif kind == "type":
            text = action.text or ""
            if not text:
                logger.debug("Pilot type vide -> noop")
                return
            pyautogui.write(text, interval=type_interval)

        elif kind == "key":
            key = action.key or ""
            if not key:
                raise PilotError(
                    "unsupported_action: kind='key' sans `key` defini."
                )
            # Hotkey si combo "ctrl+c" / "alt+f4" / "win+d".
            if "+" in key:
                parts = [p.strip().lower() for p in key.split("+") if p.strip()]
                if not parts:
                    raise PilotError(
                        f"unsupported_action: hotkey vide apres parsing de {key!r}."
                    )
                pyautogui.hotkey(*parts)
            else:
                pyautogui.press(key)

        elif kind == "move":
            pyautogui.moveTo(action.x, action.y, duration=move_duration)

        elif kind == "scroll":
            amount = action.scroll_amount or 1
            direction = (action.scroll_direction or "down").lower()
            sign = _scroll_sign(direction)
            # pyautogui.scroll : positive = up, negative = down.
            # Pour symetrie horizontale, pyautogui.hscroll n'existe pas
            # toujours selon les versions ; on log et on ignore left/right.
            if direction in {"left", "right"}:
                logger.warning(
                    "Pilot scroll horizontal (%s) ignore : pyautogui ne le "
                    "supporte pas de maniere portable. Action noop.",
                    direction,
                )
                return
            pyautogui.scroll(amount * sign)

    except PilotError:
        # Deja relabel correctement -> on remonte tel quel.
        raise
    except Exception as exc:  # noqa: BLE001
        # FailSafeException est defini sur pyautogui (n'existe pas avant import) ;
        # on identifie via le nom de classe pour ne pas creer de couplage dur.
        if type(exc).__name__ == "FailSafeException":
            raise PilotError(
                "failsafe_triggered: pyautogui Failsafe declenche. "
                "L'utilisateur a bouge la souris en haut-gauche pour interrompre "
                "le Pilot. Aucune action n'a ete executee. C'est le comportement "
                "attendu d'une commande d'urgence — le Pilot doit s'arreter."
            ) from exc
        # Autres erreurs pyautogui (driver, OS) -> on relabel en PilotError sans
        # masquer le type d'origine.
        raise PilotError(
            f"pyautogui_error: {type(exc).__name__}: {exc} "
            f"(action={action.short_label()}, kind={kind})"
        ) from exc


def _scroll_sign(direction: str) -> int:
    """Convertit 'up'/'down' en signe pyautogui (up=+, down=-).

    Retourne +1 par default si direction inconnue (defensif, pas critique).
    """
    direction = direction.lower()
    if direction == "up":
        return 1
    if direction == "down":
        return -1
    return 1
