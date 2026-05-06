"""Shared utilities — Windows API wrappers, logging, admin helpers."""

from winboost.utils.admin import (
    AdminRequiredError,
    is_admin,
    relaunch_as_admin,
    require_admin,
)

__all__ = [
    "AdminRequiredError",
    "is_admin",
    "relaunch_as_admin",
    "require_admin",
]
