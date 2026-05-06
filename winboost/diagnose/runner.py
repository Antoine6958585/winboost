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
        """Construit un plan de fix ordonne, dedoublonne et FILTRE.

        Strategie :
        1. Tri par severite : critical -> error -> warning.
        2. Pour chaque check problematique :
           a. On filtre les actions "symboliques" (declaratives, non
              automatisables — voir `_SYMBOLIC_ACTIONS`). Les autres
              `suggested_actions` produisent un step actionnable.
           b. Si le check est dans MANUAL_FIX_DESCRIPTIONS et n'a pas
              produit d'action automatisable, on ajoute un step manuel
              riche (description + alternative).
           c. Sinon : warning sans action et sans manual fix preconfigure
              -> exclu (filtre anti-bruit), SAUF si message contient
              "manuel:" ou "action:" (signal explicite de l'auteur du check).
              Errors/criticals sans action -> step manuel base sur le message.
        3. Filtre supplementaire : warnings issus d'un timeout / "lecture KO" /
           "impossible" sont exclus (pas d'info utile pour l'utilisateur).
        4. Dedoublonnage : un meme `action_id` ou un meme message ne sortent
           qu'une seule fois.
        """
        # Groupes ordonnes par severite
        order = [Severity.CRITICAL.value, Severity.ERROR.value, Severity.WARNING.value]
        plan: list[dict[str, Any]] = []
        seen_actions: set[str] = set()
        seen_manual_keys: set[str] = set()
        step = 1

        for severity in order:
            for r in results:
                if r.severity != severity:
                    continue

                # Actions automatisables : tout suggested_action sauf les
                # symboliques (qui declenchent un manual fix riche).
                automated_actions = tuple(
                    a for a in (r.suggested_actions or ()) if a not in _SYMBOLIC_ACTIONS
                )

                if automated_actions:
                    for action_id in automated_actions:
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
                    continue

                # Filtre anti-bruit : un WARNING dont le message est purement
                # diagnostique (timeout, lecture KO, "impossible de lire")
                # signale que le check n'a pas pu juger de l'etat du systeme.
                # Dans ce cas on ne genere AUCUN step (meme si check est dans
                # MANUAL_FIX_DESCRIPTIONS), parce que rien ne prouve qu'il y
                # a un probleme reel a corriger.
                if severity == Severity.WARNING.value and _warning_is_noise(r):
                    continue

                # Pas d'action automatisable. Tente un manual fix riche.
                manual_desc = MANUAL_FIX_DESCRIPTIONS.get(r.name)
                if manual_desc is not None:
                    key = f"manual:{r.name}"
                    if key in seen_manual_keys:
                        continue
                    seen_manual_keys.add(key)
                    plan.append(
                        {
                            "step": step,
                            "manual": True,
                            "description": _format_manual_description(manual_desc, r),
                            "alternative": manual_desc.get("alternative"),
                            "severity": r.severity,
                            "from_check": r.name,
                        }
                    )
                    step += 1
                    continue

                # Filtre anti-bruit : warning sans action ni manual fix.
                if severity == Severity.WARNING.value and not _warning_is_actionable(r):
                    continue

                # Erreur/critique (ou warning explicitement actionable) sans
                # action ni manual fix : fallback step manuel sur le message.
                key = f"msg:{r.message}"
                if key in seen_manual_keys:
                    continue
                seen_manual_keys.add(key)
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


# ---------------------------------------------------------------------------
# Manual fix descriptions — pour les checks dont le fix n'est pas automatable
#
# Beaucoup de problemes Windows (drivers BT mal mappes, services optionnels,
# updates Windows manquantes) n'ont pas d'action YAML safe : la correction
# passe par une manipulation utilisateur (Settings, Device Manager, Update).
# Ce mapping permet d'enrichir le plan de fix avec des instructions concretes
# au lieu d'un message brut "warning".
#
# Convention : la cle est le `name` du Check ; la valeur est un dict avec
# `step_description` (instructions principales) et `alternative` (plan B
# si la premiere methode echoue, ou None si aucune).
# ---------------------------------------------------------------------------

