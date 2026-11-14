"""Setting `role_health` for one account, every run.

Onboarding is the step that fails silently. A StackSet that never arrived
produces no error anywhere until a collector returns nothing, and nothing
renders as zero. Writing a health state on every run is what turns that into
something visible before anyone trusts a figure.

The state is written even when the check fails, which is the point. A collector
that only writes on success leaves the previous run's HEALTHY in place while the
account is broken, which is worse than never having written it at all.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text

from finops_core.domain.account import RoleHealth
from finops_core.errors import SchemaDrift
from finops_ingest.registry import CollectorContext, CollectorOutcome

COLLECTOR = "account_health"

Clock = Callable[[], datetime]


def _system_clock() -> datetime:
    return datetime.now(UTC)


class AccountHealthCollector:
    """Checks one account's collector role and records the answer."""

    def __init__(self, health_check: Any, clock: Clock = _system_clock) -> None:
        self._check = health_check
        self._clock = clock

    def __call__(self, context: CollectorContext) -> CollectorOutcome:
        unit = context.unit
        if unit.account is None or unit.region is None:
            raise SchemaDrift(
                scope_key=unit.scope_key,
                collector=COLLECTOR,
                detail="an account health unit arrived without an account or a region",
            )

        health = self._check.check(unit.account, unit.region)
        context.connection.execute(
            text(
                "UPDATE cloud_account SET role_health = :health, "
                "role_health_checked_at = :checked, role_health_error = :error, "
                "collected_at = :collected WHERE tenant_id = :tenant AND provider = :provider "
                "AND account_id = :account"
            ),
            {
                "health": RoleHealth(health.health).value,
                "checked": health.collected_at,
                # Empty string would read as "checked and fine" in a report. The
                # absence of an error is a NULL.
                "error": health.error or None,
                "collected": health.collected_at,
                "tenant": unit.tenant_id,
                "provider": unit.account.provider.value,
                "account": unit.account.account_id,
            },
        )
        return CollectorOutcome(items_written=1)
