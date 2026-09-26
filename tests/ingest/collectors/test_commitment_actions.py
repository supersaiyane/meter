"""Coverage gaps as findings, over a real database.

FEAT-055, TASK-P1-022. The arithmetic has its own suite against numbers. What this asks is
whether the right coverage rows reach it and whether what lands in `recommendation` is
something a reader can act on.

Two cases carry this file. The latest window per dimension, because an estate with six months
of history holds six rows per dimension and recommending against the oldest would be advising
on a baseline that has since changed. And the lifecycle: next month's coverage row updates the
finding somebody is working on rather than opening a second one beside it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text

from finops_core.config import Settings
from finops_ingest.collectors.commitment_actions import CommitmentActionsCollector
from finops_ingest.registry import CollectorContext

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 26, 6, 0, tzinfo=UTC)

INSERT = text(
    "INSERT INTO commitment_coverage (coverage_id, tenant_id, ingest_run_id, commitment_type, "
    "dimension, dimension_value, window_start, window_end, eligible_spend, covered_spend, "
    "as_of, collected_at) VALUES (:id, :t, :run, :type, :dim, :value, :start, :end, "
    ":eligible, :covered, :at, :at)"
)


@dataclass(frozen=True)
class Unit:
    tenant_id: UUID


def coverage(
    engine: Engine,
    tenant: UUID,
    *,
    eligible: str,
    covered: str,
    start: date = date(2026, 8, 1),
    end: date = date(2026, 8, 31),
    dimension: str = "SERVICE",
    dimension_value: str = "AmazonEC2",
    commitment_type: str = "SAVINGS_PLAN",
) -> None:
    with engine.begin() as connection:
        connection.execute(
            INSERT,
            {
                "id": uuid4(),
                "t": tenant,
                "run": uuid4(),
                "type": commitment_type,
                "dim": dimension,
                "value": dimension_value,
                "start": start,
                "end": end,
                "eligible": Decimal(eligible),
                "covered": Decimal(covered),
                "at": NOW,
            },
        )


def collect(engine: Engine, tenant: UUID, settings: Settings | None) -> int:
    with engine.begin() as connection:
        outcome = CommitmentActionsCollector(clock=lambda: NOW)(
            CollectorContext(
                unit=Unit(tenant_id=tenant),
                connection=connection,
                run_id=uuid4(),
                settings=settings,
            )
        )
    return int(outcome.items_written)


def findings(engine: Engine, tenant: UUID) -> list[tuple[str, Decimal, str, str]]:
    """Every action, keyed by the dimension it is about.

    `commitment_action` rather than `recommendation`, per ADR-0025: a finding derived from a
    payer wide fact is payer wide, and stamping an account on it would have disclosed the
    organization's commitment position to whoever held that account.
    """
    with engine.connect() as connection:
        return [
            (row[0], row[1], row[2], row[3])
            for row in connection.execute(
                text(
                    "SELECT commitment_type || ':' || dimension || ':' || dimension_value, "
                    "estimated_monthly_saving, rationale, severity "
                    "FROM commitment_action WHERE tenant_id = :t ORDER BY 1"
                ),
                {"t": tenant},
            )
        ]


def test_an_uncovered_baseline_becomes_one_finding(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    coverage(engine, tenant_id, eligible="10000", covered="4000")
    assert collect(engine, tenant_id, settings) == 1
    reference, saving, said, severity = findings(engine, tenant_id)[0]
    assert reference == "SAVINGS_PLAN:SERVICE:AmazonEC2"
    assert saving == Decimal("1826.0000") or saving == Decimal("1826.4000")
    # ADR-0016: severity comes from the money, and 1826 a month is over the critical boundary.
    assert severity == "CRITICAL"
    assert "70.0 percent of today's" in said


def test_the_rationale_admits_the_discount_is_configured(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """A reader deciding to commit real money is entitled to know which half of the number is
    an assumption. ADR-0007."""
    coverage(engine, tenant_id, eligible="10000", covered="4000")
    collect(engine, tenant_id, settings)
    _reference, _saving, said, _severity = findings(engine, tenant_id)[0]
    assert "modelled from a configured discount rather than from a quote" in said
    assert "obligates 12 months" in said


def test_only_the_latest_window_per_dimension_is_judged(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """The first case this file exists for. An estate with six months of history holds six rows
    per dimension, and recommending against the oldest would be advising on a baseline that has
    since changed. One finding, from the most recent window."""
    coverage(
        engine,
        tenant_id,
        eligible="10000",
        covered="0",
        start=date(2026, 6, 1),
        end=date(2026, 6, 30),
    )
    coverage(engine, tenant_id, eligible="10000", covered="9000")
    assert collect(engine, tenant_id, settings) == 1
    _reference, _saving, said, _severity = findings(engine, tenant_id)[0]
    # The August window, where ninety percent was already covered, not the June one.
    assert "90.0 percent of eligible" in said
    assert "2026-08-01" in said


def test_two_dimensions_produce_two_findings(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """A commitment covers a class of usage, so two classes are two decisions. Collapsing them
    would hide one behind the other's number."""
    coverage(engine, tenant_id, eligible="10000", covered="0")
    coverage(engine, tenant_id, eligible="8000", covered="0", commitment_type="RESERVED")
    assert collect(engine, tenant_id, settings) == 2
    assert {one[0] for one in findings(engine, tenant_id)} == {
        "SAVINGS_PLAN:SERVICE:AmazonEC2",
        "RESERVED:SERVICE:AmazonEC2",
    }


