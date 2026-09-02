"""Writing role_health every run, including the runs that fail.

A collector that only writes on success leaves the previous run's HEALTHY in
place while the account is broken. That is worse than never having written it:
the screen says the account is fine, with a timestamp, and the timestamp is what
makes it believable.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text

from finops_core.domain.account import AccountHealth, AccountKey, Provider, RoleHealth
from finops_core.errors import SchemaDrift
from finops_ingest.collectors.account_health import AccountHealthCollector
from finops_ingest.dispatcher import WorkUnit
from finops_ingest.registry import CollectorContext

AT = datetime(2026, 8, 24, 6, 0, tzinfo=UTC)
REGION = "eu-west-1"
ACCOUNT = AccountKey(provider=Provider.AWS, account_id="111122223333")

pytestmark = pytest.mark.integration


class StubHealthCheck:
    def __init__(self, health: RoleHealth, error: str = "") -> None:
        self._health = health
        self._error = error

    def check(self, account: AccountKey, _region: str) -> AccountHealth:
        return AccountHealth(
            key=account, health=self._health, error=self._error, as_of=AT, collected_at=AT
        )


def seed_account(engine: Engine, tenant: UUID) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO cloud_account (account_pk, tenant_id, provider, account_id, "
                "name, status, as_of, collected_at) VALUES "
                "(:pk, :tenant, 'aws', :account, 'live', 'ACTIVE', :at, :at)"
            ),
            {"pk": uuid4(), "tenant": tenant, "account": ACCOUNT.account_id, "at": AT},
        )


def unit_for(
    tenant: UUID, account: AccountKey | None = ACCOUNT, region: str | None = REGION
) -> WorkUnit:
    return WorkUnit(
        tenant_id=tenant,
        collector="account_health",
        window_start=AT,
        window_end=AT,
        account=account,
        region=region,
    )


def run(engine: Engine, tenant: UUID, check: StubHealthCheck, unit: WorkUnit | None = None) -> int:
    with engine.begin() as connection:
        outcome = AccountHealthCollector(check, clock=lambda: AT)(
            CollectorContext(unit=unit or unit_for(tenant), connection=connection)
        )
    return outcome.items_written


def stored(engine: Engine, tenant: UUID) -> dict[str, object]:
    with engine.connect() as connection:
        row = (
            connection.execute(
                text("SELECT * FROM cloud_account WHERE tenant_id = :t"), {"t": tenant}
            )
            .mappings()
            .one()
        )
    return dict(row)


def test_role_health_is_written(engine: Engine, tenant_id: UUID) -> None:
    seed_account(engine, tenant_id)
    assert run(engine, tenant_id, StubHealthCheck(RoleHealth.HEALTHY)) == 1
    row = stored(engine, tenant_id)
    assert row["role_health"] == "HEALTHY"
    assert row["role_health_checked_at"] == AT


def test_a_healthy_account_records_no_error(engine: Engine, tenant_id: UUID) -> None:
    """A blank string would read as checked and fine in a report. Absence is NULL."""
    seed_account(engine, tenant_id)
    run(engine, tenant_id, StubHealthCheck(RoleHealth.HEALTHY))
    assert stored(engine, tenant_id)["role_health_error"] is None


@pytest.mark.parametrize(
    "health",
    [
        RoleHealth.ACCESS_DENIED,
        RoleHealth.NOT_DEPLOYED,
        RoleHealth.THROTTLED,
        RoleHealth.UNKNOWN,
    ],
)
def test_every_state_the_database_admits_round_trips(
    engine: Engine, tenant_id: UUID, health: RoleHealth
) -> None:
    seed_account(engine, tenant_id)
    run(engine, tenant_id, StubHealthCheck(health, error="something to act on"))
    assert stored(engine, tenant_id)["role_health"] == health.value


def test_a_failing_check_overwrites_a_previous_healthy(engine: Engine, tenant_id: UUID) -> None:
    """Otherwise the screen keeps saying fine, with a fresh timestamp to prove it."""
    seed_account(engine, tenant_id)
    run(engine, tenant_id, StubHealthCheck(RoleHealth.HEALTHY))
    run(engine, tenant_id, StubHealthCheck(RoleHealth.ACCESS_DENIED, error="policy is wrong"))
    row = stored(engine, tenant_id)
    assert row["role_health"] == "ACCESS_DENIED"
    assert "policy is wrong" in str(row["role_health_error"])


def test_a_recovery_clears_the_previous_error(engine: Engine, tenant_id: UUID) -> None:
    seed_account(engine, tenant_id)
    run(engine, tenant_id, StubHealthCheck(RoleHealth.NOT_DEPLOYED, error="never arrived"))
    run(engine, tenant_id, StubHealthCheck(RoleHealth.HEALTHY))
    row = stored(engine, tenant_id)
    assert row["role_health"] == "HEALTHY"
    assert row["role_health_error"] is None


def test_the_error_is_stored_so_nobody_has_to_read_logs(engine: Engine, tenant_id: UUID) -> None:
    seed_account(engine, tenant_id)
    run(
        engine,
        tenant_id,
        StubHealthCheck(RoleHealth.UNKNOWN, error="check the StackSet, then the trust policy"),
    )
    assert "StackSet" in str(stored(engine, tenant_id)["role_health_error"])


def test_a_unit_without_an_account_is_schema_drift(engine: Engine, tenant_id: UUID) -> None:
    """A dispatch bug must be loud, not quietly skipped."""
    seed_account(engine, tenant_id)
    with pytest.raises(SchemaDrift):
        run(
            engine,
            tenant_id,
            StubHealthCheck(RoleHealth.HEALTHY),
            unit=unit_for(tenant_id, account=None, region=None),
        )


def test_one_tenant_health_write_does_not_touch_another(engine: Engine, tenant_id: UUID) -> None:
    other = uuid4()
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO tenant (tenant_id, name) VALUES (:id, :name)"),
            {"id": other, "name": f"tenant-{other}"},
        )
    seed_account(engine, tenant_id)
    seed_account(engine, other)
    run(engine, tenant_id, StubHealthCheck(RoleHealth.ACCESS_DENIED, error="denied"))
    assert stored(engine, other)["role_health"] == "UNKNOWN"
