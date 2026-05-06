r"""AnthropicPilot — orchestrateur Computer Use loop.

Implemente le **loop de pilotage visuel** :

    user prompt
       |
       v
    capture screenshot --> Anthropic API (computer_use tool)
       |                          |
       |                          v
       |                  proposed action(s)
       |                          |
       |                          v
       |              ConfirmationManager.ask(...)
       |                          |
       |          confirm? -- yes /  no \-- cancel/skip
       |                |                |
       |                v                v
       |        execute action       skip / abort
       |                |
       |                v
       |          new screenshot --+
       +-----------------------------+
       (loop until done / abort)

## Garde-fous (non-negociables)

1. **BYOK** : `api_key` obligatoire au constructeur (pas de fallback gratuit).
2. **Profil Lab** : `assert_profile_lab(config)` valide le profil utilisateur.
3. **RGPD opt-in** : `assert_rgpd_accepted(config)` valide les opt-ins
   granulaires (`screenshots`, `ocr_text`, `system_info`).
4. **Plafond budgetaire** : `BudgetManager.assert_can_spend()` avant chaque
   appel API ; `record_spend()` apres.
5. **Sandbox** : `Sandbox.check_click()` + `check_can_act()` a chaque action.
6. **Confirmation** : `ConfirmationManager.ask()` retourne 'confirm' avant
   toute execution. Pas de mode "trust me".
7. **Audit trail** : `HistoryManager.log_action()` apres chaque action,
   succes ou echec.
8. **Cancel global** : `pilot.stop()` ou ConfirmDecision='cancel' arrete
   immediatement le loop et libere le controle.

## Compatibilite SDK Anthropic Computer Use

Au moment d'ecrire ce module (2026-05), le SDK officiel `anthropic` Python
expose Computer Use via le **tool_use** standard :

    client.beta.messages.create(
        model="claude-opus-4-7",  # ou claude-sonnet-4-6
        max_tokens=4096,
        tools=[{"type": "computer_20250124", "name": "computer", ...}],
        messages=[...]
    )

Le SDK NE FAIT PAS le clic lui-meme : il propose des `tool_use` blocks
qu'on doit interpreter et executer cote client. Si l'API Anthropic evolue
vers un SDK qui execute les actions, ce module devra etre adapte.

Limitation actuelle : ce module **ne tente pas** d'executer les clics
(pyautogui/keyboard) directement. Le loop est complet jusqu'a la
proposition + confirmation, et l'execution effective passe par un callback
`executor` injecte au constructeur. La GUI v2.3 fournira un executor
pyautogui ; les tests fournissent un executor mock. Cela laisse le
controle total au caller et evite d'embarquer pyautogui en dependance
core (il reste optionnel dans `[pilot]`).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from winboost.core.config import DEFAULT_CONFIG_DIR, Config
from winboost.core.history import HistoryManager
from winboost.pilot.budget import BudgetExceededError, BudgetManager
from winboost.pilot.confirmation_ui import (
    ConfirmationDecision,
    ConfirmationManager,
    ProposedAction,
)
from winboost.pilot.sandbox import Sandbox, SandboxViolationError

logger = logging.getLogger(__name__)

__all__ = [
    "AnthropicPilot",
    "PilotAction",
    "PilotResult",
    "PilotError",
    "BYOKMissingError",
    "ProfileNotLabError",
    "RGPDNotAcceptedError",
    "ScreenshotProvider",
    "ActionExecutor",
    "AnthropicClientFactory",
    "DEFAULT_MODEL",
    "DEFAULT_MAX_ITERATIONS",
    "RGPD_OPT_IN_KEYS",
    "PILOT_LAB_PROFILE_NAME",
    "PILOT_SCREENSHOT_DIR",
    "assert_profile_lab",
    "assert_rgpd_accepted",
]

#: Modele Anthropic par defaut. Peut etre override dans le constructeur.
DEFAULT_MODEL: str = "claude-opus-4-7"

#: Plafond hard d'iterations dans le loop, meme avec l'utilisateur qui
#: confirme tout. Ceinture supplementaire au plafond budgetaire.
DEFAULT_MAX_ITERATIONS: int = 30

#: Cles d'opt-in RGPD obligatoires dans `config["pilot"]["rgpd"]`.
RGPD_OPT_IN_KEYS: tuple[str, ...] = ("screenshots", "ocr_text", "system_info")

#: Nom canonique du profil Lab requis pour activer le Pilot.
PILOT_LAB_PROFILE_NAME: str = "lab"

#: Dossier ou les screenshots sont persistes (audit trail local).
PILOT_SCREENSHOT_DIR: Path = DEFAULT_CONFIG_DIR / "pilot_screenshots"


# --- Exceptions ---------------------------------------------------------


class PilotError(RuntimeError):
    """Classe parente de toutes les erreurs Pilot specifiques."""


class BYOKMissingError(PilotError):
    """Levee si aucune cle Anthropic n'est fournie."""


