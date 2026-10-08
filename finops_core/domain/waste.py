"""What the estate should cost instead, and how sure we are of it.

Two numbers carry every recommendation and they must never become one.

**Severity answers how much money is at stake.** It comes from the money, per
ADR-0016, through the same function the query findings and the anomalies use, so
three screens do not mean different things by the word high.

**Confidence answers how sure the estimate is.** It comes from how many days the
estimate rests on, and from nothing else.

A single blended score is the obvious simplification and it hides exactly the
recommendation most worth arguing about: a ten thousand dollar finding resting on
three days of data is CRITICAL and LOW, and a reader needs both figures to decide
whether to act this week. `severity_of` and `confidence_of` below take different
arguments on purpose, so neither can see the other's input.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from finops_core.domain.fact import Fact
from finops_core.domain.observation import MINIMUM_HISTORY
from finops_core.errors import CollectionError


class Confidence(StrEnum):
    """How much data the estimate rests on. Never derived from the money."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class Lifecycle(StrEnum):
    """Where a recommendation is. The event log is what says how it got there."""

    OPEN = "OPEN"
    ACCEPTED = "ACCEPTED"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"
    VERIFIED = "VERIFIED"
    REGRESSED = "REGRESSED"
    DISMISSED = "DISMISSED"


#: Transitions that are allowed. Everything else is refused, which is what stops a
#: VERIFIED recommendation quietly returning to OPEN and being counted twice.
ALLOWED: dict[Lifecycle, frozenset[Lifecycle]] = {
    Lifecycle.OPEN: frozenset({Lifecycle.ACCEPTED, Lifecycle.DISMISSED}),
    Lifecycle.ACCEPTED: frozenset({Lifecycle.IN_PROGRESS, Lifecycle.DISMISSED, Lifecycle.OPEN}),
    Lifecycle.IN_PROGRESS: frozenset({Lifecycle.DONE, Lifecycle.DISMISSED}),
    # DONE is where the verification collector takes over, and only it may move a
    # recommendation on from here.
    Lifecycle.DONE: frozenset({Lifecycle.VERIFIED, Lifecycle.REGRESSED}),
    # Terminal. A verified saving that later regresses is a new finding, not an
    # edit of the old one, because the old one was true when it was made.
    Lifecycle.VERIFIED: frozenset(),
    Lifecycle.REGRESSED: frozenset(),
    Lifecycle.DISMISSED: frozenset({Lifecycle.OPEN}),
}


class Source(StrEnum):
    """Who found it. One table holds all of them."""

    COMPUTE_OPTIMIZER = "COMPUTE_OPTIMIZER"
    COST_OPTIMIZATION_HUB = "COST_OPTIMIZATION_HUB"
    TRUSTED_ADVISOR = "TRUSTED_ADVISOR"
    METER = "METER"


class WasteClass(StrEnum):
    """The closed list. A free text class is one no screen can label and no score
    can weight, so adding one is a migration rather than a string."""

    RIGHTSIZE_INSTANCE = "RIGHTSIZE_INSTANCE"
    IDLE_INSTANCE = "IDLE_INSTANCE"
    GRAVITON_CANDIDATE = "GRAVITON_CANDIDATE"
    EBS_OVERPROVISIONED = "EBS_OVERPROVISIONED"
    EBS_GP2_TO_GP3 = "EBS_GP2_TO_GP3"
    EBS_UNATTACHED = "EBS_UNATTACHED"
    SNAPSHOT_AGED = "SNAPSHOT_AGED"
    NAT_GATEWAY_IDLE = "NAT_GATEWAY_IDLE"
    LOAD_BALANCER_IDLE = "LOAD_BALANCER_IDLE"
    ELASTIC_IP_UNASSOCIATED = "ELASTIC_IP_UNASSOCIATED"
    DYNAMODB_OVERPROVISIONED = "DYNAMODB_OVERPROVISIONED"
    LOG_GROUP_NO_RETENTION = "LOG_GROUP_NO_RETENTION"
    LOG_GROUP_UNQUERIED = "LOG_GROUP_UNQUERIED"
    LOG_DUPLICATE_DELIVERY = "LOG_DUPLICATE_DELIVERY"
    METRIC_UNQUERIED = "METRIC_UNQUERIED"
    ALARM_INSUFFICIENT_DATA = "ALARM_INSUFFICIENT_DATA"
    CONTAINER_RIGHTSIZE = "CONTAINER_RIGHTSIZE"
    PARKABLE_WINDOW = "PARKABLE_WINDOW"
    COMMITMENT_UNCOVERED = "COMMITMENT_UNCOVERED"
    #: TASK-P9-008. An instance that needs a larger type. Its own kind, with an added monthly
    #: cost and a saving of nought, so no total of savings can fall because of one.
    UPSIZE_INSTANCE = "UPSIZE_INSTANCE"


