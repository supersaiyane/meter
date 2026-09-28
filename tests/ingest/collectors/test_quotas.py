"""Every quota in a slice, over a real database.

FEAT-033 and FEAT-034. The entity's rules have their own suite in `tests/core/test_quota.py`,
the database's in `tests/db/test_p5_constraints.py`, and the reading's in
`tests/providers/aws/test_quotas.py`. What this asks is what actually lands in the three
tables, and three cases carry the file.

**A second run over an unchanged estate leaves the row count unchanged.** The identity index
treats two nulls as equal, so a global quota written by two regional runs is one row. Without
that clause it would be one row per run forever, and a screen would show one account level
limit once per region and add them up.

**A quota that had usage and now has none writes the null.** Keeping the last known figure is
the worse of the two failures, because a stale number is indistinguishable from a current one
and it is the one somebody acts on.

**A request's status moves in place and its history accumulates, keeping its dates.** The
current status can say a request was approved but not when, and FEAT-034 exists for the
increase nobody checked on: a `changed_at` that tracked the clock would answer how long an
increase has been waiting with today, every day.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text

from finops_core.domain.account import AccountKey, Provider
from finops_core.domain.quota import (
    QuotaIncreaseRequest,
    QuotaUsage,
    RequestStatus,
    UsageSource,
)
from finops_core.errors import SchemaDrift
from finops_fakes import fixtures
from finops_fakes.quotas import FakeQuotaSource
from finops_ingest.collectors.quotas import QuotaCollector
from finops_ingest.registry import CollectorContext

pytestmark = pytest.mark.integration

NOW = fixtures.AS_OF
ACCOUNT = "fake-platform-a"
REGION = "us-fake-1"
OTHER_REGION = "eu-fake-1"
KEY = AccountKey(provider=Provider.AWS, account_id=ACCOUNT)
REASON = "AWS publishes no usage metric for this quota"

INSERT_RUN = text(
    "INSERT INTO ingest_run (run_id, tenant_id, collector, scope_key, idempotency_key, "
    "status, as_of_window_start, as_of_window_end) "
    "VALUES (:run, :t, 'quotas', :scope, :key, 'SUCCEEDED', :at, :at)"
)


@dataclass(frozen=True)
class Unit:
    tenant_id: UUID
    account: AccountKey | None = KEY
    region: str | None = REGION

    @property
    def scope_key(self) -> str:
        return f"{self.account}:{self.region}"


class Source:
    """A quota source over whatever the test wants it to return."""

    def __init__(
        self,
        quotas: tuple[QuotaUsage, ...] = (),
        requests: tuple[QuotaIncreaseRequest, ...] = (),
    ) -> None:
        self._quotas = quotas
        self._requests = requests

    def list_quotas(self, _account: AccountKey, _region: str) -> tuple[QuotaUsage, ...]:
        return self._quotas

    def requests(self, _account: AccountKey, _region: str) -> tuple[QuotaIncreaseRequest, ...]:
        return self._requests


def collect(
    engine: Engine,
    tenant: UUID,
    *,
    source: Any = None,
    region: str | None = REGION,
    account: AccountKey | None = KEY,
) -> Any:
    run = uuid4()
    with engine.begin() as connection:
        connection.execute(
            INSERT_RUN,
            {"run": run, "t": tenant, "scope": f"{account}:{region}", "key": str(run), "at": NOW},
        )
        return QuotaCollector(source or FakeQuotaSource(at=NOW), clock=lambda: NOW)(
            CollectorContext(
                unit=Unit(tenant_id=tenant, account=account, region=region),
                connection=connection,
                run_id=run,
                settings=None,
            )
        )


def rows(engine: Engine, tenant: UUID, table: str) -> int:
    with engine.connect() as connection:
        return int(
            connection.execute(
                text(f"SELECT count(*) FROM {table} WHERE tenant_id = :t"),
                {"t": tenant},
            ).scalar_one()
        )


def quota_row(engine: Engine, tenant: UUID, code: str) -> Any:
    with engine.connect() as connection:
        return connection.execute(
            text(
                "SELECT used_value, usage_source, unmeasurable_reason, limit_value, region_id "
                "FROM quota_usage WHERE tenant_id = :t AND quota_code = :q"
            ),
            {"t": tenant, "q": code},
        ).one()


def a_quota(**overrides: Any) -> QuotaUsage:
    values: dict[str, Any] = {
        "account_key": KEY,
        "region_id": REGION,
        "service_code": "ec2",
        "quota_code": "L-1216C47A",
        "quota_name": "Running On-Demand Standard instances",
        "quota_limit": Decimal("320"),
        "used": Decimal("196"),
        "usage_source": UsageSource.AWS_USAGE_METRIC,
        "unmeasurable_reason": None,
        "as_of": NOW,
        "collected_at": NOW,
    }
    values.update(overrides)
    return QuotaUsage(**values)


def a_request(**overrides: Any) -> QuotaIncreaseRequest:
    values: dict[str, Any] = {
        "account_key": KEY,
        "request_id": "request-0001",
        "region_id": REGION,
        "service_code": "ec2",
        "quota_code": "L-1216C47A",
        "quota_name": "Running On-Demand Standard instances",
        "desired_value": Decimal("640"),
        "status": RequestStatus.PENDING,
        "requested_at": NOW - timedelta(days=4),
        "last_updated_at": NOW - timedelta(days=2),
        "as_of": NOW,
        "collected_at": NOW,
    }
    values.update(overrides)
    return QuotaIncreaseRequest(**values)


def unmeasured() -> QuotaUsage:
    return a_quota(used=None, usage_source=UsageSource.NONE, unmeasurable_reason=REASON)


# --- the estate, written whole ------------------------------------------------


def test_the_estate_writes_measured_and_unmeasured_quotas_alike(
    engine: Engine, tenant_id: UUID
) -> None:
    """The ratio is the feature, so both halves have to reach the table."""
    collect(engine, tenant_id)
    with engine.connect() as connection:
        counted = connection.execute(
            text(
                "SELECT usage_source = 'NONE' AS unmeasured, count(*) FROM quota_usage "
                "WHERE tenant_id = :t GROUP BY 1"
            ),
            {"t": tenant_id},
        ).all()
    by_state = {bool(row[0]): int(row[1]) for row in counted}
    assert by_state.get(False, 0) > 0, "no measured quota reached the table"
    assert by_state.get(True, 0) > 0, "no unmeasured quota reached the table"


def test_every_unmeasured_row_carries_a_reason(engine: Engine, tenant_id: UUID) -> None:
    """The constraint enforces it, so this is about the collector passing it through."""
    collect(engine, tenant_id)
    with engine.connect() as connection:
        blank = connection.execute(
            text(
                "SELECT count(*) FROM quota_usage WHERE tenant_id = :t "
                "AND usage_source = 'NONE' AND coalesce(trim(unmeasurable_reason), '') = ''"
            ),
            {"t": tenant_id},
        ).scalar_one()
    assert int(blank) == 0


def test_a_second_run_over_an_unchanged_estate_changes_no_row_count(
    engine: Engine, tenant_id: UUID
) -> None:
    """TASK-P5-004's second acceptance criterion."""
    collect(engine, tenant_id)
    first = rows(engine, tenant_id, "quota_usage")
    collect(engine, tenant_id)
    assert rows(engine, tenant_id, "quota_usage") == first


