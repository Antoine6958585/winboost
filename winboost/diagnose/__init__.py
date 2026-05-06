"""Module diagnose — diagnostics systemiques rules-based pour WinBoost.

Le module `winboost.diagnose` execute des chaines de checks scriptes (pas IA,
rules-based, fast) sur des themes systeme : bluetooth, gaming, network, audio,
display. Il produit un `DiagnosticReport` listant les anomalies detectees +
un plan de fix actionable pointant vers les actions YAML existantes.

Usage de base :
    from winboost.diagnose.runner import DiagnosticRunner

    runner = DiagnosticRunner()
    report = runner.run_from_query("ma manette bluetooth bug dans rocket league")
    print(report.summary)
    for step in report.recommended_fix_plan:
        print(step)

Les diagnostics sont volontairement rapides (< 5s) car ils servent de couche
"premier reflexe" avant le chat IA ou l'execution d'actions YAML.
"""

from __future__ import annotations

from winboost.diagnose.checks import Check, CheckResult, Severity
from winboost.diagnose.runner import DiagnosticReport, DiagnosticRunner

__all__ = [
    "Check",
    "CheckResult",
    "DiagnosticReport",
    "DiagnosticRunner",
    "Severity",
]