#: Where confidence steps up. Two weeks is the floor for existing at all, a month
#: is enough to have seen a weekly cycle, and a quarter has seen a month end.
CONFIDENT_DAYS = 30
VERY_CONFIDENT_DAYS = 90


def confidence_of(observation_days: int) -> Confidence:
    """How sure the estimate is, from how long it watched.

    Takes only the day count. It cannot see the money, and that is the point: a
    large finding is not a confident one, and the two figures answer different
    questions.
    """
    if observation_days >= VERY_CONFIDENT_DAYS:
        return Confidence.HIGH
    if observation_days >= CONFIDENT_DAYS:
        return Confidence.MEDIUM
    return Confidence.LOW


#: Compute Optimizer's performance risk runs from none to very high.
LEAST_RISK = Decimal(0)
MOST_RISK = Decimal(4)


@dataclass(frozen=True, kw_only=True)
class RankedOption:
    """One target a provider ranked for a recommendation, as it ranked it. TASK-P9-006.

    P9 spec section 5.5: every ranked option is kept, not only the first, so a reader can see
    what was passed over and why. The price is not here: it is the catalog's, looked up when the
    option is stored, and an option the catalog cannot price is kept and says so.
    """

    rank: int
    instance_type: str
    #: The provider's own risk that the target underperforms, 0 to 4.
    performance_risk: Decimal
    #: The provider's own monthly figure, where it gives one. Modelled, and kept beside the
    #: catalog's price rather than replaced by it.
    provider_monthly_saving: Decimal | None = None
    migration_effort: str | None = None
    #: What changes on the way, in the provider's words: architecture, hypervisor, storage.
    platform_differences: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.rank < 1:
            raise ValueError(f"an option ranked {self.rank} is not ranked")
        if not self.instance_type:
            raise ValueError("an option names the type it would move to")
        if not LEAST_RISK <= self.performance_risk <= MOST_RISK:
            raise ValueError(f"a performance risk of {self.performance_risk} is off the scale")


