"""Budget manager — plafond mensuel d'usage Anthropic Computer Use.

Suit les depenses (en EUR) sur l'API Anthropic et bloque les nouvelles
actions des qu'un plafond mensuel est atteint. Le plafond default est
**5 EUR/mois** (~30-50 actions Computer Use a 0.10-0.15 EUR/action selon
modele et taille screenshots).

L'utilisateur peut ajuster le plafond depuis Settings, mais il est
volontairement conservateur par defaut — c'est de l'argent reel, et le
profil Lab est experimental.

## Stockage

Le compteur est persiste dans `%LOCALAPPDATA%/WinBoost/pilot_budget.json` :

    {
      "month": "2026-05",          # YYYY-MM, reset auto au changement
      "spent_eur": 1.234,           # cumul du mois courant
      "limit_eur": 5.0,             # plafond mensuel
      "actions_count": 8            # nombre d'actions executees ce mois
    }

Format JSON UTF-8, indente, ecrit atomiquement (best-effort).

## Couts estimes

Source : tarifs Anthropic publics (sonnet-4-6 / opus-4-7) au 2026-01.
Calcul : input_tokens * input_rate + output_tokens * output_rate. La
conversion USD -> EUR utilise un taux fixe pessimiste (1 USD = 1 EUR) pour
ne jamais sous-estimer le cout — c'est volontaire.

API : `cost_eur = MODEL_PRICING[model].compute(input_tokens, output_tokens)`.
"""

from __future__ import annotations

import contextlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from winboost.core.config import DEFAULT_CONFIG_DIR

logger = logging.getLogger(__name__)

__all__ = [
    "BudgetManager",
    "BudgetExceededError",
    "ModelPricing",
    "MODEL_PRICING",
    "DEFAULT_BUDGET_EUR",
    "DEFAULT_BUDGET_FILE",
]

#: Plafond mensuel par defaut, en EUR. Volontairement conservateur.
DEFAULT_BUDGET_EUR: float = 5.0

#: Chemin de stockage par defaut du compteur de depenses.
DEFAULT_BUDGET_FILE: Path = DEFAULT_CONFIG_DIR / "pilot_budget.json"


@dataclass(frozen=True)
class ModelPricing:
    """Prix d'un modele Anthropic, exprime en EUR / 1M tokens.

    On utilise EUR/1M pour rester aligne sur la pricing-page Anthropic
    (qui exprime tout en USD/1M tokens). Le ratio USD->EUR est applique
    en amont dans `MODEL_PRICING`.
    """

    name: str
    input_per_1m_eur: float
    output_per_1m_eur: float

    def compute(self, input_tokens: int, output_tokens: int) -> float:
        """Retourne le cout estime en EUR pour un appel donne.

        Args:
            input_tokens: nombre de tokens en entree (>= 0).
            output_tokens: nombre de tokens generes (>= 0).
        """
        if input_tokens < 0 or output_tokens < 0:
            raise ValueError("Token counts must be non-negative")
        cost = (
            (input_tokens / 1_000_000) * self.input_per_1m_eur
            + (output_tokens / 1_000_000) * self.output_per_1m_eur
        )
        return round(cost, 6)


#: Tarifs publics Anthropic (extraits 2026-01) avec marge USD=EUR.
#: Source : https://www.anthropic.com/pricing — a re-checker avant chaque
#: release. Les noms de modeles suivent les conventions Anthropic ("model
#: family + date").
MODEL_PRICING: dict[str, ModelPricing] = {
    # Sonnet : ~3 USD/1M input, ~15 USD/1M output
    "claude-sonnet-4-6": ModelPricing("claude-sonnet-4-6", 3.0, 15.0),
    "claude-sonnet-4-20250514": ModelPricing("claude-sonnet-4-20250514", 3.0, 15.0),
    # Opus : ~15 USD/1M input, ~75 USD/1M output (a re-verifier)
    "claude-opus-4-7": ModelPricing("claude-opus-4-7", 15.0, 75.0),
}


class BudgetExceededError(RuntimeError):
    """Levee quand une action ferait depasser le plafond mensuel.

    Le message contient le plafond, le cumul actuel, et la date du
    prochain reset (1er du mois suivant).
    """


