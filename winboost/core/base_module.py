"""Module de base abstrait — tous les modules WinBoost heritent de BaseModule."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RiskLevel(Enum):
    """Niveaux de risque des actions WinBoost."""

    INFO = "info"          # Lecture seule
    LOW = "low"            # Confirmation simple
    MEDIUM = "medium"      # Preview + explication + confirmation
    HIGH = "high"          # Warning + dry-run + double confirm
    CRITICAL = "critical"  # Bloque par defaut


@dataclass
class Issue:
    """Un probleme detecte par un module."""

    id: str
    description: str
    detail: str = ""
    risk_level: RiskLevel = RiskLevel.LOW
    auto_fixable: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScanResult:
    """Resultat d'un scan de module."""

    module_name: str
    issues: list[Issue] = field(default_factory=list)
    summary: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def issue_count(self) -> int:
        return len(self.issues)

    @property
    def has_issues(self) -> bool:
        return len(self.issues) > 0


@dataclass
class FixResult:
    """Resultat d'une correction appliquee."""

    module_name: str
    fixed: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    summary: str = ""

    @property
    def fixed_count(self) -> int:
        return len(self.fixed)

    @property
    def success(self) -> bool:
        return len(self.errors) == 0


class BaseModule(ABC):
    """Classe abstraite pour tous les modules WinBoost.

    Chaque module doit implementer scan(), fix() et preview().
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Identifiant unique du module (ex: 'temp_cleaner')."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Description courte du module."""
        ...

    @property
    @abstractmethod
    def risk_level(self) -> RiskLevel:
        """Niveau de risque par defaut du module."""
        ...

    @abstractmethod
    def scan(self) -> ScanResult:
        """Analyse le systeme sans modification. Retourne les problemes detectes."""
        ...

    @abstractmethod
    def fix(self, scan_result: ScanResult) -> FixResult:
        """Applique les corrections pour les problemes detectes."""
        ...

    def preview(self, scan_result: ScanResult) -> str:
        """Description humaine des corrections qui seront appliquees."""
        if not scan_result.has_issues:
            return f"[{self.name}] Aucun probleme detecte."

        lines = [f"[{self.name}] {scan_result.issue_count} probleme(s) detecte(s) :"]
        for issue in scan_result.issues:
            prefix = "  [AUTO]" if issue.auto_fixable else "  [MANUEL]"
            lines.append(f"{prefix} {issue.description}")
        return "\n".join(lines)
