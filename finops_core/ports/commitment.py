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

from finops_core.domain.account import AccountKey
from finops_core.domain.commitments import (
    CommitmentPolicy,
    HeldCommitment,
    PurchaseRecommendation,
)
from finops_core.domain.cost import CommitmentCoverage, CommitmentDay, CommitmentUse


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

    def daily(self, window_start: date, window_end: date) -> Iterable[CommitmentDay]:
        """Each kind of commitment's use and coverage, one row per kind per day.

        Read at the provider's daily grain, one request per figure for the whole window, so
        a run that reads a month of days costs what one window does, and each run rewrites
        the days a late bill changed. A kind with nothing committed and nothing covered on a
        day has no row for that day. `window_end` is exclusive, and no day after it is read.

        Raises:
            AccessDenied, NotOptedIn, Throttled, Unreachable: as for `utilization`.
            NoData: Nothing was committed or covered on any day in the window.
        """
        ...


@runtime_checkable
class CommitmentHoldings(Protocol):
    """What each member account holds, from the service that sold it. FEAT-086, TASK-P14-002.

    A port of its own rather than a third method on `CommitmentReport`, because it is a different
    source at a different grain: Cost Explorer reports use and coverage for the organization, as
    the payer; this reads each account's own commitments, as that account's collector role, and a
    commitment belongs to the account that bought it.

    **Two methods, because Savings Plans have no Region and reservations do.** A Savings Plan is
    read once per account; a reservation in every Region the account is read in. One method taking
    an optional Region would let a caller read the Savings Plans once per Region and count each
    plan as many times.

    Every failure is a typed `CollectionError`. An account that refuses is AccessDenied, never an
    account that holds nothing.
    """

    def savings_plans(self, account: AccountKey) -> Iterable[HeldCommitment]:
        """Every Savings Plan the account holds, in every state, retired ones included."""
        ...

    def reservations(self, account: AccountKey, region: str) -> Iterable[HeldCommitment]:
        """Every reservation the account holds in the Region, for each service read."""
        ...


@runtime_checkable
class PurchaseRecommendations(Protocol):
    """AWS's own purchase recommendations, read as the payer. FEAT-089, TASK-P14-006, OPEN-35.

    Asked in the tenant's policy's term and payment option, so AWS's answer and Meter's own plan
    are about the same purchase. Each call is one recommendation: a Savings Plans type, or a
    reserved service as Cost Explorer names it. Every failure is a typed `CollectionError`.
    """

    def savings_plans(self, program: str, policy: CommitmentPolicy) -> PurchaseRecommendation:
        """AWS's recommendation for one Savings Plans type, `Compute` or `EC2Instance`."""
        ...

    def reservations(self, service: str, policy: CommitmentPolicy) -> PurchaseRecommendation:
        """AWS's recommendation for one reserved service, summed over its lines."""
        ...
