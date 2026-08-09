"""FSAR 安全层 — Phase 2.

公开接口:
- PermissionState / load_permissions / save_permissions
- RiskEngine / RiskVerdict
- ask_user / ConfirmResponse / ConfirmResult
- AuditEntry / make_entry / append_entry / tail
"""

from src.security.permissions import (
    PermissionState,
    load_permissions,
    save_permissions,
)
from src.security.risk import (
    RiskEngine,
    RiskVerdict,
    SAFE,
    LOW,
    MEDIUM,
    HIGH,
    CRITICAL,
)
from src.security.confirmation import (
    ConfirmResponse,
    ConfirmResult,
    ask_user,
)
from src.security.audit import (
    AuditEntry,
    append_entry,
    make_entry,
    tail,
)

__all__ = [
    "PermissionState", "load_permissions", "save_permissions",
    "RiskEngine", "RiskVerdict", "SAFE", "LOW", "MEDIUM", "HIGH", "CRITICAL",
    "ConfirmResponse", "ConfirmResult", "ask_user",
    "AuditEntry", "append_entry", "make_entry", "tail",
]
