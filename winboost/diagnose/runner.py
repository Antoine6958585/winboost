"""DiagnosticRunner — orchestrateur de diagnostics rules-based par theme.

Le runner :
1. Match une requete utilisateur (FR/EN) vers un ou plusieurs themes
2. Charge les checks de chaque theme matche
3. Execute les checks en sequence (rapide, < 5s total)
4. Aggrege les resultats en un `DiagnosticReport`
5. Construit un `recommended_fix_plan` ordonne par severite/dependances

Les themes sont declares dans `winboost.diagnose.themes` ; chaque theme
expose une fonction `get_checks() -> list[Check]` (voir
`themes/bluetooth.py` pour le pattern).

Pattern d'usage :
    runner = DiagnosticRunner()
    report = runner.run_from_query("ma manette bluetooth bug dans rocket league")

    if report.has_problems:
        print(report.summary)
        for step in report.recommended_fix_plan:
            print(f"  Etape {step['step']} : {step['description']}")
"""

from __future__ import annotations

import json
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from winboost.diagnose.checks import Check, CheckResult, Severity
from winboost.diagnose.themes import audio as audio_theme
from winboost.diagnose.themes import bluetooth as bluetooth_theme
from winboost.diagnose.themes import display as display_theme
from winboost.diagnose.themes import gaming as gaming_theme
from winboost.diagnose.themes import network as network_theme

# ---------------------------------------------------------------------------
# Mapping theme -> module (extensible : ajouter une entree pour un nouveau theme)
# ---------------------------------------------------------------------------

ThemeFactory = Callable[[], list[Check]]

THEME_REGISTRY: dict[str, ThemeFactory] = {
    "bluetooth": bluetooth_theme.get_checks,
    "gaming": gaming_theme.get_checks,
    "network": network_theme.get_checks,
    "audio": audio_theme.get_checks,
    "display": display_theme.get_checks,
}

# Keywords FR/EN -> theme. Ordre = ordre de scan dans la query.
# Une query peut matcher plusieurs themes (ex: "manette bluetooth dans rocket league"
# matche bluetooth + gaming).
THEME_KEYWORDS: dict[str, tuple[str, ...]] = {
    "bluetooth": (
        "bluetooth",
        "bt",
        "manette",
        "controller",
        "appairage",
        "appaire",
        "pairing",
        "casque sans fil",
        "headset bt",
    ),
    "gaming": (
        "jeu",
        "jeux",
        "game",
        "gaming",
        "rocket league",
        "steam",
        "gamepad",
        "xinput",
        "directinput",
        "xbox",
        "playstation",
        "fps",
        "lag",
    ),
    "network": (
        "internet",
        "dns",
        "ping",
        "wifi",
        "wi-fi",
        "ethernet",
        "reseau",
        "réseau",
        "network",
        "connexion",
        "deconnect",
        "déconnect",
        "lent",
        "ipv6",
    ),
    "audio": (
        "son",
        "audio",
        "casque",
        "haut parleur",
        "haut-parleur",
        "speaker",
        "micro",
        "microphone",
        "muet",
        "sound",
    ),
    "display": (
        "ecran",
        "écran",
        "luminosite",
        "luminosité",
        "display",
        "monitor",
        "resolution",
        "résolution",
        "ecran noir",
        "écran noir",
        "hdr",
        "brightness",
        "moniteur",
        "screen",
    ),
}

DEFAULT_FALLBACK_THEME = "bluetooth"