def test_a_second_region_reuses_the_global_quotas_rather_than_copying_them(
    engine: Engine, tenant_id: UUID
) -> None:
    """A global quota is one row however many regions report it.

    Without NULLS NOT DISTINCT on the identity index this is where it breaks: two nulls never
    conflict under PostgreSQL's default, so the second region inserts another copy of every
    account level limit and the screen adds them up.
    """
    collect(engine, tenant_id)
    with engine.connect() as connection:
        after_one = connection.execute(
            text("SELECT count(*) FROM quota_usage WHERE tenant_id = :t AND region_id IS NULL"),
            {"t": tenant_id},
        ).scalar_one()
    assert int(after_one) > 0, "the estate has no global quota, so this would prove nothing"

    collect(engine, tenant_id, region=OTHER_REGION)
    with engine.connect() as connection:
        after_two = connection.execute(
            text("SELECT count(*) FROM quota_usage WHERE tenant_id = :t AND region_id IS NULL"),
            {"t": tenant_id},
        ).scalar_one()
    assert int(after_two) == int(after_one)


# --- the figure that goes away -----------------------------------------------


def test_a_quota_that_loses_its_usage_writes_the_null_rather_than_keeping_the_figure(
    engine: Engine, tenant_id: UUID
) -> None:
    """TASK-P5-004's third acceptance criterion, and the important one.

    A stale figure is indistinguishable from a current one and it is the one somebody acts on,
    so an upsert leaving `used_value` alone when the new reading is null would be worse than
    no feature at all.
    """
    collect(engine, tenant_id, source=Source(quotas=(a_quota(),)))
    assert quota_row(engine, tenant_id, "L-1216C47A").used_value == Decimal("196")

    collect(engine, tenant_id, source=Source(quotas=(unmeasured(),)))
    after = quota_row(engine, tenant_id, "L-1216C47A")
    assert after.used_value is None
    assert after.usage_source == "NONE"
    assert after.unmeasurable_reason == REASON


