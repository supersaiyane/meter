"""Migration 0030 backfills the provider pair, and the release before it still writes. P10.

P10 spec section 12 item 2: `ProviderName` carried into `ServiceProviderName` and
`HostProviderName`, with an old reader still working. Constraint 12 says old and new task
definitions run against one schema during a rolling deploy, so the release before P10, which
names none of the eight columns 0030 adds, must keep writing after it runs, and a row written
before it must arrive with the pair filled rather than null.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from alembic import command
from sqlalchemy import Engine, text

from finops_ingest.collectors.partitions import ensure_partition
from tests.conftest import alembic_config

pytestmark = pytest.mark.integration

BEFORE_P10 = "0029_report_schedule"
AT = datetime(2026, 8, 24, 6, 0, tzinfo=UTC)
AUG, SEP = date(2026, 8, 1), date(2026, 9, 1)

#: The columns the cost collector wrote before P10, and nothing 0030 added.
OLD_WRITE = text(
    "INSERT INTO cost_focus_daily (tenant_id, ingest_run_id, source_fingerprint, as_of, "
    "collected_at, billing_account_id, sub_account_id, billing_period_start, "
    "billing_period_end, charge_period_start, charge_period_end, provider_name, "
    "service_name, region_id, resource_id, charge_category, billed_cost, effective_cost, "
    "list_cost, contracted_cost, tags) "
    "VALUES (:t, :run, :fingerprint, :at, :at, '111122223333', '111122223333', :period, "
    ":period_end, :period, :period, 'AWS', 'AmazonEC2', 'eu-west-1', :resource, 'Usage', "
    ":cost, :cost, :cost, :cost, '{}'::jsonb)"
)


@pytest.fixture(autouse=True, scope="module")
def _partitions(partition_sandbox: None) -> None:
    """This module writes cost rows into a monthly partition, and gives it back. See conftest."""


def write_as_before(engine: Engine, tenant: UUID) -> None:
    with engine.begin() as connection:
        ensure_partition(connection, "cost_focus_daily", AUG)
        connection.execute(
            OLD_WRITE,
            {
                "t": tenant,
                "run": uuid4(),
                "fingerprint": uuid4().hex,
                "period": AUG,
                "period_end": SEP,
                "resource": f"r-{uuid4().hex[:8]}",
                "cost": Decimal("12.3400"),
                "at": AT,
            },
        )


def test_a_row_from_before_p10_arrives_with_its_provider_pair_and_the_old_writer_still_writes(
    engine: Engine, tenant_id: UUID
) -> None:
    config = alembic_config(engine.url.render_as_string(hide_password=False))
    command.downgrade(config, BEFORE_P10)
    try:
        write_as_before(engine, tenant_id)
    finally:
        command.upgrade(config, "head")

    with engine.connect() as connection:
        before = connection.execute(
            text(
                "SELECT service_provider_name, host_provider_name, billing_currency, invoice_id "
                "FROM cost_focus_daily WHERE tenant_id = :t"
            ),
            {"t": tenant_id},
        ).one()
    assert tuple(before) == ("AWS", "AWS", None, None)

    # The release before P10 is still running somewhere during the deploy, and writes as it did.
    write_as_before(engine, tenant_id)
    with engine.connect() as connection:
        written = connection.execute(
            text("SELECT count(*) FROM cost_focus_daily WHERE tenant_id = :t"), {"t": tenant_id}
        ).scalar_one()
    assert written == 2
