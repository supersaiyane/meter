"""What each member account holds, per account and Region, every day. FEAT-086, TASK-P14-002.

P14 spec sections 5.3 and 7. A reservation is read in every Region the account is read in; a
Savings Plan has no Region, so it is read once per account, in the first collection Region's unit,
rather than once per Region and counted as many times.

**A run restates what it read and nothing else.** Rows this run did not see are removed only from
the scope it read: the account and Region's reservations, and the account's Savings Plans when it
read them. Without the account or the Region one unit would remove another's rows. A read that
fails raises its typed cause before anything is removed, so an account that refuses keeps its last
good rows with their age, constraint 5, rather than reading as an account that holds nothing.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sqlalchemy import text

from finops_core.domain.commitments import RESERVATION, SAVINGS_PLAN, HeldCommitment
from finops_core.errors import SchemaDrift
from finops_core.ports.commitment import CommitmentHoldings
from finops_ingest.registry import CollectorContext, CollectorOutcome

COLLECTOR = "commitment_inventory"

UPSERT = text(
    "INSERT INTO commitment_inventory (tenant_id, ingest_run_id, kind, commitment_id, program, "
    "account_id, region_id, applies_to, quantity, hourly_commitment, term_months, "
    "payment_option, upfront_amount, recurring_hourly, currency, starts_at, ends_at, state, "
    "as_of, collected_at) VALUES (:tenant, :run, :kind, :id, :program, :account, :region, "
    ":applies_to, :quantity, :hourly, :term, :payment, :upfront, :recurring, :currency, "
    ":starts_at, :ends_at, :state, :as_of, :collected_at) "
    "ON CONFLICT ON CONSTRAINT pk_commitment_inventory DO UPDATE SET "
    "ingest_run_id = EXCLUDED.ingest_run_id, program = EXCLUDED.program, "
    "account_id = EXCLUDED.account_id, region_id = EXCLUDED.region_id, "
    "applies_to = EXCLUDED.applies_to, quantity = EXCLUDED.quantity, "
    "hourly_commitment = EXCLUDED.hourly_commitment, term_months = EXCLUDED.term_months, "
    "payment_option = EXCLUDED.payment_option, upfront_amount = EXCLUDED.upfront_amount, "
    "recurring_hourly = EXCLUDED.recurring_hourly, currency = EXCLUDED.currency, "
    "starts_at = EXCLUDED.starts_at, ends_at = EXCLUDED.ends_at, state = EXCLUDED.state, "
    "as_of = EXCLUDED.as_of, collected_at = EXCLUDED.collected_at"
)

#: Each predicate is load bearing: the account and the Region keep one unit to its own rows.
RETRACT_RESERVATIONS = text(
    "DELETE FROM commitment_inventory WHERE tenant_id = :tenant AND kind = :kind "
    "AND account_id = :account AND region_id = :region AND ingest_run_id <> :run"
)
RETRACT_SAVINGS_PLANS = text(
    "DELETE FROM commitment_inventory WHERE tenant_id = :tenant AND kind = :kind "
    "AND account_id = :account AND ingest_run_id <> :run"
)


class CommitmentInventoryCollector:
    """One account and Region's reservations, and its Savings Plans in the first Region's unit."""

    def __init__(self, holdings: CommitmentHoldings, *, first_region: str) -> None:
        self._holdings = holdings
        self._first_region = first_region

    def __call__(self, context: CollectorContext) -> CollectorOutcome:
        if context.run_id is None:
            raise ValueError("commitment_inventory needs the run id from the ledger's claim")
        unit = context.unit
        if unit.account is None or unit.region is None:
            raise SchemaDrift(
                scope_key=unit.scope_key,
                collector=COLLECTOR,
                detail="a commitment inventory unit arrived without an account or a Region",
            )
        account, region = unit.account, str(unit.region)
        held = list(self._holdings.reservations(account, region))
        reads_plans = region == self._first_region
        if reads_plans:
            held.extend(self._holdings.savings_plans(account))

        written = self._write(context, held)
        base = {"tenant": unit.tenant_id, "account": account.account_id, "run": context.run_id}
        removed = context.connection.execute(
            RETRACT_RESERVATIONS, {**base, "kind": RESERVATION, "region": region}
        ).rowcount
        if reads_plans:
            removed += context.connection.execute(
                RETRACT_SAVINGS_PLANS, {**base, "kind": SAVINGS_PLAN}
            ).rowcount
        return CollectorOutcome(items_written=written, items_removed=int(removed or 0))

    @staticmethod
    def _write(context: CollectorContext, held: Iterable[HeldCommitment]) -> int:
        batch: list[dict[str, Any]] = [
            {
                "tenant": context.unit.tenant_id,
                "run": context.run_id,
                "kind": one.kind,
                "id": one.commitment_id,
                "program": one.program,
                "account": one.account_id,
                "region": one.region_id,
                "applies_to": one.applies_to,
                "quantity": one.quantity,
                "hourly": one.hourly_commitment,
                "term": one.term_months,
                "payment": one.payment_option,
                "upfront": one.upfront_amount,
                "recurring": one.recurring_hourly,
                "currency": one.currency,
                "starts_at": one.starts_at,
                "ends_at": one.ends_at,
                "state": one.state,
                "as_of": one.as_of,
                "collected_at": one.collected_at,
            }
            for one in held
        ]
        if batch:
            context.connection.execute(UPSERT, batch)
        return len(batch)
