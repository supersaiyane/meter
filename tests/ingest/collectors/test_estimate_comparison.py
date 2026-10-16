"""Each resource a merged plan created, set against its bill. TASK-P16-007, FEAT-097.

Against PostgreSQL. A created line waits until the resource is seen in its mapped state, is
pending while its thirty days are unbilled, is then judged at list cost with effective cost beside
it, and is restated as the bill is until sixty days after its window. A folder mapped to no state
and a resource never seen are not compared, with the reason, and only the last priced plan of a
merged pull request is read, its creations alone. The database refuses a verdict without its
figures. Retention removes a plan past its window with everything priced, compared and followed
from it.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from finops_core.config import Settings
from finops_ingest.collectors.estimate_comparison import (
    COLLECTOR,
    UNMAPPED,
    UNSEEN,
    EstimateComparisonCollector,
)
from finops_ingest.collectors.partitions import ensure_partition, month_floor
from finops_ingest.collectors.retention import retention_plans
from finops_ingest.dispatcher import WorkUnit
from finops_ingest.plan_records import PlanTarget, record_plan
from finops_ingest.registry import CollectorContext, CollectorOutcome
from finops_query.plan_reading import PlannedChange, ReducedPlan

pytestmark = pytest.mark.integration

MERGED = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)
#: Seen three hours after the merge, so the window is 2026-10-12 up to 2026-11-11.
SEEN = MERGED + timedelta(hours=3)
WINDOW = (date(2026, 10, 12), date(2026, 11, 11))
BILL_READ = datetime(2026, 11, 11, 8, 0, tzinfo=UTC)
JUDGED = datetime(2026, 11, 12, 6, 0, tzinfo=UTC)
REPOSITORY = "acme/infra"
STATE = "s3://acme-state/storage.tfstate"
ADDRESS = "aws_instance.web"
INSTANCE = "i-0123456789abcdef0"

Line = tuple[str, tuple[str, ...], str | None]


@pytest.fixture(autouse=True, scope="module")
def _partitions(partition_sandbox: None) -> None:
    """This module creates partitions, so it gives them back. See conftest."""


def a_plan(
    connection: Any,
    tenant: UUID,
    *,
    lines: Sequence[Line] = ((ADDRESS, ("create",), "73"),),
    head: str = "abc1234",
    pull_request: int = 7,
    folder: str = "storage",
    state: str | None = STATE,
    received: datetime = MERGED - timedelta(hours=1),
) -> UUID:
    """A plan recorded and priced: each line an address, its actions and its monthly figure, or
    None for a line that could not be priced."""
    changes = tuple(
        PlannedChange(address, "aws_instance", actions, "eu-west-1", {}, {})
        for address, actions, _ in lines
    )
    target = PlanTarget(REPOSITORY, pull_request, head, folder)
    found = ReducedPlan("1.2", None, None, changes)
    plan_id = record_plan(connection, tenant, target, found, route="test", now=received)
    values = {"p": plan_id, "t": tenant, "state": state, "at": received}
    connection.execute(
        text(
            "UPDATE terraform_plan SET status = 'PRICED', state_reference = :state "
            "WHERE plan_id = :p"
        ),
        values,
    )
    connection.execute(
        text(
            "INSERT INTO plan_estimate (plan_id, tenant_id, monthly_before, monthly_after, "
            "monthly_change, currency, priced_lines, unpriced_lines, priced_at, as_of, "
            "collected_at) VALUES (:p, :t, 0, 0, 0, 'USD', 0, 0, :at, :at, :at)"
        ),
        values,
    )
    for address, actions, monthly in lines:
        figure = None if monthly is None else Decimal(monthly)
        connection.execute(
            text(
                "INSERT INTO plan_estimate_line (plan_id, tenant_id, address, resource_type, "
                "actions, region, monthly_before, monthly_after, reason) VALUES (:p, :t, "
                ":address, 'aws_instance', :actions, 'eu-west-1', :before, :after, :reason)"
            ),
            {
                **values,
                "address": address,
                "actions": list(actions),
                "before": None if actions == ("create",) else figure,
                "after": figure,
                "reason": "usage based, priced by what it carries" if figure is None else None,
            },
        )
    return plan_id


def pull_request_is(
    connection: Any, tenant: UUID, state: str, *, number: int = 7, at: datetime = MERGED
) -> None:
    connection.execute(
        text(
            "INSERT INTO plan_pull_request (tenant_id, repository, pull_request, state, head_sha, "
            "merged_seen_at, as_of, collected_at) VALUES (:t, :repo, :n, :state, 'abc1234', "
            ":merged, :at, :at) ON CONFLICT (tenant_id, repository, pull_request) DO UPDATE SET "
            "state = EXCLUDED.state, merged_seen_at = EXCLUDED.merged_seen_at"
        ),
        {
            "t": tenant,
            "repo": REPOSITORY,
            "n": number,
            "state": state,
            "merged": at if state == "MERGED" else None,
            "at": at,
        },
    )


def seen(connection: Any, tenant: UUID, *, at: datetime = SEEN) -> None:
    connection.execute(
        text(
            "INSERT INTO resource_management (management_id, tenant_id, ingest_run_id, "
            "sub_account_id, provider_id, address, state_reference, as_of, collected_at) "
            "VALUES (:id, :t, :run, '111111111111', :resource, :address, :state, :at, :at)"
        ),
        {
            "id": uuid4(),
            "t": tenant,
            "run": uuid4(),
            "resource": INSTANCE,
            "address": ADDRESS,
            "state": STATE,
            "at": at,
        },
    )


def billed(connection: Any, tenant: UUID, list_each: str, effective_each: str) -> None:
    """The instance's thirty days in the window, a row a day at the prices given."""
    days = [WINDOW[0] + timedelta(days=offset) for offset in range(30)]
    for month in {month_floor(day) for day in days}:
        ensure_partition(connection, "cost_focus_daily", month)
    for day in days:
        start = datetime.combine(day, time(), tzinfo=UTC)
        connection.execute(
            text(
                "INSERT INTO cost_focus_daily (tenant_id, ingest_run_id, source_fingerprint, "
                "as_of, collected_at, billing_account_id, sub_account_id, billing_period_start, "
                "billing_period_end, charge_period_start, charge_period_end, provider_name, "
                "service_name, region_id, charge_category, billed_cost, effective_cost, "
                "list_cost, resource_id) VALUES (:t, :run, :fingerprint, :read, :read, "
                "'billing-1', '111111111111', :month, :month, :start, :end, 'aws', "
                "'Amazon Elastic Compute Cloud', 'eu-west-1', 'Usage', :effective, :effective, "
                ":list, :resource)"
            ),
            {
                "t": tenant,
                "run": uuid4(),
                "fingerprint": f"{INSTANCE}-{day}",
                "read": BILL_READ,
                "month": month_floor(day),
                "start": start,
                "end": start + timedelta(days=1),
                "effective": Decimal(effective_each),
                "list": Decimal(list_each),
                "resource": INSTANCE,
            },
        )


