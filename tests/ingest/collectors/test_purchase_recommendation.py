"""AWS's purchase advice, one row per type and service. TASK-P14-006, FEAT-089.

The collector asks in the tenant's own policy's terms, writes AWS's answer for each Savings Plans
type and each configured service, and writes a service that failed as a row with its typed cause
beside the ones that answered. Only a run where every read failed fails, and then the last good
rows stay.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text

from finops_core.domain.commitments import (
    ALL_UPFRONT,
    NO_UPFRONT,
    CommitmentPolicy,
    PurchaseRecommendation,
)
from finops_core.errors import CollectionError, Misconfigured, Throttled
from finops_fakes.commitments import FakePurchaseRecommendations
from finops_ingest.collectors.purchase_recommendation import PurchaseRecommendationCollector
from finops_ingest.commitment_policy import install_default_policy
from finops_ingest.dispatcher import WorkUnit
from finops_ingest.registry import CollectorContext, CollectorOutcome

pytestmark = pytest.mark.integration

NOW = datetime(2026, 10, 13, 6, tzinfo=UTC)
EC2_NAME = "Amazon Elastic Compute Cloud - Compute"
RDS_NAME = "Amazon Relational Database Service"
REDSHIFT_NAME = "Amazon Redshift"
SERVICES = (EC2_NAME, RDS_NAME, REDSHIFT_NAME)


@dataclass
class Spy:
    """The fake advice, recording each read's policy and failing what a test names."""

    tenant: UUID
    failing: dict[str, CollectionError] = field(default_factory=dict)
    policies: list[CommitmentPolicy] = field(default_factory=list)

    def savings_plans(self, program: str, policy: CommitmentPolicy) -> PurchaseRecommendation:
        return self._ask("savings_plans", program, policy)

    def reservations(self, service: str, policy: CommitmentPolicy) -> PurchaseRecommendation:
        return self._ask("reservations", service, policy)

    def _ask(self, how: str, program: str, policy: CommitmentPolicy) -> PurchaseRecommendation:
        self.policies.append(policy)
        failure = self.failing.get(program) or self.failing.get("*")
        if failure is not None:
            raise failure
        fake = FakePurchaseRecommendations(self.tenant, at=NOW)
        answer: PurchaseRecommendation = getattr(fake, how)(program, policy)
        return answer


def refused(program: str, cause: type[CollectionError] = Misconfigured) -> CollectionError:
    return cause(scope_key=program, collector="purchase_recommendation", detail="refused")


def run(
    engine: Engine, spy: Spy, *, services: tuple[str, ...] = SERVICES, run_id: UUID | None = None
) -> CollectorOutcome:
    work = WorkUnit(
        tenant_id=spy.tenant,
        collector="purchase_recommendation",
        window_start=NOW - timedelta(days=1),
        window_end=NOW,
    )
    collector = PurchaseRecommendationCollector(spy, services=services, clock=lambda: NOW)
    with engine.begin() as connection:
        return collector(
            CollectorContext(unit=work, connection=connection, run_id=run_id or uuid4())
        )


def rows(engine: Engine, tenant: UUID) -> dict[str, dict[str, Any]]:
    with engine.connect() as connection:
        found = connection.execute(
            text(
                "SELECT kind, program, term_years, payment_option, recommended, hourly_commitment, "
                "units, estimated_monthly_savings, upfront_cost, failure_cause "
                "FROM purchase_recommendation WHERE tenant_id = :t"
            ),
            {"t": tenant},
        ).mappings()
        return {row["program"]: dict(row) for row in found}


def test_every_type_and_service_is_one_row(engine: Engine, tenant_id: UUID) -> None:
    outcome = run(engine, Spy(tenant_id))
    found = rows(engine, tenant_id)
    assert set(found) == {"Compute", "EC2Instance", *SERVICES}
    assert outcome.items_written == 5
    compute = found["Compute"]
    assert (compute["kind"], compute["recommended"], compute["hourly_commitment"]) == (
        "savings_plan",
        True,
        Decimal("0.8500000000"),
    )
    assert (found[EC2_NAME]["units"], found[RDS_NAME]["units"]) == (Decimal(2), Decimal(1))
    # AWS looked and advises buying nothing: an answer, written as one.
    assert (found["EC2Instance"]["recommended"], found[REDSHIFT_NAME]["recommended"]) == (
        False,
        False,
    )
    assert all(row["failure_cause"] is None for row in found.values())


def test_a_tenant_without_a_policy_is_asked_in_the_cautious_default(
    engine: Engine, tenant_id: UUID
) -> None:
    spy = Spy(tenant_id)
    run(engine, spy)
    assert {(one.term_years, one.payment_option) for one in spy.policies} == {(1, NO_UPFRONT)}
    assert rows(engine, tenant_id)["Compute"]["upfront_cost"] == Decimal(0)


def test_the_tenants_own_policy_is_the_question_asked(engine: Engine, tenant_id: UUID) -> None:
    with engine.begin() as connection:
        install_default_policy(connection, tenant_id, updated_by="test")
        connection.execute(
            text(
                "UPDATE commitment_policy SET term_years = 3, payment_option = :pay "
                "WHERE tenant_id = :t"
            ),
            {"t": tenant_id, "pay": ALL_UPFRONT},
        )
    spy = Spy(tenant_id)
    run(engine, spy)
    assert {(one.term_years, one.payment_option) for one in spy.policies} == {(3, ALL_UPFRONT)}
    compute = rows(engine, tenant_id)["Compute"]
    assert (compute["term_years"], compute["payment_option"]) == (3, ALL_UPFRONT)
    assert compute["upfront_cost"] == Decimal("0.850") * 8760 * 3


def test_a_service_that_fails_is_a_row_with_its_cause_beside_the_others(
    engine: Engine, tenant_id: UUID
) -> None:
    outcome = run(engine, Spy(tenant_id, failing={REDSHIFT_NAME: refused(REDSHIFT_NAME)}))
    found = rows(engine, tenant_id)
    redshift = found[REDSHIFT_NAME]
    assert redshift["failure_cause"] == "Misconfigured"
    assert (redshift["recommended"], redshift["estimated_monthly_savings"]) == (None, None)
    assert found["Compute"]["failure_cause"] is None
    assert outcome.items_written == 4


def test_every_read_failing_fails_the_run_and_keeps_the_last_good_rows(
    engine: Engine, tenant_id: UUID
) -> None:
    run(engine, Spy(tenant_id))
    before = rows(engine, tenant_id)
    with pytest.raises(Throttled):
        run(engine, Spy(tenant_id, failing={"*": refused("all", Throttled)}))
    assert rows(engine, tenant_id) == before


def test_a_service_no_longer_named_leaves(engine: Engine, tenant_id: UUID) -> None:
    run(engine, Spy(tenant_id))
    outcome = run(engine, Spy(tenant_id), services=(EC2_NAME, RDS_NAME))
    assert REDSHIFT_NAME not in rows(engine, tenant_id)
    assert outcome.items_removed == 1


def test_a_run_without_its_ledger_id_is_refused(engine: Engine, tenant_id: UUID) -> None:
    work = WorkUnit(
        tenant_id=tenant_id,
        collector="purchase_recommendation",
        window_start=NOW - timedelta(days=1),
        window_end=NOW,
    )
    collector = PurchaseRecommendationCollector(Spy(tenant_id), services=SERVICES)
    with engine.begin() as connection, pytest.raises(ValueError, match="run id"):
        collector(CollectorContext(unit=work, connection=connection, run_id=None))