class BudgetManager:
    """Suit les depenses Anthropic Computer Use du mois en cours.

    Concurrency note: cette classe n'est pas thread-safe au sens fort.
    Le pilot tourne dans la GUI (boucle Tk) ou en CLI synchronously, et
    chaque action est confirmee a la main : pas de risque pratique de
    race conditions. Si on veut paralleliser un jour, ajouter un lock.
    """

    def __init__(
        self,
        path: Path | None = None,
        limit_eur: float | None = None,
        clock: Any = None,
    ) -> None:
        """Initialise le manager.

        Args:
            path: chemin du fichier de persistance. Default: `DEFAULT_BUDGET_FILE`.
            limit_eur: plafond mensuel a appliquer (et persister). Si None et
                fichier absent -> `DEFAULT_BUDGET_EUR`. Si None et fichier
                present -> on conserve la valeur du fichier.
            clock: callable retournant un `datetime` (UTC) — injectable pour
                les tests (faux mois, faux reset). Default: `datetime.now`.
        """
        self._path = path or DEFAULT_BUDGET_FILE
        self._clock = clock or (lambda: datetime.now(tz=UTC))

        self._month: str = ""
        self._spent_eur: float = 0.0
        self._limit_eur: float = DEFAULT_BUDGET_EUR
        self._actions_count: int = 0

        self._load()

        # Si l'appelant fournit un limit explicite, il prime sur le fichier.
        if limit_eur is not None:
            if limit_eur <= 0:
                raise ValueError("limit_eur must be > 0")
            self._limit_eur = float(limit_eur)
            self._save()

    @property
    def limit_eur(self) -> float:
        return self._limit_eur

    @property
    def spent_eur(self) -> float:
        self._maybe_reset()
        return self._spent_eur

    @property
    def actions_count(self) -> int:
        self._maybe_reset()
        return self._actions_count

    @property
    def remaining_eur(self) -> float:
        self._maybe_reset()
        return max(0.0, self._limit_eur - self._spent_eur)

    @property
    def current_month(self) -> str:
        self._maybe_reset()
        return self._month

    def set_limit(self, limit_eur: float) -> None:
        """Ajuste le plafond mensuel et persiste."""
        if limit_eur <= 0:
            raise ValueError("limit_eur must be > 0")
        self._limit_eur = float(limit_eur)
        self._save()

    def can_spend(self, estimated_cost_eur: float) -> bool:
        """Indique si une depense estimee tient dans le plafond restant."""
        if estimated_cost_eur < 0:
            raise ValueError("estimated_cost_eur must be >= 0")
        self._maybe_reset()
        return (self._spent_eur + estimated_cost_eur) <= self._limit_eur

    def assert_can_spend(self, estimated_cost_eur: float) -> None:
        """Leve `BudgetExceededError` si la depense ne tient pas."""
        if not self.can_spend(estimated_cost_eur):
            next_reset = self._next_reset_date()
            raise BudgetExceededError(
                f"Plafond mensuel Pilot atteint : {self._spent_eur:.4f} EUR "
                f"deja depenses sur {self._limit_eur:.2f} EUR autorises. "
                f"Prochain reset : {next_reset}. Augmente le plafond dans "
                f"Settings ou attends le reset."
            )

    def record_spend(
        self,
        cost_eur: float,
        tokens_in: int = 0,
        tokens_out: int = 0,
    ) -> None:
        """Enregistre une depense reelle apres execution d'une action.

        Args:
            cost_eur: cout reel de l'appel (>= 0).
            tokens_in: tokens en entree (telemetrie, optionnel).
            tokens_out: tokens generes (telemetrie, optionnel).
        """
        if cost_eur < 0:
            raise ValueError("cost_eur must be >= 0")
        self._maybe_reset()
        self._spent_eur = round(self._spent_eur + cost_eur, 6)
        self._actions_count += 1
        # tokens_in / tokens_out ne sont pas persistes en v1 (telemetrie
        # locale legere). On les expose pour usage futur (dashboard).
        _ = tokens_in, tokens_out
        self._save()
        logger.debug(
            "BudgetManager: +%.4f EUR (total %.4f / %.2f, actions=%d)",
            cost_eur, self._spent_eur, self._limit_eur, self._actions_count,
        )

    def estimate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """Helper : retourne le cout estime via `MODEL_PRICING`.

        Si le modele n'est pas dans la table, fallback sur sonnet-4-6
        (estimation prudente). On log un warning.
        """
        pricing = MODEL_PRICING.get(model)
        if pricing is None:
            logger.warning(
                "BudgetManager.estimate_cost: pricing inconnu pour %s, "
                "fallback sur claude-sonnet-4-6.", model
            )
            pricing = MODEL_PRICING["claude-sonnet-4-6"]
        return pricing.compute(input_tokens, output_tokens)

    # --- Internals -----------------------------------------------------

    def _now_month(self) -> str:
        """Retourne le mois courant au format YYYY-MM."""
        now = self._clock()
        return now.strftime("%Y-%m")

    def _next_reset_date(self) -> str:
        """Retourne la date du 1er du mois suivant (YYYY-MM-DD)."""
        now = self._clock()
        year = now.year + (1 if now.month == 12 else 0)
        month = 1 if now.month == 12 else now.month + 1
        return f"{year:04d}-{month:02d}-01"

    def _maybe_reset(self) -> None:
        """Reset auto du compteur si on a change de mois."""
        current = self._now_month()
        if current != self._month:
            logger.info(
                "BudgetManager: reset mensuel (%s -> %s, actions ce mois: %d)",
                self._month or "<init>", current, self._actions_count,
            )
            self._month = current
            self._spent_eur = 0.0
            self._actions_count = 0
            self._save()

    def _load(self) -> None:
        """Charge le fichier ou initialise le mois courant."""
        if not self._path.exists():
            self._month = self._now_month()
            return
        try:
            data: dict[str, Any] = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(
                "BudgetManager: fichier %s illisible (%s), reset des compteurs.",
                self._path, e,
            )
            self._month = self._now_month()
            return

        self._month = str(data.get("month", self._now_month()))
        self._spent_eur = float(data.get("spent_eur", 0.0))
        self._limit_eur = float(data.get("limit_eur", DEFAULT_BUDGET_EUR))
        self._actions_count = int(data.get("actions_count", 0))

        # Reset si le fichier est d'un mois precedent.
        self._maybe_reset()

    def _save(self) -> None:
        """Ecrit le compteur sur disque (best-effort, ne crash pas le pilot)."""
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.warning("BudgetManager: impossible de creer %s : %s", self._path.parent, e)
            return
        payload = {
            "month": self._month,
            "spent_eur": round(self._spent_eur, 6),
            "limit_eur": self._limit_eur,
            "actions_count": self._actions_count,
        }
        with contextlib.suppress(OSError):
            self._path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