def compare(engine: Engine, tenant: UUID, at: datetime = JUDGED) -> CollectorOutcome:
    work = WorkUnit(tenant_id=tenant, collector=COLLECTOR, window_start=at, window_end=at)
    with engine.begin() as connection:
        return EstimateComparisonCollector(clock=lambda: at)(
            CollectorContext(unit=work, connection=connection, run_id=uuid4())
        )


def comparisons(engine: Engine, tenant: UUID) -> list[Any]:
    with engine.connect() as connection:
        return list(
            connection.execute(
                text("SELECT * FROM estimate_comparison WHERE tenant_id = :t ORDER BY address"),
                {"t": tenant},
            ).all()
        )


def test_a_created_resource_waits_to_be_seen_then_is_pending_until_its_days_are_billed(
    engine: Engine, tenant_id: UUID
) -> None:
    with engine.begin() as connection:
        a_plan(connection, tenant_id)
        pull_request_is(connection, tenant_id, "MERGED")
    assert compare(engine, tenant_id, MERGED + timedelta(hours=1)).items_written == 0
    assert comparisons(engine, tenant_id) == []

    with engine.begin() as connection:
        seen(connection, tenant_id)
    assert compare(engine, tenant_id, SEEN + timedelta(days=1)).items_written == 1
    [row] = comparisons(engine, tenant_id)
    assert (row.verdict, row.provider_id, row.seen_at) == ("PENDING", INSTANCE, SEEN)
    assert (row.window_start, row.window_end) == WINDOW
    assert (row.estimate_monthly, row.list_monthly, row.reason) == (Decimal("73"), None, None)