class ProfileNotLabError(PilotError):
    """Levee si le profil utilisateur n'est pas 'lab'."""


class RGPDNotAcceptedError(PilotError):
    """Levee si l'opt-in RGPD granulaire est incomplet."""


# --- Protocols (DI) ------------------------------------------------------


class ScreenshotProvider(Protocol):
    """Capture un screenshot de la zone autorisee.

    Renvoie les bytes PNG. Doit lever en cas d'echec (pas de None).
    """

    def __call__(self, sandbox: Sandbox) -> bytes: ...


class ActionExecutor(Protocol):
    """Execute concretement une action proposee (clic, type, key...).

    Doit lever PilotError en cas d'echec irrecuperable. Le pilot continuera
    le loop sinon (Claude prend connaissance de l'echec et propose autre chose).
    """

    def __call__(self, action: ProposedAction) -> None: ...


class AnthropicClientFactory(Protocol):
    """Factory injectable pour creer le client Anthropic.

    Permet de mocker l'API en tests sans toucher au constructeur principal.
    Default : `lambda api_key: anthropic.Anthropic(api_key=api_key)`.
    """

    def __call__(self, api_key: str) -> Any: ...


# --- Dataclasses ---------------------------------------------------------


@dataclass(frozen=True)
class PilotAction:
    """Action effectivement proposee, confirmee, et executee/skippee.

    Sert de log structure unifie : un PilotResult contient une liste de
    PilotAction (audit trail complet de la session).
    """

    iteration: int
    timestamp: str
    proposed: ProposedAction
    decision: ConfirmationDecision
    executed: bool
    cost_eur: float
    tokens_in: int
    tokens_out: int
    error: str = ""
    screenshot_before: str = ""
    screenshot_after: str = ""