@dataclass(frozen=True, kw_only=True)
class Recommendation(Fact):
    """One thing worth changing, whatever found it.

    `severity` arrives already computed, because it comes from settings this layer
    must not read. `confidence` is computed here, because it needs nothing but the
    day count already on the entity.
    """

    tenant_id: UUID
    sub_account_id: str
    source: Source
    #: The provider's own identifier, so a re read updates rather than duplicates.
    #: For a METER sourced finding it is ours and is stable across runs.
    source_reference: str
    waste_class: WasteClass
    resource_id: str
    region_id: str

    #: Modelled, always. What we think would be saved, never what was saved.
    estimated_monthly_saving: Decimal
    #: From the money, through `finops_query.severity`. Never entered by hand.
    severity: str
    observation_days: int
    lifecycle: Lifecycle
    owner: str | None
    ticket_reference: str | None
    #: The working, so a reader can disagree with it.
    rationale: str
    #: The type the resource runs as now, where the source names one. TASK-P9-006.
    current_instance_type: str | None = None
    #: Every target the source ranked, best first. TASK-P9-006.
    options: tuple[RankedOption, ...] = ()
    #: What an Upsize adds to the bill a month, modelled. Only an Upsize has one. TASK-P9-008.
    added_monthly_cost: Decimal | None = None

    def __post_init__(self) -> None:
        ranks = [option.rank for option in self.options]
        if len(set(ranks)) != len(ranks):
            raise ValueError("two options share a rank, so neither is the one ranked there")
        upsize = self.waste_class is WasteClass.UPSIZE_INSTANCE
        if upsize != (self.added_monthly_cost is not None):
            raise ValueError("an Upsize states its added cost, and nothing else has one")
        if upsize and (self.added_monthly_cost or 0) <= 0:
            raise ValueError("an Upsize adds to the bill, so its added cost is above nought")
        if upsize and self.estimated_monthly_saving != 0:
            raise ValueError("an Upsize saves nothing, so no total of savings can fall by it")
        if isinstance(self.estimated_monthly_saving, float):
            raise TypeError("money is Decimal. A float saving rounds differently on two screens.")
        if self.estimated_monthly_saving < 0:
            raise ValueError("a saving is never negative. A cost increase is not a recommendation")
        if self.observation_days < MINIMUM_HISTORY:
            # Not a cautious estimate. A new resource looks exactly like an idle
            # one for its first fortnight, and a product that recommends
            # terminating it teaches the reader to ignore the screen.
            raise ValueError(
                f"{self.observation_days} days is under the {MINIMUM_HISTORY} day floor. "
                "There is no recommendation, not a low confidence one."
            )
        if not self.rationale:
            raise ValueError("a recommendation nobody can argue with is one nobody acts on twice")

    @property
    def confidence(self) -> Confidence:
        return confidence_of(self.observation_days)

    def may_move_to(self, target: Lifecycle) -> bool:
        return target in ALLOWED[self.lifecycle]


@dataclass(frozen=True, kw_only=True)
class RealizedSaving(Fact):
    """What actually appeared in the bill, and what it can honestly claim.

    Separate from the estimate, in its own table, because the two are different
    kinds of number and every tool that inflates identified savings does it by
    adding a modelled figure to a measured one.
    """

    recommendation_id: UUID
    tenant_id: UUID
    window_before_start: date
    window_before_end: date
    window_after_start: date
    window_after_end: date
    #: Measured, from cost_focus_daily.
    cost_before: Decimal
    cost_after: Decimal
    #: The control. Without it a fall in cost cannot be told apart from a fall in
    #: use, and the counterfactual is unobservable.
    usage_before: Decimal
    usage_after: Decimal
    verdict: str
    why: str

    def __post_init__(self) -> None:
        for name in ("cost_before", "cost_after", "usage_before", "usage_after"):
            if isinstance(getattr(self, name), float):
                raise TypeError(f"{name} is Decimal, not float")
        if self.window_before_end <= self.window_before_start:
            raise ValueError("a window ends after it starts")
        if self.window_after_end <= self.window_after_start:
            raise ValueError("a window ends after it starts")

    @property
    def realized_monthly_saving(self) -> Decimal:
        return self.cost_before - self.cost_after


@dataclass(frozen=True)
class ScopedFindings:
    """What a source found in the scopes it could read, and why it could not read the rest.

    TASK-P9-006, constraint 5. A source read one account and one Region at a time can lose some
    and not others. Iterating gives the findings, so a caller that knows nothing of scopes reads
    it as before; a caller that does records each refusal and withdraws nothing it could not see.
    """

    found: tuple[Recommendation, ...]
    #: Every (account, Region) read in full.
    read: frozenset[tuple[str, str]]
    refused: tuple[CollectionError, ...] = ()

    def __iter__(self) -> Iterator[Recommendation]:
        return iter(self.found)
