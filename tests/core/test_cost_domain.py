"""The two cost types, and the mistakes they exist to make impossible.

A billing period whose end is read as inclusive costs a month. A total that
travels without saying which measure it is gets rendered under whichever label
the screen happened to use. Neither mistake is visible by reading the code that
makes it, which is why both are types rather than conventions.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from finops_core.domain.cost import BillingPeriod, CostMeasure, CostTotal

AUGUST = BillingPeriod(start=date(2026, 8, 1), end=date(2026, 9, 1))
NOW = datetime(2026, 8, 23, 6, 0, tzinfo=UTC)


class TestTheEndIsExclusive:
    def test_the_last_day_of_the_month_is_covered(self) -> None:
        assert AUGUST.covers(date(2026, 8, 31))

    def test_the_end_itself_is_not(self) -> None:
        """`PERIOD_END` for August is 2026-09-01, the start of the next period.

        That is the FOCUS convention and the fixtures already follow it. Nothing
        wrote it down, so the first person to read the end as inclusive would
        have counted one day of September into August and found out at a
        reconciliation.
        """
        assert not AUGUST.covers(date(2026, 9, 1))

    def test_a_day_before_it_starts_is_not_covered(self) -> None:
        assert not AUGUST.covers(date(2026, 7, 31))

    def test_a_period_that_ends_before_it_starts_is_refused(self) -> None:
        with pytest.raises(ValueError, match="ends before it starts"):
            BillingPeriod(start=date(2026, 9, 1), end=date(2026, 8, 1))

    def test_a_period_of_no_length_is_refused(self) -> None:
        # Not a period. A caller that produced one has an off by one, and
        # returning an empty interval would hide it.
        with pytest.raises(ValueError, match="ends before it starts"):
            BillingPeriod(start=date(2026, 8, 1), end=date(2026, 8, 1))


class TestOpenIsAskedOfAClock:
    def test_a_period_still_running_is_open(self) -> None:
        assert AUGUST.is_open(at=NOW)

    def test_a_period_well_past_is_closed(self) -> None:
        assert not AUGUST.is_open(at=datetime(2026, 9, 15, 0, 0, tzinfo=UTC))

    def test_the_moment_it_closes_is_closed(self) -> None:
        # The end is exclusive here too. A period is open while charges can
        # still land in it, and at its end they cannot.
        assert not AUGUST.is_open(at=datetime(2026, 9, 1, 0, 0, tzinfo=UTC))

    def test_the_clock_comes_from_the_caller(self) -> None:
        """No `datetime.now()` inside the type.

        A type that reads the wall clock cannot be tested at a boundary, and
        every test of it is a test of when it ran.
        """
        old = BillingPeriod(start=date(2020, 1, 1), end=date(2020, 2, 1))
        assert old.is_open(at=datetime(2020, 1, 15, tzinfo=UTC))
        assert not old.is_open(at=NOW)

    def test_a_naive_clock_is_refused(self) -> None:
        # Comparing a naive datetime against an aware one raises deep inside
        # the comparison, at a point where the message says nothing about
        # billing periods.
        with pytest.raises(ValueError, match="timezone"):
            AUGUST.is_open(at=datetime(2026, 8, 23, 6, 0))


class TestATotalCarriesItsMeasure:
    def test_it_cannot_be_built_without_one(self) -> None:
        with pytest.raises(TypeError):
            CostTotal(amount=Decimal("1.00"), as_of=NOW, collected_at=NOW)  # type: ignore[call-arg]

    def test_two_measures_of_the_same_amount_are_not_the_same_total(self) -> None:
        """The whole point. Amortized and billed cost are routinely equal for a
        month with no commitments in it, and a screen that renders one under the
        other's label is wrong in a way nobody can see until the month they
        differ.
        """
        effective = CostTotal(
            amount=Decimal("100.00"), measure=CostMeasure.EFFECTIVE, as_of=NOW, collected_at=NOW
        )
        billed = CostTotal(
            amount=Decimal("100.00"), measure=CostMeasure.BILLED, as_of=NOW, collected_at=NOW
        )
        assert effective != billed

    def test_money_is_never_a_float(self) -> None:
        """`finops_core/domain/cost.py` says money is Decimal and never float.

        A float total over a month of line items is wrong in the last places,
        and a cost report that does not reconcile with the invoice is a cost
        report nobody uses twice. Saying it in a docstring did not stop anyone.
        """
        with pytest.raises(TypeError, match="Decimal"):
            CostTotal(
                amount=100.0,  # type: ignore[arg-type]
                measure=CostMeasure.EFFECTIVE,
                as_of=NOW,
                collected_at=NOW,
            )

    def test_it_is_a_fact_so_it_carries_both_timestamps(self) -> None:
        # Constraints 4 and 10. A total with no `as_of` is a number with no
        # claim about when it was true.
        with pytest.raises(TypeError):
            CostTotal(amount=Decimal("1.00"), measure=CostMeasure.EFFECTIVE)  # type: ignore[call-arg]

    def test_effective_is_the_amortized_measure(self) -> None:
        # Named here so the roadmap's decision is readable from the code. The
        # primary measure everywhere is amortized cost, which FOCUS calls
        # effective, and unblended is retained only for invoice reconciliation.
        assert CostMeasure.EFFECTIVE.value == "effective"
        assert set(CostMeasure) == {
            CostMeasure.EFFECTIVE,
            CostMeasure.BILLED,
            CostMeasure.LIST,
            CostMeasure.CONTRACTED,
        }


class TestTheFingerprintIsAnIdentityAndNotASummary:
    """`source_fingerprint` is the key a restated month upserts on."""

    def _identity(self, **overrides: object) -> str:
        from finops_core.domain.cost import source_fingerprint

        fields: dict[str, object] = {
            "billing_account_id": "111122223333",
            "sub_account_id": "444455556666",
            "charge_period_start": datetime(2026, 8, 1, tzinfo=UTC),
            "charge_period_end": datetime(2026, 8, 2, tzinfo=UTC),
            "service_name": "AmazonEC2",
            "resource_id": "i-0001",
            "sku_id": None,
            "charge_category": "Usage",
            "commitment_discount_id": None,
        }
        fields.update(overrides)
        return source_fingerprint(**fields)  # type: ignore[arg-type]

    def test_the_same_charge_hashes_the_same_way(self) -> None:
        assert self._identity() == self._identity()

    def test_a_different_charge_does_not(self) -> None:
        assert self._identity() != self._identity(resource_id="i-0002")
        assert self._identity() != self._identity(service_name="AmazonRDS")

    def test_it_takes_no_cost_at_all(self) -> None:
        """The whole design, expressed as a signature.

        AWS restates the current month continuously. A fingerprint that
        included the amount would make a restated row a new row, and the month
        would grow by one copy of every corrected line item. The function
        cannot be handed a cost, so nobody can add one in a hurry.
        """
        import inspect

        from finops_core.domain.cost import source_fingerprint

        taken = set(inspect.signature(source_fingerprint).parameters)
        assert not {name for name in taken if "cost" in name or "quantity" in name}

    def test_it_survives_a_process_restart(self) -> None:
        """`hash()` is salted per process.

        A fingerprint from it is stable within one run and different in the
        next, and the symptom is a table that doubles every time the worker
        restarts, which looks like a billing problem rather than a code one.
        """
        import subprocess
        import sys

        script = (
            "from datetime import UTC, datetime;"
            "from finops_core.domain.cost import source_fingerprint;"
            "print(source_fingerprint("
            "billing_account_id='111122223333', sub_account_id='444455556666',"
            "charge_period_start=datetime(2026, 8, 1, tzinfo=UTC),"
            "charge_period_end=datetime(2026, 8, 2, tzinfo=UTC),"
            "service_name='AmazonEC2', resource_id='i-0001', sku_id=None,"
            "charge_category='Usage', commitment_discount_id=None))"
        )
        runs = {
            subprocess.run(
                [sys.executable, "-c", script], capture_output=True, text=True, check=True
            ).stdout.strip()
            for _ in range(2)
        }
        assert len(runs) == 1, f"the digest changed between processes: {runs}"
        assert runs == {self._identity()}