def test_a_quota_that_gains_usage_drops_the_reason_with_it(engine: Engine, tenant_id: UUID) -> None:
    """The other direction, which rots rather than being obviously wrong.

    A sentence explaining why there is no figure, sitting beside a figure, is the row that
    makes a reader distrust every other explanation on the screen.
    """
    collect(engine, tenant_id, source=Source(quotas=(unmeasured(),)))
    collect(engine, tenant_id, source=Source(quotas=(a_quota(),)))
    after = quota_row(engine, tenant_id, "L-1216C47A")
    assert after.used_value == Decimal("196")
    assert after.unmeasurable_reason is None


def test_a_quota_the_provider_stopped_returning_is_removed(engine: Engine, tenant_id: UUID) -> None:
    """A current state table holding a row nothing reports is a limit nobody has."""
    collect(
        engine,
        tenant_id,
        source=Source(quotas=(a_quota(), a_quota(quota_code="L-GONE", quota_name="Withdrawn"))),
    )
    assert rows(engine, tenant_id, "quota_usage") == 2

    outcome = collect(engine, tenant_id, source=Source(quotas=(a_quota(),)))
    assert rows(engine, tenant_id, "quota_usage") == 1
    assert outcome.items_removed == 1


def test_another_account_is_untouched_by_a_retraction(engine: Engine, tenant_id: UUID) -> None:
    """The retraction is scoped to its slice, or one account's run empties another's."""
    other = AccountKey(provider=Provider.AWS, account_id="fake-product-a")
    collect(engine, tenant_id, source=Source(quotas=(a_quota(),)))
    collect(
        engine,
        tenant_id,
        account=other,
        source=Source(quotas=(a_quota(account_key=other, quota_code="L-OTHER"),)),
    )
    assert rows(engine, tenant_id, "quota_usage") == 2

    collect(engine, tenant_id, source=Source(quotas=(a_quota(),)))
    assert rows(engine, tenant_id, "quota_usage") == 2


# --- the requests -------------------------------------------------------------


def test_a_request_is_stored_with_submitted_by_meter_false(engine: Engine, tenant_id: UUID) -> None:
    """Constraint 6 in the row itself. The column can hold nothing else."""
    collect(engine, tenant_id, source=Source(requests=(a_request(),)))
    with engine.connect() as connection:
        submitted = connection.execute(
            text("SELECT submitted_by_meter FROM quota_request WHERE tenant_id = :t"),
            {"t": tenant_id},
        ).scalar_one()
    assert submitted is False


def test_a_requests_status_moves_in_place_and_its_history_accumulates(
    engine: Engine, tenant_id: UUID
) -> None:
    """One request, one row, and the sequence of states it passed through beside it."""
    collect(engine, tenant_id, source=Source(requests=(a_request(),)))
    collect(
        engine,
        tenant_id,
        source=Source(
            requests=(
                a_request(status=RequestStatus.APPROVED, last_updated_at=NOW - timedelta(days=1)),
            )
        ),
    )
    assert rows(engine, tenant_id, "quota_request") == 1
    with engine.connect() as connection:
        status = connection.execute(
            text("SELECT status FROM quota_request WHERE tenant_id = :t"), {"t": tenant_id}
        ).scalar_one()
        history = connection.execute(
            text(
                "SELECT status FROM quota_request_history WHERE tenant_id = :t ORDER BY changed_at"
            ),
            {"t": tenant_id},
        ).scalars()
    assert status == "APPROVED"
    assert list(history) == ["PENDING", "APPROVED"]