@dataclass(frozen=True)
class DiagnosticReport:
    """Rapport complet d'un diagnostic.

    Attributes:
        theme: Nom du theme execute (ou themes joints par "+", ex: "bluetooth+gaming").
        query: La requete originale fournie par l'utilisateur.
        timestamp: Timestamp UTC de l'execution.
        checks: Liste des CheckResult dans l'ordre d'execution.
        summary: Phrase recapitulative (ex: "2 erreurs detectees").
        recommended_fix_plan: Plan ordonne d'actions recommandees. Chaque
            etape est un dict avec au minimum les cles "step", "description".
            Si l'etape correspond a une action YAML : cle "action_id".
            Si l'etape est manuelle : cle "manual": True.
    """

    theme: str
    query: str
    timestamp: datetime
    checks: tuple[CheckResult, ...]
    summary: str
    recommended_fix_plan: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    @property
    def has_problems(self) -> bool:
        """True si au moins un check signale un probleme."""
        return any(c.is_problem for c in self.checks)

    @property
    def themes(self) -> list[str]:
        """Liste des themes individuels (split sur '+')."""
        return [t for t in self.theme.split("+") if t]

    def to_dict(self) -> dict[str, Any]:
        """Serialisation JSON-friendly (datetime -> isoformat)."""
        return {
            "theme": self.theme,
            "query": self.query,
            "timestamp": self.timestamp.isoformat(),
            "checks": [c.to_dict() for c in self.checks],
            "summary": self.summary,
            "recommended_fix_plan": [dict(step) for step in self.recommended_fix_plan],
            "has_problems": self.has_problems,
        }

    def to_json(self, indent: int | None = 2) -> str:
        """Serialisation JSON directe (utile pour CLI --json)."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


class DiagnosticRunner:
    """Orchestrateur principal des diagnostics.

    Le runner est stateless : on peut le reutiliser pour plusieurs requetes
    sans probleme. Pour les tests, on peut injecter un `theme_registry`
    custom et/ou des `theme_keywords` custom.

    Args:
        theme_registry: Mapping theme -> factory de checks. Defaut = THEME_REGISTRY.
        theme_keywords: Mapping theme -> keywords. Defaut = THEME_KEYWORDS.
        fallback_theme: Theme utilise si aucun match. Defaut = "bluetooth"
            (choisi car le use case principal est la manette d'Antoine).
    """

    def __init__(
        self,
        theme_registry: dict[str, ThemeFactory] | None = None,
        theme_keywords: dict[str, tuple[str, ...]] | None = None,
        fallback_theme: str = DEFAULT_FALLBACK_THEME,
        parallel: bool = True,
        max_workers: int = 8,
    ) -> None:
        self.theme_registry = theme_registry if theme_registry is not None else THEME_REGISTRY
        self.theme_keywords = theme_keywords if theme_keywords is not None else THEME_KEYWORDS
        self.fallback_theme = fallback_theme
        self.parallel = parallel
        self.max_workers = max_workers

        if self.fallback_theme not in self.theme_registry:
            raise ValueError(
                f"fallback_theme '{self.fallback_theme}' inconnu. "
                f"Themes disponibles : {sorted(self.theme_registry.keys())}"
            )

    # -----------------------------------------------------------------------
    # Matching de theme depuis une requete utilisateur
    # -----------------------------------------------------------------------

    def match_themes(self, query: str) -> list[str]:
        """Identifie les themes pertinents pour une requete.

        Args:
            query: La requete brute (FR ou EN).

        Returns:
            Liste de noms de themes matches, ordonnee selon THEME_KEYWORDS.
            Si aucun match, retourne [fallback_theme].
        """
        query_lc = query.lower().strip()
        matches: list[str] = []

        for theme, keywords in self.theme_keywords.items():
            for kw in keywords:
                if kw in query_lc:
                    if theme not in matches:
                        matches.append(theme)
                    break  # une seule matche suffit pour ce theme

        if not matches:
            return [self.fallback_theme]
        return matches

    # -----------------------------------------------------------------------
    # Execution
    # -----------------------------------------------------------------------

    def run_from_query(self, query: str) -> DiagnosticReport:
        """Execute le diagnostic depuis une requete utilisateur.

        Match les themes via match_themes() puis fusionne les rapports si
        plusieurs themes matchent.
        """
        if not query or not query.strip():
            raise ValueError("query ne peut pas etre vide")

        themes = self.match_themes(query)
        return self.run_themes(themes, original_query=query)

    def run_themes(self, themes: list[str], original_query: str = "") -> DiagnosticReport:
        """Execute un ou plusieurs themes et fusionne les rapports.

        Args:
            themes: Liste de noms de themes a executer.
            original_query: La requete utilisateur originale (pour le rapport).

        Returns:
            Un DiagnosticReport unique combinant tous les checks.
        """
        if not themes:
            raise ValueError("Au moins un theme requis")

        all_results: list[CheckResult] = []
        executed: list[str] = []
        ordered_checks: list[Check] = []

        for theme_name in themes:
            factory = self.theme_registry.get(theme_name)
            if factory is None:
                # Theme inconnu : on log dans le rapport mais on continue
                all_results.append(
                    CheckResult(
                        name=f"theme_unknown_{theme_name}",
                        severity=Severity.WARNING.value,
                        message=f"Theme inconnu : '{theme_name}'",
                        details={"theme": theme_name},
                        suggested_actions=(),
                    )
                )
                continue

            ordered_checks.extend(factory())
            executed.append(theme_name)

        if self.parallel and len(ordered_checks) > 1:
            # Parallelisation I/O-bound : chaque check fait 1-2 calls subprocess
            # PowerShell. Avec ThreadPoolExecutor on aggrege les latences cold-start.
            with ThreadPoolExecutor(max_workers=self.max_workers) as ex:
                futures = [ex.submit(c.safe_run) for c in ordered_checks]
                results_in_order = [f.result() for f in futures]
            all_results.extend(results_in_order)
        else:
            for check in ordered_checks:
                all_results.append(check.safe_run())

        theme_label = "+".join(executed) if executed else "+".join(themes)
        summary = self._build_summary(all_results)
        plan = self._build_fix_plan(all_results)

        return DiagnosticReport(
            theme=theme_label,
            query=original_query,
            timestamp=datetime.now(UTC),
            checks=tuple(all_results),
            summary=summary,
            recommended_fix_plan=tuple(plan),
        )

    def run_theme(self, theme: str, original_query: str = "") -> DiagnosticReport:
        """Raccourci pour executer un seul theme."""
        return self.run_themes([theme], original_query=original_query)

    # -----------------------------------------------------------------------
    # Synthese
    # -----------------------------------------------------------------------

    @staticmethod
    def _build_summary(results: list[CheckResult]) -> str:
        """Construit la phrase de synthese d'apres les severites."""
        if not results:
            return "Aucun check execute"

        counts = {
            Severity.OK.value: 0,
            Severity.WARNING.value: 0,
            Severity.ERROR.value: 0,
            Severity.CRITICAL.value: 0,
        }
        for r in results:
            counts[r.severity] = counts.get(r.severity, 0) + 1

        problems = (
            counts[Severity.WARNING.value]
            + counts[Severity.ERROR.value]
            + counts[Severity.CRITICAL.value]
        )
        if problems == 0:
            return f"Aucun probleme detecte ({counts[Severity.OK.value]} checks OK)"

        parts: list[str] = []
        if counts[Severity.CRITICAL.value]:
            parts.append(f"{counts[Severity.CRITICAL.value]} critique(s)")
        if counts[Severity.ERROR.value]:
            parts.append(f"{counts[Severity.ERROR.value]} erreur(s)")
        if counts[Severity.WARNING.value]:
            parts.append(f"{counts[Severity.WARNING.value]} warning(s)")

        # Ajoute les 1-2 messages les plus graves pour le contexte
        sorted_problems = sorted(
            [r for r in results if r.is_problem],
            key=lambda r: (
                {"critical": 0, "error": 1, "warning": 2}.get(r.severity, 3)
            ),
        )
        top_msgs = [r.message for r in sorted_problems[:2]]
        detail = " : " + " | ".join(top_msgs) if top_msgs else ""

        return f"{', '.join(parts)} detecte(s){detail}"

    @staticmethod
    def _build_fix_plan(results: list[CheckResult]) -> list[dict[str, Any]]:
        """Construit un plan de fix ordonne et dedoublonne.

        Strategie :
        1. On collecte tous les `suggested_actions` des checks problematiques
        2. On dedoublonne en preservant l'ordre d'apparition
        3. On ordonne par severite : critical -> error -> warning
        4. Si un check problematique n'a pas d'action_id : etape manuelle
        """
        # Groupes ordonnes par severite
        order = [Severity.CRITICAL.value, Severity.ERROR.value, Severity.WARNING.value]
        plan: list[dict[str, Any]] = []
        seen_actions: set[str] = set()
        seen_manual: set[str] = set()
        step = 1

        for severity in order:
            for r in results:
                if r.severity != severity:
                    continue

                if r.suggested_actions:
                    for action_id in r.suggested_actions:
                        if action_id in seen_actions:
                            continue
                        seen_actions.add(action_id)
                        plan.append(
                            {
                                "step": step,
                                "action_id": action_id,
                                "description": _describe_action(action_id, r),
                                "severity": r.severity,
                                "from_check": r.name,
                            }
                        )
                        step += 1
                else:
                    # Pas d'action YAML => etape manuelle dedoublonnee par message
                    key = r.message
                    if key in seen_manual:
                        continue
                    seen_manual.add(key)
                    plan.append(
                        {
                            "step": step,
                            "manual": True,
                            "description": r.message,
                            "severity": r.severity,
                            "from_check": r.name,
                        }
                    )
                    step += 1

        return plan


# ---------------------------------------------------------------------------
# Helpers internes
# ---------------------------------------------------------------------------


# Catalogue minimal action_id -> description courte FR.
# Pas exhaustif : utilise uniquement comme fallback descriptif. Les checks
# sont libres de fournir un message plus precis dans `CheckResult.message`.
_ACTION_DESCRIPTIONS: dict[str, str] = {
    "net_011": "Couper le service Bluetooth (toggle off)",
    "net_012": "Redemarrer / activer le service Bluetooth",
    "net_013": "Reset Winsock (corrige les piles reseau corrompues)",
    "net_014": "Flush DNS cache",
    "net_015": "Forcer DNS Cloudflare 1.1.1.1",
    "net_016": "Restaurer DNS automatique (DHCP)",
    "net_017": "Disable IPv6",
    "net_018": "Enable IPv6",
    "net_019": "Disable Wi-Fi adapter",
    "net_020": "Enable Wi-Fi adapter",
    "sys_011": "Activer le mode sombre Windows",
    "sys_012": "Desactiver le mode sombre Windows",
    "sys_013": "Luminosite a 30 %",
    "sys_014": "Luminosite a 60 %",
    "sys_015": "Luminosite a 100 %",
    "sys_016": "Activer Focus Assist",
    "sys_017": "Desactiver Focus Assist",
    "sys_018": "Activer Night Light",
    "sys_019": "Plan d'alimentation Hautes performances",
    "sys_020": "Plan d'alimentation Equilibre",
    "app_011": "Couper le son (mute)",
    "app_012": "Volume a 20 %",
    "app_013": "Volume a 50 %",
    "app_014": "Volume a 80 %",
}


def _describe_action(action_id: str, check_result: CheckResult) -> str:
    """Construit une description lisible pour une etape du plan de fix.

    Combine la description catalogue de l'action_id avec le message du
    check, pour que l'utilisateur comprenne *pourquoi* cette action est
    suggeree.
    """
    base = _ACTION_DESCRIPTIONS.get(action_id, f"Action {action_id}")
    return f"{base} (cause : {check_result.message})"
