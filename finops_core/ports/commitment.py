"""Reading what was committed, what it consumed, and what it covered.

Its own port rather than a widening of `CostExport`, and the reason is not
tidiness. A Savings Plan is not a line item: it arrives from a different API, on a
different cadence, at a grain the billing export does not have. Modelling it as a
charge row would put a second meaning on `cost_focus_daily`, and a table with two
meanings is one nobody can sum.

**Two methods, because the provider has two grains and so does the truth.**
Utilization is per commitment: this plan obliged us to pay so much and consumed so
much of it. Coverage is per service or region: of the spend that could have been
on a commitment, this much was. A dollar of covered spend cannot be attributed to
one of three overlapping plans, so no provider reports coverage per plan and
neither does this port. A single method returning both on one object would invite
exactly that fabrication.

On AWS this is Cost Explorer, which is a different service from the data export
the cost rows come from, with its own throttle and its own per request charge. See
ADR-0012 for why the cadence is a row in `collector_schedule` rather than a
constant here.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from typing import Protocol, runtime_checkable

from finops_core.domain.cost import CommitmentCoverage, CommitmentUse


@runtime_checkable
class CommitmentReport(Protocol):
    """Utilization per commitment, and coverage per dimension."""

    def utilization(self, window_start: date, window_end: date) -> Iterable[CommitmentUse]:
        """Every commitment that was live at any point in the window.

        Includes commitments that expired inside the window, and ones whose term
        has not started. An expired commitment is reported as expired rather than
        omitted, because the money was spent and the coverage gap the expiry leaves
        is the finding a reader needs.

        `window_end` is exclusive.

        Raises:
            AccessDenied: The cost and usage APIs are not readable with these
                credentials.
            NotOptedIn: Cost Explorer has never been enabled for this payer, which
                is a distinct condition from holding no commitments.
            NoData: The payer holds no commitments. This is the one cause a caller
                may render as an empty list rather than a failure.
            Throttled: The provider rejected the read rate.
            Unreachable: The endpoint did not answer.
        """
        ...

    def coverage(self, window_start: date, window_end: date) -> Iterable[CommitmentCoverage]:
        """What share of the eligible estate was covered, per dimension.

        One row per commitment type and dimension value, never per commitment.

        `window_end` is exclusive.

        Raises:
            AccessDenied: The cost and usage APIs are not readable with these
                credentials.
            NotOptedIn: Cost Explorer has never been enabled for this payer.
            NoData: Nothing in the window was eligible for a commitment, which is
                a fact about the estate rather than a failure.
            Throttled: The provider rejected the read rate.
            Unreachable: The endpoint did not answer.
        """
        ...
