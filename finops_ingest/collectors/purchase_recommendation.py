"""AWS's purchase recommendations, read daily in the tenant's policy's terms. FEAT-089.

TASK-P14-006, P14 spec sections 5.1 and 7, OPEN-35. One organization wide unit reads AWS's
recommendation for each Savings Plans type and each reserved service, in the term and payment
option the tenant's policy names, so AWS's answer and Meter's own plan are about the same purchase.

**Partial failure is first class, constraint 5.** Each type and service is its own read. One that
fails is written as a row with its typed cause and no figures, beside the ones that answered, so a
service name Cost Explorer refuses costs that service and nothing else. Only when every read fails
does the run fail, with the first cause, and then nothing is written or removed.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from functools import partial
from typing import Any, Final

from sqlalchemy import text

from finops_core.domain.commitments import RESERVATION, SAVINGS_PLAN, PurchaseRecommendation
from finops_core.errors import CollectionError
from finops_core.ports.commitment import PurchaseRecommendations
from finops_ingest.commitment_policy import policy_for
from finops_ingest.registry import CollectorContext, CollectorOutcome

COLLECTOR = "purchase_recommendation"

#: The Savings Plans types a plan is drafted for, OPEN-35: the two that cover EC2.
SAVINGS_PLANS_PROGRAMS: Final = ("Compute", "EC2Instance")

UPSERT = text(
    "INSERT INTO purchase_recommendation (tenant_id, ingest_run_id, kind, program, term_years, "
    "payment_option, lookback_days, recommended, hourly_commitment, units, "
    "estimated_monthly_savings, estimated_savings_percent, upfront_cost, currency, "
    "failure_cause, failure_detail, as_of, collected_at) VALUES (:tenant, :run, :kind, :program, "
    ":term, :payment, :lookback, :recommended, :hourly, :units, :savings, :percent, :upfront, "
    ":currency, :cause, :detail, :as_of, :collected_at) "
    "ON CONFLICT ON CONSTRAINT pk_purchase_recommendation DO UPDATE SET "
    "ingest_run_id = EXCLUDED.ingest_run_id, term_years = EXCLUDED.term_years, "
    "payment_option = EXCLUDED.payment_option, lookback_days = EXCLUDED.lookback_days, "
    "recommended = EXCLUDED.recommended, hourly_commitment = EXCLUDED.hourly_commitment, "
    "units = EXCLUDED.units, estimated_monthly_savings = EXCLUDED.estimated_monthly_savings, "
    "estimated_savings_percent = EXCLUDED.estimated_savings_percent, "
    "upfront_cost = EXCLUDED.upfront_cost, currency = EXCLUDED.currency, "
    "failure_cause = EXCLUDED.failure_cause, failure_detail = EXCLUDED.failure_detail, "
    "as_of = EXCLUDED.as_of, collected_at = EXCLUDED.collected_at"
)

#: A type or service no longer asked about leaves; the tenant keeps every row this run wrote.
RETRACT = text(
    "DELETE FROM purchase_recommendation WHERE tenant_id = :tenant AND ingest_run_id <> :run"
)

Clock = Callable[[], datetime]


def _system_clock() -> datetime:
    return datetime.now(UTC)


class PurchaseRecommendationCollector:
    """Every Savings Plans type and reserved service AWS is asked about, one row each."""

    def __init__(
        self,
        recommendations: PurchaseRecommendations,
        *,
        services: Sequence[str],
        clock: Clock = _system_clock,
    ) -> None:
        self._recommendations = recommendations
        self._services = tuple(services)
        self._clock = clock

    def __call__(self, context: CollectorContext) -> CollectorOutcome:
        if context.run_id is None:
            raise ValueError("purchase_recommendation needs the run id from the ledger's claim")
        tenant = context.unit.tenant_id
        policy = policy_for(context.connection, tenant)
        asked: Sequence[tuple[str, str, Callable[[], PurchaseRecommendation]]] = [
            (SAVINGS_PLAN, program, partial(self._recommendations.savings_plans, program, policy))
            for program in SAVINGS_PLANS_PROGRAMS
        ] + [
            (RESERVATION, service, partial(self._recommendations.reservations, service, policy))
            for service in self._services
        ]
        read: list[PurchaseRecommendation] = []
        failed: list[tuple[str, str, CollectionError]] = []
        for kind, program, ask in asked:
            try:
                read.append(ask())
            except CollectionError as failure:
                failed.append((kind, program, failure))
        if failed and not read:
            raise failed[0][2]

        at = self._clock()
        base = {"tenant": tenant, "run": context.run_id}
        batch: list[dict[str, Any]] = [
            {
                **base,
                "kind": one.kind,
                "program": one.program,
                "term": one.term_years,
                "payment": one.payment_option,
                "lookback": one.lookback_days,
                "recommended": one.recommended,
                "hourly": one.hourly_commitment,
                "units": one.units,
                "savings": one.estimated_monthly_savings,
                "percent": one.estimated_savings_percent,
                "upfront": one.upfront_cost,
                "currency": one.currency,
                "cause": None,
                "detail": None,
                "as_of": one.as_of,
                "collected_at": one.collected_at,
            }
            for one in read
        ] + [
            {
                **base,
                "kind": kind,
                "program": program,
                "term": policy.term_years,
                "payment": policy.payment_option,
                "lookback": 0,
                "recommended": None,
                "hourly": None,
                "units": None,
                "savings": None,
                "percent": None,
                "upfront": None,
                "currency": None,
                "cause": failure.cause,
                "detail": str(failure),
                "as_of": at,
                "collected_at": at,
            }
            for kind, program, failure in failed
        ]
        context.connection.execute(UPSERT, batch)
        removed = context.connection.execute(RETRACT, {"tenant": tenant, "run": context.run_id})
        return CollectorOutcome(items_written=len(read), items_removed=int(removed.rowcount or 0))
