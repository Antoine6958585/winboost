"""Serializers MCP — convertit les types riches WinBoost en dicts JSON-compatibles.

Conventions :
- Les chaines vides deviennent `None` lorsqu'elles representent "absence" (ex: verdict.reason)
- Les enums (RiskLevel) sont serialises en `value` string
- Aucune dependance fastmcp ici (ce module est aussi utilise par le CLI `chat --json`)

Cible : conformite stricte au schema documente sur la commande `winboost chat --json`
+ extension pour les tools MCP (action_to_dict, scan_to_dict, fix_to_dict).
"""

from __future__ import annotations

from typing import Any


def routed_action_to_dict(routed: Any) -> dict[str, Any]:
    """Serialise un `RoutedAction` (action + verdict + score + source) en dict.

    Utilise par :
    - `winboost chat --json` (CLI T066)
    - `winboost mcp` tool `chat` (T070)
    """
    action = routed.action
    verdict = routed.verdict
    return {
        "id": action.id,
        "name": action.name,
        "description": action.description,
        "category": action.category,
        "risk_level": action.risk_level,
        "requires_admin": bool(action.requires_admin),
        "reversible": bool(action.reversible),
        "verdict": {
            "allowed": bool(verdict.allowed),
            "requires_dry_run": bool(verdict.requires_dry_run),
            "requires_confirmation": bool(verdict.requires_confirmation),
            "reason": verdict.reason if verdict.reason else None,
        },
    }


def route_result_to_dict(query: str, result: Any) -> dict[str, Any]:
    """Serialise un `RouteResult` complet en dict JSON-compatible.

    Schema strictement aligne avec `winboost chat --json --help`.
    """
    return {
        "query": query,
        "resolved_by": result.resolved_by,
        "message": result.message,
        "has_actions": bool(result.has_actions),
        "actions": [routed_action_to_dict(r) for r in result.actions],
        "blocked": [routed_action_to_dict(r) for r in result.blocked],
    }


def action_to_dict(action: Any) -> dict[str, Any]:
    """Serialise un `Action` du registry pour le tool `list_actions`.

    Format compact : pas de execute/rollback/preview/keywords (verbeux et
    pas utiles cote consommateur MCP qui veut juste lister/decouvrir).
    """
    return {
        "id": action.id,
        "name": action.name,
        "description": action.description,
        "category": action.category,
        "risk_level": action.risk_level,
        "requires_admin": bool(action.requires_admin),
        "reversible": bool(action.reversible),
    }


def issue_to_dict(issue: Any) -> dict[str, Any]:
    """Serialise un `Issue` (sortie de scan d'un BaseModule) en dict."""
    risk = issue.risk_level
    risk_value = risk.value if hasattr(risk, "value") else str(risk)
    return {
        "id": issue.id,
        "description": issue.description,
        "risk_level": risk_value,
        "auto_fixable": bool(getattr(issue, "auto_fixable", False)),
        "metadata": dict(getattr(issue, "metadata", {}) or {}),
    }


def scan_result_to_dict(result: Any) -> dict[str, Any]:
    """Serialise un `ScanResult` (sortie de Engine.scan_module) en dict."""
    return {
        "module_name": result.module_name,
        "summary": getattr(result, "summary", ""),
        "issue_count": getattr(result, "issue_count", len(result.issues)),
        "has_issues": bool(getattr(result, "has_issues", len(result.issues) > 0)),
        "issues": [issue_to_dict(i) for i in result.issues],
    }


def scan_all_to_dict(results: dict[str, Any]) -> dict[str, Any]:
    """Serialise un dict de ScanResult (sortie de Engine.scan_all) en payload."""
    modules = {name: scan_result_to_dict(r) for name, r in results.items()}
    total_issues = sum(m["issue_count"] for m in modules.values())
    return {
        "modules": modules,
        "module_count": len(modules),
        "total_issues": total_issues,
    }