def test_once_its_thirty_days_are_billed_list_cost_decides_with_effective_cost_beside(
    engine: Engine, tenant_id: UUID
) -> None:
    with engine.begin() as connection:
        a_plan(connection, tenant_id)
        pull_request_is(connection, tenant_id, "MERGED")
        seen(connection, tenant_id)
        billed(connection, tenant_id, list_each="2.64", effective_each="1.92")

    assert compare(engine, tenant_id).items_written == 1
    [row] = comparisons(engine, tenant_id)
    assert (row.verdict, row.list_monthly, row.effective_monthly, row.variance_percent) == (
        "WITHIN",
        Decimal("80.3"),
        Decimal("58.4"),
        Decimal("10.0"),
    )
    assert (row.as_of, row.collected_at, row.judged_at) == (BILL_READ, JUDGED, JUDGED)


def test_a_restated_bill_restates_the_verdict_until_sixty_days_after_its_window(
    engine: Engine, tenant_id: UUID
) -> None:
    with engine.begin() as connection:
        a_plan(connection, tenant_id)
        pull_request_is(connection, tenant_id, "MERGED")
        seen(connection, tenant_id)
        billed(connection, tenant_id, list_each="2.64", effective_each="1.92")
    compare(engine, tenant_id)

    restate = text("UPDATE cost_focus_daily SET list_cost = :each WHERE tenant_id = :t")
    with engine.begin() as connection:
        connection.execute(restate, {"each": Decimal("3.50"), "t": tenant_id})
    assert compare(engine, tenant_id, JUDGED + timedelta(days=10)).items_written == 1
    assert comparisons(engine, tenant_id)[0].verdict == "ABOVE"

    with engine.begin() as connection:
        connection.execute(restate, {"each": Decimal("2.64"), "t": tenant_id})
    settled = datetime.combine(WINDOW[1] + timedelta(days=61), time(), tzinfo=UTC)
    assert compare(engine, tenant_id, settled).items_written == 0
    assert comparisons(engine, tenant_id)[0].verdict == "ABOVE"


def test_an_unmapped_folder_and_a_resource_never_seen_are_not_compared_and_say_why(
    engine: Engine, tenant_id: UUID
) -> None:
    unmapped: Sequence[Line] = (("aws_instance.a", ("create",), "10"),)
    with engine.begin() as connection:
        a_plan(connection, tenant_id, folder="network", state=None, lines=unmapped)
        a_plan(connection, tenant_id)
        pull_request_is(connection, tenant_id, "MERGED")

    assert compare(engine, tenant_id, MERGED + timedelta(days=60)).items_written == 1
    assert [(row.address, row.reason) for row in comparisons(engine, tenant_id)] == [
        ("aws_instance.a", UNMAPPED)
    ]

    assert compare(engine, tenant_id, MERGED + timedelta(days=61)).items_written == 1
    found = comparisons(engine, tenant_id)
    assert [(row.address, row.verdict, row.reason) for row in found] == [
        ("aws_instance.a", "NOT_COMPARED", UNMAPPED),
        (ADDRESS, "NOT_COMPARED", UNSEEN),
    ]
    assert all(row.list_monthly is None and row.window_start is None for row in found)


def test_only_the_last_priced_plan_of_a_merged_pull_request_and_its_creations_are_compared(
    engine: Engine, tenant_id: UUID
) -> None:
    newest: Sequence[Line] = (
        (ADDRESS, ("create",), "73"),
        ("aws_instance.changed", ("update",), "20"),
        ("aws_instance.replaced", ("delete", "create"), "30"),
        ("aws_instance.unpriced", ("create",), None),
    )
    with engine.begin() as connection:
        a_plan(
            connection,
            tenant_id,
            state=None,
            lines=(("aws_instance.older", ("create",), "5"),),
            received=MERGED - timedelta(hours=2),
        )
        a_plan(connection, tenant_id, head="def5678", state=None, lines=newest)
        pull_request_is(connection, tenant_id, "OPEN")
    assert compare(engine, tenant_id).items_written == 0

    with engine.begin() as connection:
        pull_request_is(connection, tenant_id, "MERGED")
    compare(engine, tenant_id)
    assert [row.address for row in comparisons(engine, tenant_id)] == [ADDRESS]


