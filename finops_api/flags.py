"""The feature flag resolver, which lives in `finops_core.flags` since TASK-P12-004.

Kept as a name the API's callers already import, so moving the one implementation below the API,
where the dispatcher can reach it, changed no import.
"""

from finops_core.flags import (
    FLAG_FIELD_PREFIX,
    UNKNOWN_FLAG_DEFAULT,
    FlagResolver,
    TenantOverrides,
)

__all__ = ["FLAG_FIELD_PREFIX", "UNKNOWN_FLAG_DEFAULT", "FlagResolver", "TenantOverrides"]