MANUAL_FIX_DESCRIPTIONS: dict[str, dict[str, str | None]] = {
    "bluetooth_gamepad_mapping": {
        "step_description": (
            "Manette BT mal mappee. Selon le type :\n"
            "  - Xbox Wireless : desappairer + reappairer (Settings -> Bluetooth -> "
            "Remove -> maintenir bouton sync -> Re-pair). Force la reinstall du driver.\n"
            "  - DualSense / DualShock 4 : Sony n'expose PAS XInput sur le profil BT. "
            "Solution = installer DS4Windows (https://github.com/Ryochan7/DS4Windows) "
            "qui emule une manette Xbox virtuelle. Cocher 'Hide DS4 Controller' dans "
            "les Settings DS4Windows pour eviter le double-input.\n"
            "  - Pro Controller Switch / Stadia : memes types de wrappers (BetterJoy, "
            "Stadiacontroller-rs). Le BT pur ne fait pas XInput non plus."
        ),
        "alternative": (
            "Si reappairage Xbox ne fixe pas : Device Manager -> Bluetooth -> la manette "
            "-> Uninstall device + 'Delete driver' -> reboot -> reappairer. Si DualSense, "
            "rester sur USB filaire si tu ne veux pas installer DS4Windows."
        ),
    },
    "gaming_xbox_driver_freshness": {
        "step_description": (
            "Driver Xbox manquant ou obsolete. Settings -> Windows Update -> "
            "Optional updates -> Driver updates -> installer 'Xbox Wireless "
            "Adapter' ou 'XINPUT Compatible'. Si absent, telecharger depuis le "
            "site Microsoft."
        ),
        "alternative": None,
    },
    "gaming_xbl_gamesave_status": {
        "step_description": (
            "Service XblGameSave arrete = pas de saves cloud Xbox. Pour redemarrer : "
            "`winboost chat 'redemarrer service xbl'` ou Services.msc -> "
            "XblGameSave -> Start."
        ),
        "alternative": None,
    },
    "bluetooth_driver_freshness": {
        "step_description": (
            "Drivers Bluetooth obsoletes. Device Manager -> Bluetooth -> "
            "adaptateur principal (Intel/Realtek/Qualcomm) -> Update driver -> "
            "Search automatically."
        ),
        "alternative": None,
    },
}


# Actions "symboliques" : declaratives, non automatisables. Elles signalent
# au plan de fix qu'un manual fix riche doit etre genere via
# MANUAL_FIX_DESCRIPTIONS, plutot que produire un step actionnable.
_SYMBOLIC_ACTIONS: frozenset[str] = frozenset(
    {
        "bt_unpair_repair",
    }
)


# Mots-cles qui signalent qu'un message de warning, meme sans suggested_actions,
# doit apparaitre dans le plan (l'auteur du check le veut explicitement).
_ACTIONABLE_KEYWORDS: tuple[str, ...] = ("manuel:", "action:")


# Mots-cles qui signalent un warning purement diagnostique (pas d'info
# utile pour l'utilisateur) : a exclure du plan.
_NOISE_KEYWORDS: tuple[str, ...] = (
    "timeout",
    "lecture ko",
    "lecture echouee",
    "impossible de lire",
    "impossible",
    "non executable",
    "subprocess/encoding",
)


def _warning_is_noise(check_result: CheckResult) -> bool:
    """True si le message de warning est purement diagnostique (timeout,
    lecture KO, "impossible de lire") — donc sans valeur pour l'utilisateur.

    Quand un check ne peut pas determiner l'etat du systeme (PowerShell timeout,
    parsing KO), on ne sait pas s'il y a un probleme. On exclut ce warning
    du plan, plutot que de generer une action qui pourrait etre inutile.
    """
    msg = (check_result.message or "").lower()
    return any(kw in msg for kw in _NOISE_KEYWORDS)


def _warning_is_actionable(check_result: CheckResult) -> bool:
    """True si un warning sans suggested_actions merite d'apparaitre dans le plan.

    Regles :
    - Si le message contient "manuel:" ou "action:" -> oui (signal explicite).
    - Si le message est du bruit diagnostique -> non.
    - Sinon -> non (filtre anti-bruit par defaut).
    """
    msg = (check_result.message or "").lower()
    if any(kw in msg for kw in _ACTIONABLE_KEYWORDS):
        return True
    if _warning_is_noise(check_result):
        return False
    return False


def _format_manual_description(
    manual_desc: dict[str, str | None], check_result: CheckResult
) -> str:
    """Concatene la description manuelle avec la cause (message du check).

    Le but : que l'utilisateur voie d'abord *quoi faire*, puis *pourquoi*.
    """
    base = manual_desc.get("step_description") or check_result.message
    cause = check_result.message
    if cause and cause not in (base or ""):
        return f"{base} (cause : {cause})"
    return base or ""