def a_comparison(connection: Any, tenant: UUID, plan_id: UUID, **changed: Any) -> None:
    row = {
        "plan": plan_id,
        "address": ADDRESS,
        "t": tenant,
        "provider": None,
        "seen": None,
        "start": None,
        "end": None,
        "list": None,
        "effective": None,
        "variance": None,
        "verdict": "NOT_COMPARED",
        "reason": UNSEEN,
        "at": JUDGED,
        **changed,
    }
    connection.execute(
        text(
            "INSERT INTO estimate_comparison (plan_id, address, tenant_id, resource_type, "
            "provider_id, seen_at, window_start, window_end, estimate_monthly, list_monthly, "
            "effective_monthly, variance_percent, verdict, reason, judged_at, as_of, "
            "collected_at) VALUES (:plan, :address, :t, 'aws_instance', :provider, :seen, "
            ":start, :end, 73, :list, :effective, :variance, :verdict, :reason, :at, :at, :at)"
        ),
        row,
    )


@pytest.mark.parametrize(
    ("changed", "constraint"),
    [
        ({"verdict": "WITHIN", "reason": None}, "judged_has_figures"),
        ({"reason": None}, "not_compared_says_why"),
        ({"list": Decimal(80), "effective": Decimal(58), "variance": Decimal(9)}, "unjudged"),
        ({"verdict": "PENDING", "reason": None}, "pending_is_seen"),
        ({"start": WINDOW[1], "end": WINDOW[0]}, "window"),
        ({"verdict": "RIGHT"}, "verdict"),
    ],
)
def test_the_database_refuses_a_verdict_without_its_facts(
    engine: Engine, tenant_id: UUID, changed: dict[str, Any], constraint: str
) -> None:
    with engine.begin() as connection:
        plan_id = a_plan(connection, tenant_id)
    refused = pytest.raises(IntegrityError, match=f"ck_estimate_comparison__{constraint}")
    with refused, engine.begin() as connection:
        a_comparison(connection, tenant_id, plan_id, **changed)
    with engine.begin() as connection:
        a_comparison(connection, tenant_id, plan_id)


def test_a_plan_past_its_window_goes_with_everything_from_it_and_a_newer_one_stays(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    now = datetime(2027, 12, 1, tzinfo=UTC)
    kept_for = timedelta(days=settings.retention_plan_days)
    old_at, new_at = now - kept_for - timedelta(days=1), now - kept_for + timedelta(days=1)
    with engine.begin() as connection:
        old = a_plan(connection, tenant_id, received=old_at)
        a_comparison(connection, tenant_id, old)
        pull_request_is(connection, tenant_id, "MERGED", at=old_at)
        new = a_plan(connection, tenant_id, pull_request=8, received=new_at)
        a_comparison(connection, tenant_id, new)
        pull_request_is(connection, tenant_id, "MERGED", number=8, at=new_at)

    work = WorkUnit(
        tenant_id=tenant_id, collector="retention_plans", window_start=now, window_end=now
    )
    with engine.begin() as connection:
        outcome = retention_plans(
            CollectorContext(unit=work, connection=connection, settings=settings),
            clock=lambda: now,
        )

    # The plan, its change, estimate, line and comparison, and its pull request's state.
    assert outcome.items_written == 6
    with engine.connect() as connection:
        for table in ("terraform_plan", "planned_change", "plan_estimate", "plan_estimate_line"):
            plans = connection.execute(
                text(f"SELECT plan_id FROM {table} WHERE tenant_id = :t"), {"t": tenant_id}
            ).scalars()
            assert set(plans) == {new}, table
        numbers = connection.execute(
            text("SELECT pull_request FROM plan_pull_request WHERE tenant_id = :t"),
            {"t": tenant_id},
        ).scalars()
        assert list(numbers) == [8]
    assert [row.plan_id for row in comparisons(engine, tenant_id)] == [new]
