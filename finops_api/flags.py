"""Resolving a feature flag, in three steps, none of which may raise.

Order, from ADR-0017: the `feature_flag` table for this tenant, then the
environment default, then the flag's declared default.

Two behaviours matter more than the lookup itself.

An unknown key reads as the conservative default instead of raising. A flag key
is a string, strings get typed wrong, and a mistyped flag must leave a feature
off rather than take the request down with a KeyError.

A failure reading the override table is swallowed for the same reason. The flag
table is a convenience; the API is not allowed to stop serving because the
convenience is unavailable.

The tenant lookup arrives as a callable rather than a repository, because
persistence lands in TASK-P0-010 and this task does not wait for it. TASK-P0-011
passes the real one in.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping

from finops_core.config import Settings
from finops_core.constants import TENANT_FLAG_CACHE_TTL_SECONDS

#: What an unrecognised flag key resolves to. Off, because a typo must not
#: switch something on that nobody decided to switch on.
UNKNOWN_FLAG_DEFAULT = False

FLAG_FIELD_PREFIX = "feature_"

TenantOverrides = Callable[[str], Mapping[str, bool]]
Clock = Callable[[], float]


class FlagResolver:
    """Reads a flag for a tenant, caching the per tenant override briefly."""

    def __init__(
        self,
        settings: Settings,
        overrides: TenantOverrides | None = None,
        ttl_seconds: float = TENANT_FLAG_CACHE_TTL_SECONDS,
        clock: Clock = time.monotonic,
    ) -> None:
        self._settings = settings
        self._overrides = overrides
        self._ttl = ttl_seconds
        self._clock = clock
        self._cache: dict[str, tuple[float, Mapping[str, bool]]] = {}

    def is_enabled(self, key: str, tenant_id: str | None = None) -> bool:
        if tenant_id is not None and self._overrides is not None:
            table = self._tenant_table(tenant_id)
            if key in table:
                return bool(table[key])
        value = getattr(self._settings, f"{FLAG_FIELD_PREFIX}{key}", None)
        if value is None:
            return UNKNOWN_FLAG_DEFAULT
        return bool(value)

    def _tenant_table(self, tenant_id: str) -> Mapping[str, bool]:
        now = self._clock()
        cached = self._cache.get(tenant_id)
        if cached is not None and cached[0] > now:
            return cached[1]
        table: Mapping[str, bool]
        try:
            assert self._overrides is not None
            table = self._overrides(tenant_id)
        except Exception:
            # Cached as empty for the same interval, so an unavailable table is
            # not hammered once per request while it is down.
            table = {}
        self._cache[tenant_id] = (now + self._ttl, table)
        return table
