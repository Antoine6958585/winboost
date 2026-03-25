"""WinBoost Core — base_module, engine, config, backup, history."""

from winboost.core.backup import BackupManager
from winboost.core.base_module import BaseModule, FixResult, Issue, RiskLevel, ScanResult
from winboost.core.config import Config
from winboost.core.engine import Engine
from winboost.core.history import HistoryManager

__all__ = [
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
