"""Engine — orchestrateur central WinBoost."""

from __future__ import annotations

import importlib
import pkgutil
from typing import TYPE_CHECKING

from winboost.core.base_module import BaseModule, FixResult, ScanResult
from winboost.core.config import Config

if TYPE_CHECKING:
    pass


class Engine:
    """Charge les modules et orchestre scan/fix."""

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or Config()
        self._modules: dict[str, BaseModule] = {}

    def discover_modules(self) -> None:
        """Decouvre et charge dynamiquement tous les modules dans winboost.modules."""
        import winboost.modules as modules_pkg

        enabled = self.config.modules_enabled

        for _importer, modname, _ispkg in pkgutil.iter_modules(modules_pkg.__path__):
            if modname.startswith("_"):
                continue
            try:
                module = importlib.import_module(f"winboost.modules.{modname}")
                # Cherche une classe qui herite de BaseModule
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (
                        isinstance(attr, type)
                        and issubclass(attr, BaseModule)
                        and attr is not BaseModule
                    ):
                        instance = attr()
                        if instance.name in enabled:
                            self._modules[instance.name] = instance
            except Exception:
                # Module invalide — on skip silencieusement
                continue

    def register_module(self, module: BaseModule) -> None:
        """Enregistre un module manuellement (utile pour les tests)."""
        self._modules[module.name] = module

    @property
    def modules(self) -> dict[str, BaseModule]:
        return self._modules

    def list_modules(self) -> list[str]:
        """Retourne la liste des noms de modules charges."""
        return list(self._modules.keys())

    def get_module(self, name: str) -> BaseModule | None:
        """Recupere un module par son nom."""
        return self._modules.get(name)

    def scan_all(self) -> dict[str, ScanResult]:
        """Lance le scan sur tous les modules charges."""
        results: dict[str, ScanResult] = {}
        for name, module in self._modules.items():
            results[name] = module.scan()
        return results

    def scan_module(self, name: str) -> ScanResult:
        """Lance le scan sur un module specifique."""
        module = self._modules.get(name)
        if module is None:
            raise ValueError(f"Module inconnu : '{name}'. Disponibles : {self.list_modules()}")
        return module.scan()

    def fix_module(self, name: str, scan_result: ScanResult) -> FixResult:
        """Applique les corrections d'un module."""
        module = self._modules.get(name)
        if module is None:
            raise ValueError(f"Module inconnu : '{name}'.")
        return module.fix(scan_result)

    def preview_module(self, name: str, scan_result: ScanResult) -> str:
        """Retourne la preview des corrections d'un module."""
        module = self._modules.get(name)
        if module is None:
            raise ValueError(f"Module inconnu : '{name}'.")
        return module.preview(scan_result)
