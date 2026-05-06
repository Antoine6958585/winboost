"""WinBoost Core — base_module, engine, config, backup, history, executor."""

from winboost.core.backup import BackupManager
from winboost.core.base_module import BaseModule, FixResult, Issue, RiskLevel, ScanResult
from winboost.core.config import Config
from winboost.core.engine import Engine
from winboost.core.executor import DEFAULT_TIMEOUT_SECONDS, ActionExecutor, ApplyResult
from winboost.core.history import HistoryManager

__all__ = [
    "DEFAULT_TIMEOUT_SECONDS",
    "ActionExecutor",
    "ApplyResult",
    "BackupManager",
    "BaseModule",
    "Config",
    "Engine",
    "FixResult",
    "HistoryManager",
    "Issue",
    "RiskLevel",
    "ScanResult",
]