def test_a_second_run_updates_the_finding_rather_than_opening_another(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """The second case this file exists for. The reference is the dimension, not the window, so
    next month's coverage row updates the finding somebody is working on instead of opening a
    second one beside it and leaving the first to look abandoned."""
    coverage(engine, tenant_id, eligible="10000", covered="0")
    collect(engine, tenant_id, settings)
    coverage(
        engine,
        tenant_id,
        eligible="10000",
        covered="5000",
        start=date(2026, 9, 1),
        end=date(2026, 9, 30),
    )
    collect(engine, tenant_id, settings)

    rows = findings(engine, tenant_id)
    assert len(rows) == 1
    # The newer, smaller gap, so the list a reader works from reflects this month.
    assert "50.0 percent of eligible" in rows[0][2]
    # One row, and its lifecycle survived the update. A finding somebody has accepted is not
    # reopened by next month's coverage arriving, which is the rule `recommendation`'s own
    # upsert follows.
    with engine.connect() as connection:
        lifecycle = connection.execute(
            text("SELECT lifecycle FROM commitment_action WHERE tenant_id = :t"),
            {"t": tenant_id},
        ).scalar_one()
    assert lifecycle == "OPEN"


def test_a_fully_covered_estate_produces_nothing(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """The good outcome. A finding here would ask somebody to act on success."""
    coverage(engine, tenant_id, eligible="10000", covered="10000")
    assert collect(engine, tenant_id, settings) == 0
    assert findings(engine, tenant_id) == []


def test_an_estate_with_no_coverage_rows_produces_nothing(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """Before FEAT-019 has run there is nothing to read, and that is not a failure. A tenant
    whose first ingest has not happened is not a tenant with no commitments."""
    assert collect(engine, tenant_id, settings) == 0


def test_it_refuses_to_run_without_settings(engine: Engine, tenant_id: UUID) -> None:
    """The discount rate is an assumption about a price nobody has been quoted and the term
    decides how long a wrong decision lasts. Defaulting either would put a number nobody chose
    behind advice to commit real money."""
    coverage(engine, tenant_id, eligible="10000", covered="0")
    with pytest.raises(ValueError, match="configuration"):
        collect(engine, tenant_id, None)