def test_a_transition_already_recorded_keeps_its_original_date(
    engine: Engine, tenant_id: UUID
) -> None:
    """Otherwise the day a request was approved walks forward to today, one run at a time.

    That is the specific way this table would become useless while looking full: FEAT-034 is
    about how long an increase has been waiting, and a `changed_at` tracking the clock answers
    that question with today, every day.
    """
    approved_on = NOW - timedelta(days=30)
    for _ in range(2):
        collect(
            engine,
            tenant_id,
            source=Source(
                requests=(
                    a_request(
                        status=RequestStatus.APPROVED,
                        requested_at=approved_on - timedelta(days=8),
                        last_updated_at=approved_on,
                    ),
                )
            ),
        )
    with engine.connect() as connection:
        changed = connection.execute(
            text("SELECT changed_at FROM quota_request_history WHERE tenant_id = :t"),
            {"t": tenant_id},
        ).scalar_one()
    assert changed == approved_on


def test_a_denied_request_is_stored_rather_than_dropped(engine: Engine, tenant_id: UUID) -> None:
    """The status a product is tempted to hide, and the one somebody most needs."""
    collect(engine, tenant_id, source=Source(requests=(a_request(status=RequestStatus.DENIED),)))
    with engine.connect() as connection:
        status = connection.execute(
            text("SELECT status FROM quota_request WHERE tenant_id = :t"), {"t": tenant_id}
        ).scalar_one()
    assert status == "DENIED"


def test_the_estate_tracks_a_request_for_a_quota_it_cannot_measure(
    engine: Engine, tenant_id: UUID
) -> None:
    """Tracking and measuring are independent, which is the whole of TASK-P5-008.

    Asked per account, which is the only grain where the question means anything. The first
    version asked it of the whole tenant and would have passed for the wrong reason: the same
    quota is measurable in `fake-platform-a`, which has Business support, and not in
    `fake-product-a`, which does not, so tenant wide every tracked quota looked measurable
    while the account actually holding the request could measure none of them.
    """
    account = "fake-product-a"
    collect(engine, tenant_id, account=AccountKey(provider=Provider.AWS, account_id=account))
    with engine.connect() as connection:
        tracked = set(
            connection.execute(
                text(
                    "SELECT quota_code FROM quota_request WHERE tenant_id = :t "
                    "AND sub_account_id = :a"
                ),
                {"t": tenant_id, "a": account},
            ).scalars()
        )
        measurable = set(
            connection.execute(
                text(
                    "SELECT quota_code FROM quota_usage WHERE tenant_id = :t "
                    "AND sub_account_id = :a AND usage_source <> 'NONE'"
                ),
                {"t": tenant_id, "a": account},
            ).scalars()
        )
    assert tracked, "the estate tracks no request in this account, so this proves nothing"
    assert tracked - measurable, "every tracked request is for a quota this account measures"


# --- the gap worth reporting --------------------------------------------------


def test_quotas_unpublished_by_the_provider_are_not_recorded_as_errors(
    engine: Engine, tenant_id: UUID
) -> None:
    """A permanent error nobody can act on is how a screen of errors becomes one nobody reads.

    Most quotas in a real estate have no usage metric. That is the provider's limit rather than
    a fault of ours, it is already stated per row, and filing it as a sync error would bury the
    gaps that do have a fix.
    """
    collect(engine, tenant_id, source=Source(quotas=(unmeasured(),)))
    assert rows(engine, tenant_id, "sync_error") == 0


def test_a_missing_support_tier_is_recorded_as_a_named_gap(engine: Engine, tenant_id: UUID) -> None:
    """OPEN-03, somewhere an operator looks rather than only on each row."""
    blocked = a_quota(
        quota_code="L-ADVISOR",
        used=None,
        usage_source=UsageSource.NONE,
        unmeasurable_reason=(
            "Only Trusted Advisor reports usage for this quota, and it could not be read: "
            "NotOptedIn: no plan"
        ),
    )
    collect(engine, tenant_id, source=Source(quotas=(blocked,)))
    with engine.connect() as connection:
        recorded = connection.execute(
            text(
                "SELECT error_type, detail FROM sync_error WHERE tenant_id = :t "
                "AND collector = 'quotas'"
            ),
            {"t": tenant_id},
        ).all()
    assert len(recorded) == 1
    assert recorded[0].error_type == "NotOptedIn"
    assert "Trusted Advisor" in recorded[0].detail


# --- the unit that names no slice --------------------------------------------


def test_a_unit_with_no_region_is_refused_rather_than_defaulted(
    engine: Engine, tenant_id: UUID
) -> None:
    """A default region would collect one region's quotas and file them under every other."""
    with pytest.raises(SchemaDrift):
        collect(engine, tenant_id, region=None, source=Source())