@dataclass
class PilotResult:
    """Resultat d'une execution complete du loop.

    Attributes:
        prompt: prompt utilisateur initial.
        actions: chronologie des PilotAction.
        total_cost_eur: cumul des couts API sur la session.
        total_tokens_in: somme des input tokens.
        total_tokens_out: somme des output tokens.
        completed: True si le loop s'est termine "naturellement"
            (Claude a indique fin de mission), False si abort.
        abort_reason: raison de l'abort si applicable.
        iterations: nombre de tours de loop effectues.
    """

    prompt: str
    actions: list[PilotAction] = field(default_factory=list)
    total_cost_eur: float = 0.0
    total_tokens_in: int = 0
    total_tokens_out: int = 0
    completed: bool = False
    abort_reason: str = ""
    iterations: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialisation JSON-friendly pour audit / debug."""
        return {
            "prompt": self.prompt,
            "iterations": self.iterations,
            "completed": self.completed,
            "abort_reason": self.abort_reason,
            "total_cost_eur": round(self.total_cost_eur, 6),
            "total_tokens_in": self.total_tokens_in,
            "total_tokens_out": self.total_tokens_out,
            "actions": [
                {
                    "iteration": a.iteration,
                    "timestamp": a.timestamp,
                    "proposed_kind": a.proposed.kind,
                    "proposed_x": a.proposed.x,
                    "proposed_y": a.proposed.y,
                    "proposed_text": a.proposed.text,
                    "rationale": a.proposed.rationale,
                    "decision": a.decision,
                    "executed": a.executed,
                    "cost_eur": round(a.cost_eur, 6),
                    "tokens_in": a.tokens_in,
                    "tokens_out": a.tokens_out,
                    "error": a.error,
                    "screenshot_before": a.screenshot_before,
                    "screenshot_after": a.screenshot_after,
                }
                for a in self.actions
            ],
        }


# --- Validation helpers --------------------------------------------------


def assert_profile_lab(config: Config) -> None:
    """Valide que le profil utilisateur est 'lab'.

    Raises:
        ProfileNotLabError: si profile != 'lab'.
    """
    profile = config.get("profile", "safe")
    if profile != PILOT_LAB_PROFILE_NAME:
        raise ProfileNotLabError(
            f"Le Pilot Computer Use requiert le profil 'lab' (actuel: {profile!r}). "
            "Active le profil Lab dans Settings -- c'est experimental, separe du "
            "tier Pro standard."
        )


def assert_rgpd_accepted(config: Config) -> None:
    """Valide que tous les opt-ins RGPD sont a True.

    L'opt-in est granulaire : chaque type de donnee envoyee a Anthropic
    doit etre accepte separement. Si un seul flag manque, on refuse.

    Format attendu dans config :
        config["pilot"] = {
            "rgpd": {
                "screenshots": True,
                "ocr_text": True,
                "system_info": True,
                "accepted_at": "2026-05-06T12:34:56Z",
            }
        }

    Raises:
        RGPDNotAcceptedError: si un flag manque ou est False.
    """
    pilot_cfg = config.get("pilot", {}) or {}
    rgpd = pilot_cfg.get("rgpd", {}) or {}
    missing = [k for k in RGPD_OPT_IN_KEYS if not rgpd.get(k, False)]
    if missing:
        raise RGPDNotAcceptedError(
            f"Opt-in RGPD incomplet pour le Pilot. Manquant: {missing}. "
            "L'utilisation du Pilot envoie des screenshots a l'API Anthropic "
            "(datacenter US, hors UE). Consulte la notice RGPD complete dans "
            "winboost/pilot/README.md et coche TOUS les opt-ins (screenshots, "
            "ocr_text, system_info) avant de continuer."
        )


# --- Pilot ---------------------------------------------------------------


class AnthropicPilot:
    """Orchestrateur Computer Use avec garde-fous WinBoost.

    Args:
        api_key: cle Anthropic (BYOK obligatoire). Si None ou vide, leve
            BYOKMissingError des `run()`.
        config: Config WinBoost (profil, opt-ins RGPD).
        sandbox: zone d'ecran autorisee + safety limits.
        confirmation: gestionnaire de confirmation utilisateur.
        budget: gestionnaire de plafond mensuel.
        history: HistoryManager pour l'audit trail (optionnel mais recommande).
        screenshot_provider: callable qui capture la zone (DI -- testable).
        action_executor: callable qui execute clic/type/key (DI -- testable).
        client_factory: factory pour le client Anthropic (DI -- mockable).
        model: nom du modele (default "claude-opus-4-7").
        max_iterations: plafond d'iterations du loop.
        screenshot_dir: ou stocker les screenshots de l'audit trail.

    Note:
        Le pilot est *strictement injecte*. Tous les composants critiques
        sont fournis au constructeur, ce qui rend la classe entierement
        testable sans toucher a l'API ni a l'ecran.
    """

    def __init__(
        self,
        api_key: str | None,
        *,
        config: Config | None = None,
        sandbox: Sandbox | None = None,
        confirmation: ConfirmationManager | None = None,
        budget: BudgetManager | None = None,
        history: HistoryManager | None = None,
        screenshot_provider: ScreenshotProvider | None = None,
        action_executor: ActionExecutor | None = None,
        client_factory: AnthropicClientFactory | None = None,
        model: str = DEFAULT_MODEL,
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
        screenshot_dir: Path | None = None,
    ) -> None:
        # Garde-fou n°1 : BYOK obligatoire, EVALUE TOT (pas a run() time).
        # On veut que construire un pilot sans cle echoue immediatement.
        if not api_key:
            raise BYOKMissingError(
                "Cle Anthropic absente. Le Pilot Computer Use necessite une "
                "cle API personnelle (BYOK). Configure-la dans Settings ou "
                "via la variable d'environnement ANTHROPIC_API_KEY. "
                "Pas de fallback gratuit -- c'est de l'argent reel et c'est "
                "TON argent."
            )
        self._api_key = api_key
        self._model = model
        self._max_iterations = int(max_iterations)
        if self._max_iterations < 1:
            raise ValueError("max_iterations doit etre >= 1")

        self._config = config or Config()
        self._sandbox = sandbox or Sandbox()
        self._confirmation = confirmation or ConfirmationManager()
        self._budget = budget or BudgetManager()
        self._history = history
        self._screenshot_dir = screenshot_dir or PILOT_SCREENSHOT_DIR

        self._screenshot_provider = screenshot_provider or _default_screenshot_provider
        self._action_executor = action_executor or _default_action_executor
        self._client_factory = client_factory or _default_client_factory

        self._stop_requested = False
        self._allow_batch_remaining = 0  # Reste d'actions sans re-confirm

    # --- Public API ----------------------------------------------------

    def stop(self) -> None:
        """Demande l'arret immediat du loop (cancel global, equivalent Esc).

        Le flag est lu en debut de chaque iteration. La derniere action
        en cours d'execution se termine ; le loop sort proprement avec
        `abort_reason='user_stop'`.
        """
        logger.info("AnthropicPilot.stop() requested")
        self._stop_requested = True

    def run(self, prompt: str) -> PilotResult:
        """Execute le loop pilote pour un prompt utilisateur.

        Verifie tous les garde-fous AVANT de demarrer le loop :
        BYOK, profil Lab, RGPD opt-in, budget initial.

        Returns:
            PilotResult complet (chronologie + couts).

        Raises:
            BYOKMissingError, ProfileNotLabError, RGPDNotAcceptedError,
            BudgetExceededError: si un prerequis n'est pas satisfait.

        Note:
            Si `pilot.stop()` est appele AVANT `run()`, le flag est honore
            (le loop sort des la 1ere iteration avec `abort_reason='user_stop'`).
            Le reset etat ne touche que `_allow_batch_remaining`.
        """
        # Reset etat batch (mais on respecte un stop() pre-run !)
        self._allow_batch_remaining = 0

        # Garde-fous (peuvent lever)
        # BYOK est deja valide au constructeur, on re-verifie par defense.
        if not self._api_key:
            raise BYOKMissingError("api_key vide au moment de run().")
        assert_profile_lab(self._config)
        assert_rgpd_accepted(self._config)

        # Pre-budget: refuse de demarrer si plafond deja atteint.
        # Estime un cout minimal (1 iteration, ~2k input + 500 output) pour
        # eviter de demarrer un loop qui crashera des le 1er tour.
        min_cost = self._budget.estimate_cost(self._model, 2000, 500)
        self._budget.assert_can_spend(min_cost)

        client = self._client_factory(self._api_key)
        result = PilotResult(prompt=prompt)

        # Conversation state envoye a chaque iteration. Le SDK Anthropic
        # demande l'historique complet (les tool_results referencent les
        # tool_use_ids precedents).
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": prompt},
        ]

        for iteration in range(1, self._max_iterations + 1):
            result.iterations = iteration

            if self._stop_requested:
                result.abort_reason = "user_stop"
                self._log_history("aborted", f"user_stop@iter{iteration}", "info")
                break

            # Plafond consecutif applique sauf si on est dans un batch
            # auto-confirme ; dans ce cas, on autorise sans re-demander.
            if self._allow_batch_remaining == 0:
                try:
                    self._sandbox.check_can_act()
                except SandboxViolationError as e:
                    # Demande explicite de re-confirmation utilisateur via
                    # un appel "synthetique" au confirmer (action 'wait').
                    decision = self._request_reconfirm(str(e))
                    if decision == "confirm":
                        self._sandbox.reset_consecutive()
                    elif decision == "allow_batch":
                        self._sandbox.reset_consecutive()
                        self._allow_batch_remaining = 5
                    else:
                        result.abort_reason = "consecutive_limit_no_reconfirm"
                        self._log_history(
                            "aborted",
                            f"consecutive_limit_iter{iteration}",
                            "low",
                        )
                        break

            # Pre-iteration : capture screenshot
            try:
                screenshot = self._screenshot_provider(self._sandbox)
            except Exception as e:  # noqa: BLE001
                result.abort_reason = f"screenshot_failed: {e}"
                self._log_history("error", f"screenshot_failed: {e}", "low")
                break
            screenshot_path = self._persist_screenshot(screenshot, iteration, "before")

            # Appel API : chiffre estime AVANT, recheck budget.
            estimated = self._budget.estimate_cost(self._model, 2500, 800)
            try:
                self._budget.assert_can_spend(estimated)
            except BudgetExceededError as e:
                result.abort_reason = f"budget_exceeded: {e}"
                self._log_history("aborted", "budget_exceeded", "info")
                break

            # Appel client Anthropic (peut lever)
            try:
                api_response = self._call_anthropic(client, messages, screenshot)
            except Exception as e:  # noqa: BLE001
                result.abort_reason = f"api_error: {e}"
                self._log_history("error", f"api_error: {e}", "info")
                break

            # Telemetrie + budget reel
            tokens_in = int(api_response.get("input_tokens", 0))
            tokens_out = int(api_response.get("output_tokens", 0))
            cost_eur = self._budget.estimate_cost(self._model, tokens_in, tokens_out)
            self._budget.record_spend(cost_eur, tokens_in, tokens_out)
            result.total_cost_eur = round(result.total_cost_eur + cost_eur, 6)
            result.total_tokens_in += tokens_in
            result.total_tokens_out += tokens_out

            # Anthropic peut renvoyer plusieurs tool_use blocks par turn.
            # On les traite sequentiellement (chacun est une action
            # confirmable). Le stop_reason='end_turn' sans tool_use signale
            # la fin de mission.
            tool_uses = api_response.get("tool_uses", [])
            assistant_content = api_response.get("raw_content", [])
            stop_reason = api_response.get("stop_reason", "")

            # On ajoute la reponse assistant a l'historique de conversation
            # (Anthropic exige d'envoyer l'echo a chaque turn).
            messages.append({"role": "assistant", "content": assistant_content})

            if not tool_uses:
                # Fin de mission propre.
                result.completed = stop_reason == "end_turn"
                if not result.abort_reason:
                    result.abort_reason = stop_reason or "no_tool_use"
                self._log_history(
                    "completed" if result.completed else "stopped",
                    f"iter{iteration}_{stop_reason}",
                    "info",
                )
                break

            # Boucle sur chaque tool_use propose
            tool_results: list[dict[str, Any]] = []
            should_break = False
            for tool_use in tool_uses:
                proposed = _parse_tool_use(tool_use)

                # Confirmation (ou batch en cours)
                decision = self._decide(proposed, screenshot)

                pilot_action = PilotAction(
                    iteration=iteration,
                    timestamp=datetime.now(tz=UTC).isoformat(),
                    proposed=proposed,
                    decision=decision,
                    executed=False,
                    cost_eur=cost_eur,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    screenshot_before=screenshot_path,
                )

                if decision == "cancel":
                    result.abort_reason = "user_cancel"
                    result.actions.append(pilot_action)
                    self._log_history("cancelled", proposed.short_label(), "info")
                    should_break = True
                    break

                if decision == "skip":
                    result.actions.append(pilot_action)
                    self._log_history("skipped", proposed.short_label(), "info")
                    tool_results.append(_make_tool_result(
                        tool_use, content="User skipped this action."
                    ))
                    continue

                # Sandbox check pour les actions a coordonnees
                executed = False
                err = ""
                screenshot_after_path = ""
                try:
                    if proposed.x is not None and proposed.y is not None:
                        self._sandbox.check_click(proposed.x, proposed.y)
                    self._action_executor(proposed)
                    self._sandbox.record_action()
                    executed = True
                    # Gestion du batch : 'allow_batch' sur cette action ouvre
                    # un quota de 5 actions suivantes auto-confirmees.
                    if decision == "allow_batch" and self._allow_batch_remaining == 0:
                        self._allow_batch_remaining = 5
                    elif self._allow_batch_remaining > 0:
                        self._allow_batch_remaining -= 1

                    # Capture post-action (utile pour Anthropic next turn)
                    try:
                        screenshot_after = self._screenshot_provider(self._sandbox)
                        screenshot_after_path = self._persist_screenshot(
                            screenshot_after, iteration, "after",
                        )
                    except Exception as e:  # noqa: BLE001
                        screenshot_after = b""
                        err = f"post_screenshot_failed: {e}"

                    tool_results.append(_make_tool_result(
                        tool_use,
                        screenshot_bytes=screenshot_after if executed else None,
                        content=f"Action executed: {proposed.short_label()}",
                    ))
                except (SandboxViolationError, PilotError) as e:
                    err = str(e)
                    tool_results.append(_make_tool_result(
                        tool_use, content=f"Action failed: {err}", is_error=True,
                    ))
                    self._log_history(
                        "error",
                        f"{proposed.short_label()}: {err}",
                        "medium",
                    )
                except Exception as e:  # noqa: BLE001
                    err = f"executor_error: {e}"
                    tool_results.append(_make_tool_result(
                        tool_use, content=f"Action failed: {err}", is_error=True,
                    ))
                    self._log_history(
                        "error",
                        f"{proposed.short_label()}: {err}",
                        "medium",
                    )

                pilot_action = PilotAction(
                    iteration=iteration,
                    timestamp=pilot_action.timestamp,
                    proposed=proposed,
                    decision=decision,
                    executed=executed,
                    cost_eur=cost_eur,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    error=err,
                    screenshot_before=screenshot_path,
                    screenshot_after=screenshot_after_path,
                )
                result.actions.append(pilot_action)
                if executed:
                    self._log_history(
                        "executed",
                        proposed.short_label(),
                        "medium" if proposed.kind in {"click", "key", "type"} else "low",
                    )

                # Esc / stop pendant l'iteration interne
                if self._stop_requested:
                    result.abort_reason = "user_stop"
                    should_break = True
                    break

            if should_break:
                break

            # Continue le dialogue : on doit envoyer les tool_results dans
            # un message user pour que Claude puisse iterer.
            if tool_results:
                messages.append({"role": "user", "content": tool_results})

        else:
            # boucle for-else : on a epuise max_iterations sans break
            if not result.abort_reason:
                result.abort_reason = "max_iterations_reached"

        return result

    # --- Internals -----------------------------------------------------

    def _decide(
        self,
        proposed: ProposedAction,
        screenshot: bytes,
    ) -> ConfirmationDecision:
        """Decision de confirmation, en tenant compte du batch en cours."""
        if self._allow_batch_remaining > 0:
            # On a deja l'autorisation utilisateur, on confirme
            # automatiquement. Le compteur batch est decremente apres
            # execution reussie.
            return "confirm"
        return self._confirmation.ask(proposed, screenshot)

    def _request_reconfirm(self, reason: str) -> ConfirmationDecision:
        """Demande explicite de re-confirmation apres plafond consecutif.

        On synthetise une action 'wait' avec rationale pour expliquer.
        """
        synthetic = ProposedAction(
            kind="wait",
            rationale=f"Plafond actions consecutives atteint. Raison: {reason}. "
                      "Confirme pour continuer ou annule.",
        )
        # Capture rapide (sandbox-bounded) -- best-effort, fallback bytes vides
        try:
            shot = self._screenshot_provider(self._sandbox)
        except Exception:  # noqa: BLE001
            shot = b""
        return self._confirmation.ask(synthetic, shot)

    def _persist_screenshot(self, data: bytes, iteration: int, phase: str) -> str:
        """Sauvegarde un screenshot et retourne son chemin (audit trail)."""
        if not data:
            return ""
        try:
            self._screenshot_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.warning("Pilot: impossible de creer %s : %s", self._screenshot_dir, e)
            return ""
        ts = int(time.time() * 1000)
        path = self._screenshot_dir / f"pilot_{ts}_iter{iteration}_{phase}.png"
        try:
            path.write_bytes(data)
        except OSError as e:
            logger.warning("Pilot: ecriture screenshot echouee : %s", e)
            return ""
        return str(path)

    def _log_history(self, status: str, detail: str, risk: str) -> None:
        """Trace dans HistoryManager si fourni."""
        if self._history is None:
            return
        try:
            self._history.log_action(
                module_name="pilot",
                action_type="pilot",
                description=detail,
                risk_level=risk,
                result_status=status,
                result_detail=detail,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("Pilot: log history echec : %s", e)

    def _call_anthropic(
        self,
        client: Any,
        messages: list[dict[str, Any]],
        screenshot: bytes,  # noqa: ARG002
    ) -> dict[str, Any]:
        """Appelle l'API Anthropic Computer Use et retourne une reponse normalisee.

        Format de retour:
            {
                "input_tokens": int,
                "output_tokens": int,
                "stop_reason": str,
                "tool_uses": list[dict],   # blocks tool_use bruts
                "raw_content": list[dict], # message.content brut (assistant)
            }

        Raises:
            PilotError: si l'API repond mal ou si le SDK n'est pas installe.
        """
        try:
            # SDK officiel Anthropic Python : `client.beta.messages.create`
            # avec tools=[{"type": "computer_20250124", "name": "computer", ...}].
            # Le SDK peut bouger d'ici la GA Computer Use ; le client_factory
            # injectable permet de patcher facilement.
            response = client.beta.messages.create(
                model=self._model,
                max_tokens=4096,
                tools=[
                    {
                        "type": "computer_20250124",
                        "name": "computer",
                        "display_width_px": self._sandbox.region.width,
                        "display_height_px": self._sandbox.region.height,
                    },
                ],
                messages=messages,
                betas=["computer-use-2025-01-24"],
            )
        except Exception as e:  # noqa: BLE001
            raise PilotError(f"Anthropic API call failed: {e}") from e

        return _normalize_anthropic_response(response)


# --- Helpers (module-level, testables) -----------------------------------


def _parse_tool_use(tool_use: dict[str, Any]) -> ProposedAction:
    """Convertit un tool_use Anthropic en ProposedAction structure."""
    inp = tool_use.get("input", {}) or {}
    action_kind = inp.get("action", tool_use.get("name", "unknown"))
    coord = inp.get("coordinate") or [None, None]
    if not isinstance(coord, (list, tuple)) or len(coord) < 2:
        coord = [None, None]
    x = int(coord[0]) if coord[0] is not None else None
    y = int(coord[1]) if coord[1] is not None else None
    return ProposedAction(
        kind=str(action_kind),
        x=x,
        y=y,
        text=inp.get("text"),
        key=inp.get("key"),
        scroll_direction=inp.get("scroll_direction"),
        scroll_amount=inp.get("scroll_amount"),
        rationale=str(inp.get("rationale", "")) or str(tool_use.get("rationale", "")),
    )


def _make_tool_result(
    tool_use: dict[str, Any],
    *,
    content: str = "",
    screenshot_bytes: bytes | None = None,
    is_error: bool = False,
) -> dict[str, Any]:
    """Construit un block tool_result a renvoyer au prochain turn.

    Si un screenshot est fourni, il est inclus comme image content (Anthropic
    accepte image inline en base64).
    """
    tool_use_id = tool_use.get("id", "")
    blocks: list[dict[str, Any]] = []
    if content:
        blocks.append({"type": "text", "text": content})
    if screenshot_bytes:
        import base64
        blocks.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": base64.b64encode(screenshot_bytes).decode("ascii"),
            },
        })
    if not blocks:
        blocks = [{"type": "text", "text": "ack"}]
    result: dict[str, Any] = {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": blocks,
    }
    if is_error:
        result["is_error"] = True
    return result


def _normalize_anthropic_response(response: Any) -> dict[str, Any]:
    """Normalise la reponse SDK Anthropic en dict previsible.

    Le SDK retourne des objets Pydantic ; on les convertit en dicts pour
    decoupler le pilot du shape exact (qui peut bouger).
    """
    # Tokens
    usage = getattr(response, "usage", None)
    input_tokens = getattr(usage, "input_tokens", 0) if usage else 0
    output_tokens = getattr(usage, "output_tokens", 0) if usage else 0
    stop_reason = getattr(response, "stop_reason", "") or ""

    raw_content_attr = getattr(response, "content", None) or []
    raw_content: list[dict[str, Any]] = []
    tool_uses: list[dict[str, Any]] = []

    for block in raw_content_attr:
        # Le block peut etre un objet Pydantic ou un dict (selon mock).
        if isinstance(block, dict):
            block_d = block
        else:
            block_d = {
                "type": getattr(block, "type", "text"),
                "text": getattr(block, "text", None),
                "id": getattr(block, "id", None),
                "name": getattr(block, "name", None),
                "input": getattr(block, "input", None),
            }
        raw_content.append(block_d)
        if block_d.get("type") == "tool_use":
            tool_uses.append(block_d)

    return {
        "input_tokens": int(input_tokens),
        "output_tokens": int(output_tokens),
        "stop_reason": str(stop_reason),
        "tool_uses": tool_uses,
        "raw_content": raw_content,
    }


# --- Default DI implementations ------------------------------------------


def _default_screenshot_provider(sandbox: Sandbox) -> bytes:  # noqa: ARG001
    """Default : leve NotImplementedError.

    L'implementation reelle (mss / Pillow ImageGrab) vit dans la couche GUI
    pour ne pas embarquer Pillow + mss en dependance core. Le caller doit
    fournir un provider explicite. Les tests fournissent un mock.
    """
    raise NotImplementedError(
        "Aucun ScreenshotProvider fourni a AnthropicPilot. "
        "Branche un provider concret (Pillow/mss en GUI, mock en tests)."
    )


def _default_action_executor(action: ProposedAction) -> None:  # noqa: ARG001
    """Default : leve NotImplementedError.

    L'executor reel (pyautogui/keyboard) n'est pas embarque ici par design :
    on veut que le caller fournisse une implementation explicite (ou un mock).
    """
    raise NotImplementedError(
        "Aucun ActionExecutor fourni a AnthropicPilot. "
        "Branche un executor concret (pyautogui en GUI, mock en tests)."
    )


def _default_client_factory(api_key: str) -> Any:
    """Default : utilise le SDK officiel anthropic.

    Si le SDK n'est pas installe, leve PilotError. Les tests passent un
    factory mocke pour eviter cette dependance en CI.
    """
    try:
        import anthropic  # type: ignore[import-not-found]
    except ImportError as e:
        raise PilotError(
            "Le SDK 'anthropic' n'est pas installe. Active l'extra Pilot : "
            "`pip install winboost[pilot]`."
        ) from e
    return anthropic.Anthropic(api_key=api_key)


# Decoration pour tracage developpeur (pas en prod chemin chaud)
_default_screenshot_provider.__name__ = "default_screenshot_provider"
_default_action_executor.__name__ = "default_action_executor"
_default_client_factory.__name__ = "default_client_factory"


# Type alias for explicit doc
StopCallback = Callable[[], None]
