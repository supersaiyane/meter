"""The response envelope. Every figure arrives with what it is worth trusting.

FEAT-050 and constraints 4, 5 and 10 in CLAUDE.md meet here. A number without
`as_of` is a number nobody can tell is stale. A view that covers two accounts
out of five, presented without saying so, is a true answer to a question nobody
asked. A failed collection rendered as an absent row is indistinguishable from
zero cost.

So `meta` is not decoration and it is not optional. It carries when the data was
true, when it was fetched, how much of the organization it covers, whether
anything is broken, and what to do about each broken thing. `degraded` is
computed rather than assigned, because a flag someone can forget to set is a
flag that will be wrong exactly when it matters.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
    model_validator,
)

from finops_api.screens import SCREEN_PATHS
from finops_core.constants import REPORT_RECIPIENTS_MAX, SAVED_VIEW_NAME_MAX_LENGTH


class CoverageOut(BaseModel):
    """What was seen against everything there was to see. ISS-016."""

    model_config = ConfigDict(frozen=True)

    visible: int
    total: int
    #: What is being counted, plural. Accounts on most routes and workspaces on
    #: the query routes, which is why it travels on the wire: the route knows
    #: what it counted and the interface was guessing, so every screen said
    #: "accounts" and the query screens were counting something else.
    unit: str = "accounts"
    #: The account the reader chose, FEAT-075, when the view is narrowed to one. Coverage is
    #: then counted against that account, so a choice is stated rather than reported as a
    #: partial view, by the owner's decision of 2026-10-06.
    chosen: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_partial(self) -> bool:
        return self.visible < self.total


class FailureOut(BaseModel):
    """One thing that is broken, and what the reader should do about it."""

    model_config = ConfigDict(frozen=True)

    scope_key: str
    collector: str
    #: One of the six causes in finops_core.errors. Never a free text message.
    cause: str
    remediation: str
    occurrences: int
    last_seen_at: datetime


class Meta(BaseModel):
    """What the numbers beside this are worth."""

    model_config = ConfigDict(frozen=True)

    #: When the data was true at the source. None when nothing has been collected.
    as_of: datetime | None
    #: When Meter fetched it. Never earlier than as_of. Constraint 10.
    collected_at: datetime | None
    scope_coverage: CoverageOut
    failures: tuple[FailureOut, ...] = ()

    @computed_field  # type: ignore[prop-decorator]
    @property
    def degraded(self) -> bool:
        """True when the reader must not take these figures at face value.

        Computed, never assigned. Three separate things make a view untrustworthy
        and any one of them is enough: something failed, the view covers only
        part of the organization, or nothing has been collected at all.
        """
        return bool(self.failures) or self.scope_coverage.is_partial or self.as_of is None

    @classmethod
    def build(
        cls,
        visible: int,
        total: int,
        unit: str = "accounts",
        as_of: datetime | None = None,
        collected_at: datetime | None = None,
        failures: Sequence[FailureOut] = (),
        chosen: str | None = None,
    ) -> Meta:
        return cls(
            as_of=as_of,
            collected_at=collected_at,
            scope_coverage=CoverageOut(visible=visible, total=total, unit=unit, chosen=chosen),
            failures=tuple(failures),
        )


class Envelope[T](BaseModel):
    """Every route returns this. There is no bare data variant."""

    model_config = ConfigDict(frozen=True)

    data: T
    meta: Meta


# --- the response models ------------------------------------------------------
#
# These describe what leaves the API, so they live here rather than beside the
# route that returns them. `finops_mcp` generates its tool schemas from these
# exact classes, and it may not import a route module, because every one of them
# imports SQLAlchemy and the facade is forbidden from reaching the service
# layer. The alternative was a second set of models in `finops_mcp` kept equal by
# hand, which is the drift the generation was meant to remove.


class MeOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    principal_id: str
    display_name: str
    tenant_id: str
    tiers: tuple[str, ...]
    is_global: bool
    accounts_in_scope: int


class AccountOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider: str
    account_id: str
    name: str
    status: str
    role_health: str
    role_health_checked_at: datetime | None
    #: The provider's own words about why the role is unusable. Never a stack trace.
    role_health_error: str | None
    as_of: datetime
    collected_at: datetime


class OrgNodeOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    node_id: str
    node_type: str
    parent_node_id: str | None
    name: str
    path: str
    depth: int
    #: False when the caller's scope does not reach this account. The node is
    #: still here; what it means is that no figure may be shown against it.
    reachable: bool
    as_of: datetime
    collected_at: datetime


class RunOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str
    collector: str
    scope_key: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    items_written: int
    #: One of the six causes, or None. Never a free text exception message.
    error_type: str | None
    error_detail: str | None


class FreshnessOut(BaseModel):
    """How far behind one collector is on one scope, against its own cadence."""

    model_config = ConfigDict(frozen=True)

    collector: str
    scope_key: str
    #: Null when the pair has never once succeeded. There is no age to report
    #: and no last known good moment, and a zero would read as this instant.
    as_of: datetime | None
    cadence_seconds: int | None
    age_seconds: float | None
    #: `current`, `stale`, or `never_collected`. Three states, because a
    #: collector that has never worked is not a stale one: stale says the answer
    #: is old, and this says there has never been an answer.
    state: str
    #: The typed cause of the last attempt, when it failed. Null otherwise.
    cause: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_stale(self) -> bool:
        """Anything that is not current. Derived, so it cannot disagree with
        `state`, which is what two independently set fields would eventually
        do."""
        return self.state != "current"


class PlatformCostOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    day: date
    module: str
    service: str
    #: Decimal, never float. A float total over a month of line items is wrong
    #: in the last places, and a figure that will not reconcile is not used twice.
    amortized_cost: Decimal
    as_of: datetime
    collected_at: datetime


class CollectorHealth(BaseModel):
    """How long since a collector last succeeded, against its own cadence."""

    model_config = ConfigDict(frozen=True)

    collector: str
    last_success_at: datetime | None
    cadence_seconds: int
    age_seconds: float | None
    is_stale: bool


class HealthOut(BaseModel):
    """`/healthz`. Deliberately not a bare liveness probe.

    A process that is running while the database is unreachable, or while
    ingestion stopped six hours ago, is a process that will serve confident and
    wrong numbers. Reporting only liveness makes that invisible to exactly the
    system that is supposed to notice.
    """

    model_config = ConfigDict(frozen=True)

    status: str
    database_reachable: bool
    collectors: tuple[CollectorHealth, ...]


class CostTotalOut(BaseModel):
    """What a billing period cost, and whether that period is finished.

    `is_open` is on the payload rather than inferred by the frontend from a
    date, because a part month set beside a whole month with no warning reads
    as a collapse in spend, and the thing that knows whether a period is still
    accruing is the side that read the export.

    Both measures travel together. They are routinely equal, since a month with
    no commitments has the same amortized and billed cost, so a screen that
    rendered one under the other's label would be right until the month it was
    not.
    """

    model_config = ConfigDict(frozen=True)

    period: date
    is_open: bool
    effective_cost: Decimal
    billed_cost: Decimal
    line_items: int


class CostSummaryOut(BaseModel):
    """This period, the one before it, and the difference between them.

    The comparison is computed here rather than on the screen. Two screens
    subtracting the same two numbers is two chances to subtract them in the
    wrong order.
    """

    model_config = ConfigDict(frozen=True)

    current: CostTotalOut
    previous: CostTotalOut | None
    #: None when there is no previous period to compare against, which is not
    #: the same as no change and must not render as zero.
    change: Decimal | None


class CostAnomalyOut(BaseModel):
    """One day that did not look like the days before it.

    Three numbers rather than a percentage, because a percentage alone is not
    actionable: somebody has to know the money before they can decide whether to
    care, and they have to know the baseline before they can disagree.
    """

    model_config = ConfigDict(frozen=True)

    account_id: str
    service_name: str
    day: date
    observed: Decimal
    baseline: Decimal
    delta: Decimal
    #: Null when the baseline had not moved. Every departure from an unmoving
    #: baseline is infinitely many deviations, so this says nothing rather than
    #: something false.
    deviations: Decimal | None
    severity: str
    #: The working. A verdict a reader cannot argue with is one they have to
    #: take on trust, and nobody takes a cost alert on trust twice.
    why: str


class CostAnomaliesOut(BaseModel):
    """The anomalies, and enough context to read an empty list correctly."""

    model_config = ConfigDict(frozen=True)

    anomalies: list[CostAnomalyOut]
    #: How many days of cost this scope has. An estate with fewer than
    #: `days_needed` cannot be judged at all, which is a different fact from an
    #: estate that is behaving, and the screen must not render them alike.
    days_collected: int
    days_needed: int


class OwnerSuggestionOut(BaseModel):
    """Whom one source says to ask about a resource. A suggestion, never an owner. FEAT-077."""

    model_config = ConfigDict(frozen=True)

    owner: str
    #: TEAM, PERSON or AUTOMATION. A creator is never a team, and a pipeline is never a person.
    kind: str
    #: CATALOGUE, TAG or CREATOR, the order a recommendation lists them in.
    source: str
    #: What a reader checks it against: the application, the tag key, or the creating event.
    detail: str
    as_of: datetime
    collected_at: datetime


class RecommendationOut(BaseModel):
    """One thing worth changing.

    Severity and confidence are two fields and never one. Severity is what is at
    stake, confidence is how sure the estimate is, and a reader needs both to
    decide whether to act this week.
    """

    model_config = ConfigDict(frozen=True)

    recommendation_id: UUID
    account_id: str
    source: str
    waste_class: str
    resource_id: str
    region_id: str
    #: Modelled, always. Never add this to a realized saving.
    estimated_monthly_saving: Decimal
    severity: str
    confidence: str
    observation_days: int
    lifecycle: str
    #: Null is a reported condition, not a gap. An unowned finding is never fixed.
    owner: str | None
    #: The strongest team any source names, ISS-021: the catalogue's, then the owner tags', and
    #: failing both the inventory node's TEAM_TAG, read as it was before TASK-P11-005. A
    #: suggestion of whom to ask, never an owner: null when nothing in the reader's access names
    #: a team. A creator is never a team, so it is never this.
    suggested_owner: str | None = None
    #: TASK-P11-005. Every source's suggestion, strongest first: the catalogue, the tags, the
    #: creator. Whom to ask, never an owner, ISS-021; empty where no source names anybody.
    owner_suggestions: list[OwnerSuggestionOut] = Field(default_factory=list)
    #: Where CloudTrail's event history began when it was asked who created the resource and
    #: found it older: created before CloudTrail's 90 days. Null when not asked, or found.
    created_before: datetime | None = None
    ticket_reference: str | None
    #: The working, so a reader can disagree with the verdict.
    rationale: str
    #: FEAT-052. What applying this would cost if it turns out to be wrong, from
    #: `finops_query.actions`. Three fields rather than one label, because the two
    #: questions are independent and neither is confidence: a high confidence resize still
    #: restarts the workload, and a low confidence snapshot deletion is still permanent.
    reversible: bool
    disturbs_running_work: bool
    #: Reversible and disturbing nothing, both halves. Not a synonym for safe: five of the
    #: eight classes that disturb nothing cannot be undone.
    is_no_regret: bool
    #: The sentence. A flag with no sentence behind it is one a reader cannot argue with.
    risk_why: str
    #: TASK-P9-010, spec section 8. The type a rightsizing moves from and to, both prices an hour
    #: at list from one price list version, and what an Upsize adds a month. Null where the
    #: finding names no target. The saving above is the price difference already scaled to the
    #: bill, never up; these are the list prices it was worked out from.
    current_instance_type: str | None = None
    target_instance_type: str | None = None
    current_hourly_price: Decimal | None = None
    target_hourly_price: Decimal | None = None
    price_version: str | None = None
    #: An Upsize's cost, modelled. Never a saving, and never added to one.
    added_monthly_cost: Decimal | None = None


class AlternativeOut(BaseModel):
    """One type a rightsizing could move to, as its source ranked it. TASK-P9-010.

    Compute Optimizer's options with its performance risk, or the types Meter's own rule found to
    fit the demand it measured, which carry no risk score. Every price is list, an hour from the
    recommendation's price list version, and a month at 730 hours; both modelled.
    """

    model_config = ConfigDict(frozen=True)

    rank: int
    instance_type: str
    #: The one the recommendation names. It leads the list.
    chosen: bool
    vcpus: int | None
    memory_mib: int | None
    network_baseline_gbps: Decimal | None
    hourly_price: Decimal | None
    monthly_price: Decimal | None
    #: The current type's monthly list price less this one's. Negative for a larger type.
    monthly_saving: Decimal | None
    #: Compute Optimizer's 0 to 4 score; null where the source gives none, as Meter's rule does.
    performance_risk: Decimal | None
    platform_differences: list[str]
    #: Why no price is shown, where none is.
    unpriced_reason: str | None


class AlternativesOut(BaseModel):
    """What a rightsizing was compared with, the chosen type first."""

    model_config = ConfigDict(frozen=True)

    recommendation_id: UUID
    current_instance_type: str | None
    current_hourly_price: Decimal | None
    price_version: str | None
    alternatives: list[AlternativeOut]


class InstanceTypeOut(BaseModel):
    """One type as the catalog describes it in one Region. FEAT-072, TASK-P9-010."""

    model_config = ConfigDict(frozen=True)

    service_code: str
    region: str
    instance_type: str
    family: str | None
    current_generation: bool | None
    architectures: list[str]
    burstable: bool
    #: A burstable type's baseline share of each vCPU, from the source it names.
    baseline_cpu: Decimal | None
    vcpus: int
    memory_mib: int
    network_performance: str | None
    network_baseline_gbps: Decimal | None
    ebs_baseline_mbps: int | None
    gpu_count: int | None
    #: False once the Region stops listing it. Kept, because a recommendation may still name it.
    offered: bool
    as_of: datetime
    collected_at: datetime


class InstanceTypesOut(BaseModel):
    """The types that match, and whether the limit cut the list short."""

    model_config = ConfigDict(frozen=True)

    instance_types: list[InstanceTypeOut]
    #: True when as many rows came back as were allowed, so more may match.
    limit_reached: bool


class PriceOut(BaseModel):
    """One price from AWS's price list, as the catalog holds it. FEAT-071, TASK-P9-010."""

    model_config = ConfigDict(frozen=True)

    sku_price_id: str
    sku: str
    service_code: str
    region: str
    #: The price list version, which is its publication time. Every price says which list it is.
    version: str
    pricing_category: str
    pricing_unit: str
    currency: str
    recurring_unit_price: Decimal
    upfront_fee: Decimal
    lease_years: int | None
    purchase_option: str | None
    offering_class: str | None
    #: The attributes that tell two prices for one product apart, as the price list names them.
    details: dict[str, str]
    effective_date: date
    as_of: datetime
    collected_at: datetime


class PricesOut(BaseModel):
    """The prices that match, and whether the limit cut the list short."""

    model_config = ConfigDict(frozen=True)

    prices: list[PriceOut]
    limit_reached: bool


class RecommendationEventOut(BaseModel):
    """One step in a recommendation's life."""

    model_config = ConfigDict(frozen=True)

    #: Null exactly once, on the row recording that it was found.
    from_lifecycle: str | None
    to_lifecycle: str
    actor: str
    reason: str | None
    occurred_at: datetime


class RecommendationDetailOut(BaseModel):
    """One recommendation and how it got where it is."""

    model_config = ConfigDict(frozen=True)

    recommendation: RecommendationOut
    history: list[RecommendationEventOut]


class RefusalOut(BaseModel):
    """One resource a sizing rule examined and declined to recommend. FEAT-062.

    There is deliberately no saving and no severity on this. A refusal has no money, ADR-0016
    orders every finding by money, and a zero here would rank as the least valuable action
    rather than as the absence of one.
    """

    model_config = ConfigDict(frozen=True)

    resource_id: str
    account_id: str
    region_id: str
    #: Which rule declined, so a reader knows what question was asked.
    waste_class: str
    #: The sentence that decided it, whole. A shortened reason is one nobody can argue with.
    reason: str
    #: What the judgement rests on. A refusal after four days is worth questioning; one after
    #: ninety is worth relying on, and a reader cannot tell them apart without this.
    observation_days: int


class RefusalsOut(BaseModel):
    """What Meter looked at and decided not to recommend. FEAT-062, ADR-0027.

    `examined` counts distinct resources rather than rows, because one resource declined by two
    rules is one resource that was looked at.
    """

    model_config = ConfigDict(frozen=True)

    refusals: tuple[RefusalOut, ...]
    examined: int


class RecommendationsOut(BaseModel):
    """The list, and the one number that is about the list rather than in it."""

    model_config = ConfigDict(frozen=True)

    recommendations: list[RecommendationOut]
    #: How many open recommendations nobody is responsible for. ISS-021: an
    #: unowned finding is never fixed, so the count is shown rather than left for
    #: somebody to notice.
    unowned: int


class RealizedSavingOut(BaseModel):
    """What actually appeared in the bill, and what it can claim.

    Deliberately carries no estimated figure. The two are different kinds of
    number and a response holding both is the first place somebody adds them.
    """

    model_config = ConfigDict(frozen=True)

    recommendation_id: UUID
    #: Measured, from the cost rows.
    cost_before: Decimal
    cost_after: Decimal
    #: The control. A fall in cost with a larger fall in usage is not a saving.
    #: Nullable, and the null is load bearing: `consumed_quantity` is absent from the
    #: billing rows for some services, and None means nobody published a quantity
    #: rather than a quantity of zero. A zero here would read as a workload that
    #: vanished. Constraint 5, and migration `0012` holds the same rule in the
    #: database.
    usage_before: Decimal | None
    usage_after: Decimal | None
    verdict: str
    why: str
    window_before_start: date
    window_after_end: date


class RealizedSavingsOut(BaseModel):
    """Realized savings, grouped by verdict rather than summed.

    A single realized total would be added to the estimated total by the first
    person who saw them side by side, and an inconclusive saving is not a saving.
    """

    model_config = ConfigDict(frozen=True)

    savings: list[RealizedSavingOut]
    #: Verdict to count and money. Never a grand total.
    by_verdict: dict[str, VerdictTotalOut]


class VerdictTotalOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    count: int
    realized_monthly: Decimal


class ScoreComponentOut(BaseModel):
    """One part of a score, with the findings that produced it.

    `points` is nullable and the null is not a zero. A component that could not be
    computed is excluded from the score's denominator, and rendering it as nought
    would report the worst possible posture for something nobody measured.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    points: Decimal | None
    weight: int
    why: str
    #: The recommendations that moved this component, so the screen can link to them.
    findings: list[UUID]


class ScoreOut(BaseModel):
    """A score that arrives with its parts, because that is FEAT-043's ship condition.

    `components` is required rather than optional. A response that could carry a
    total on its own is a response a screen would render on its own.
    """

    model_config = ConfigDict(frozen=True)

    account_id: str
    total: int
    #: What the total is out of. A score of sixty out of sixty available weight is
    #: not the same claim as sixty out of a hundred, and a reader cannot tell without
    #: this.
    available_weight: int
    why: str
    components: list[ScoreComponentOut]
    as_of: datetime


class ScoresOut(BaseModel):
    """Every scored account, worst first, and the ones nobody could score."""

    model_config = ConfigDict(frozen=True)

    scores: list[ScoreOut]
    #: Accounts with no score at all. Listed rather than omitted: an account nobody
    #: could assess is different from an account with a bad score, and a shorter list
    #: is not something anybody notices.
    unscored: list[str]


class CommitmentUseOut(BaseModel):
    """One commitment, and how much of what we paid for was consumed.

    No coverage figure, and its absence is deliberate. A dollar of covered spend
    cannot be attributed to one of several overlapping plans, so a coverage field
    here would be a number nobody measured. Coverage is `CommitmentCoverageOut`.
    """

    model_config = ConfigDict(frozen=True)

    commitment_id: str
    commitment_type: str
    #: QUEUED, ACTIVE or EXPIRED. An expired commitment is reported rather than
    #: dropped, because the coverage gap its expiry leaves is the finding.
    status: str
    term_start: date
    term_end: date
    committed: Decimal
    used: Decimal
    #: Money already spent that bought nothing. The one figure on this row a
    #: reader can act on without further arithmetic.
    wasted: Decimal
    #: Null where nothing was committed in the window, which is what a queued
    #: commitment looks like. Zero would say the whole commitment was wasted, and
    #: it has not started.
    utilization: Decimal | None


class CommitmentDayOut(BaseModel):
    """One kind of commitment on one day, TASK-P8-013, with its two fractions worked out.

    Each fraction is null on a day with nothing to divide by: nothing committed has no
    utilization, and nothing eligible has no coverage, which is a different sentence from
    zero.
    """

    model_config = ConfigDict(frozen=True)

    commitment_type: str
    day: date
    committed: Decimal
    used: Decimal
    utilization: Decimal | None
    eligible_spend: Decimal
    covered_spend: Decimal
    coverage: Decimal | None
    as_of: datetime
    collected_at: datetime


class CommitmentCoverageOut(BaseModel):
    """How much of one slice of the estate was on a commitment."""

    model_config = ConfigDict(frozen=True)

    commitment_type: str
    dimension: str
    dimension_value: str
    eligible_spend: Decimal
    covered_spend: Decimal
    #: Null where nothing was eligible. Zero says the estate is uncovered and
    #: somebody should buy; null says there was nothing there to buy for.
    coverage: Decimal | None


class BudgetOut(BaseModel):
    """One budget, the spend against it, and what that means. FEAT-060.

    Everything derived travels on the payload rather than being recomputed by the screen, so
    the interface and the API cannot disagree about whether something is over.
    """

    model_config = ConfigDict(frozen=True)

    budget_id: str
    name: str
    #: ACCOUNT, SERVICE, ALL or UNSUPPORTED.
    scope: str
    scope_value: str
    limit: Decimal
    currency: str
    period_start: date
    period_end: date
    #: Measured, from the bill. Null where no cost was collected for the period, or where the
    #: scope is one this product cannot reproduce. Null is not zero in either case.
    actual: Decimal | None
    #: UNDER, AT_RISK, OVER or UNKNOWN. Unknown is not a fourth colour on a traffic light: it
    #: is the answer when the period has not started, when no spend was collected, or when the
    #: scope cannot be joined, and it exists so none of those three renders as green.
    status: str
    #: How far through the period today is, nought to one. The denominator of the pace rule,
    #: on the wire so a reader can check the arithmetic rather than take it.
    elapsed: Decimal
    #: Spend as a fraction of the limit. Null wherever `actual` is.
    used: Decimal | None


class BudgetsOut(BaseModel):
    """Every budget for a period, and the count of the ones nothing can be compared against."""

    model_config = ConfigDict(frozen=True)

    period: date
    budgets: tuple[BudgetOut, ...]
    #: Budgets read, kept and never matched to a number. Non zero has to be said out loud: an
    #: estate with ten budgets over tag expressions is not an estate with no budgets, and a
    #: screen showing two greens out of twelve budgets would be saying the wrong thing.
    unsupported: int


class InvoiceComparisonOut(BaseModel):
    """One invoice beside Meter's billed cost for it. FEAT-076, TASK-P10-004.

    The invoice's amounts are the provider's and always present. Meter's and the differences are
    null whenever the state is not a comparison, No rows or Currency differs, and null there is
    not zero. A difference is Meter's figure less the invoice's, so a negative one is a charge
    the invoice carries and Meter's rows do not.
    """

    model_config = ConfigDict(frozen=True)

    invoice_id: str
    #: INVOICE or CREDIT_MEMO.
    invoice_type: str
    #: The invoice a credit memo corrects, and null on an invoice.
    original_invoice_id: str | None
    #: Who issued it, which is not always the provider: Marketplace charges are invoiced apart.
    invoice_issuer_name: str
    billing_currency: str
    invoice_before_tax: Decimal
    invoice_tax: Decimal
    invoice_billed_cost: Decimal
    meter_before_tax: Decimal | None
    meter_tax: Decimal | None
    difference_before_tax: Decimal | None
    difference_tax: Decimal | None
    #: Matched, Mismatched, No rows or Currency differs.
    state: str
    issued_at: datetime
    as_of: datetime
    collected_at: datetime


class ReconciliationOut(BaseModel):
    """A billing period's invoices, each compared with Meter's billed cost. FEAT-076.

    Measured on both sides: the invoice is read from the provider and Meter's figure is summed
    from the collected rows. The tolerance is the one modelled figure, and it travels on the
    payload so a reader can check a Matched rather than take it.
    """

    model_config = ConfigDict(frozen=True)

    period: date
    #: Open or Closed, as FOCUS 1.4 names them.
    period_status: str
    #: Period open or Not readable when there is no invoice to compare, and null when there is.
    state: str | None
    #: The typed cause of the failed read behind Not readable, and null otherwise.
    cause: str | None
    #: The share of an invoice amount a difference may be and still match, modelled.
    tolerance: Decimal
    #: The least difference that counts, because an invoice is stated in cents.
    minimum_difference: Decimal
    invoices: tuple[InvoiceComparisonOut, ...]


class CommitmentActionOut(BaseModel):
    """A coverage gap as something somebody is accountable for closing. FEAT-055.

    The saving is modelled from a configured discount rather than from a quote, and
    `usage_floor_percent` is the number that decides whether buying the commitment was a
    mistake: a commitment obligates its whole term whether or not the usage continues, so it
    beats on demand only while usage stays above that fraction of today's. A payload carrying
    the saving without the floor would be recommending a multi year obligation while
    withholding the figure that says what going wrong looks like.
    """

    model_config = ConfigDict(frozen=True)

    commitment_type: str
    #: SERVICE or REGION. Never an account: coverage cannot be apportioned to one.
    dimension: str
    dimension_value: str
    window_start: date
    window_end: date
    #: Measured, from the bill. On the wire beside the modelled figures so a reader can check
    #: the arithmetic rather than take it.
    eligible_spend: Decimal
    covered_spend: Decimal
    #: Modelled. The screen labels it so, through `Figure`.
    estimated_monthly_saving: Decimal
    usage_floor_percent: Decimal
    term_months: int
    confidence: str
    severity: str
    lifecycle: str
    owner: str | None
    rationale: str


class CommitmentsOut(BaseModel):
    """Both figures for one window, and never one derived from the other."""

    model_config = ConfigDict(frozen=True)

    window_start: date
    window_end: date
    commitments: list[CommitmentUseOut]
    coverage: list[CommitmentCoverageOut]
    #: FEAT-055. The coverage above as things somebody owns, worst money first. Empty where
    #: every gap is below the configured floor, which is not the same as full coverage and the
    #: screen says which.
    actions: list[CommitmentActionOut]
    #: Every commitment's unused money, added up. Carried rather than left to the
    #: screen, so the file, the screen and the API agree on it.
    wasted_total: Decimal


class CostSliceOut(BaseModel):
    """One row of a grouping: a service, an account, a region or a tag value."""

    model_config = ConfigDict(frozen=True)

    #: `unallocated` where the row carries no value for the dimension. It is
    #: never dropped and never folded into a total.
    name: str
    effective_cost: Decimal
    billed_cost: Decimal
    line_items: int


class ShowbackRowOut(BaseModel):
    """One account, service and tag value in one billing period. FEAT-045.

    The period, both timestamps and the coverage are on every row rather than only in the
    envelope, because a showback file is mailed on and pasted into a deck, and a row pasted
    out of it has to carry what it meant. Constraint 10 and FEAT-045.
    """

    model_config = ConfigDict(frozen=True)

    billing_period: date
    account_id: str
    service_name: str
    #: The value of the tag key the reader chose, `unallocated` where the line carries none.
    tag_value: str
    effective_cost: Decimal
    billed_cost: Decimal
    line_items: int
    as_of: datetime
    collected_at: datetime
    accounts_in_file: int
    accounts_in_organization: int


class ContainerCostRowOut(BaseModel):
    """One workload's share of a cluster's cost."""

    model_config = ConfigDict(frozen=True)

    namespace: str
    workload_name: str
    #: Empty where the export did not carry a workload type. Never guessed.
    workload_type: str
    cost: Decimal
    line_items: int


class ClusterCostOut(BaseModel):
    """One cluster's cost, with its breakdown where there is one."""

    model_config = ConfigDict(frozen=True)

    cluster_name: str
    #: Attributed to workloads plus the remainder nothing asked for. This is the
    #: figure that reconciles to the cluster's node charge.
    total: Decimal
    allocated: Decimal
    #: Capacity the cluster paid for and no pod requested. A real figure, not a
    #: rounding error, and the reason bin packing is worth a screen.
    unallocated: Decimal
    workloads: tuple[ContainerCostRowOut, ...] = ()
    #: False where the cluster has a cost and no per workload breakdown. The cluster
    #: is still listed, per spec section 5.4.
    breakdown_available: bool = True
    #: Why the breakdown is missing, in words, where it is missing.
    unmeasurable_reason: str | None = None


class ContainerCostOut(BaseModel):
    """Cost by cluster, namespace and workload, measured rather than apportioned."""

    model_config = ConfigDict(frozen=True)

    clusters: tuple[ClusterCostOut, ...]
    #: Clusters with a breakdown, against clusters found. The screen states the
    #: ratio so nobody counts rows to discover the gap.
    measured_count: int
    found_count: int


class ContainerUsageRowOut(BaseModel):
    """One workload's requests against its use. Two figures each, never a percentage."""

    model_config = ConfigDict(frozen=True)

    namespace: str
    workload: str
    workload_kind: str
    launch_type: str
    #: None where the cluster cannot publish requests. Never zero.
    cpu_requested_millicores: Decimal | None
    cpu_used_p99_millicores: Decimal | None
    memory_requested_mib: Decimal | None
    memory_used_peak_mib: Decimal | None
    #: KILLED, NOT_KILLED or UNOBSERVED. UNOBSERVED is not a synonym for NOT_KILLED.
    oom_status: str
    observation_days: int


class ClusterUsageOut(BaseModel):
    """A cluster and its workloads, listed whether or not its requests are readable."""

    model_config = ConfigDict(frozen=True)

    cluster_name: str
    account_id: str
    region_id: str
    platform: str
    enhanced_observability: bool
    #: Why requests cannot be stated, in words, where they cannot.
    request_unavailable_reason: str | None
    workloads: tuple[ContainerUsageRowOut, ...]


class ContainerWasteOut(BaseModel):
    """Requested against used, and the clusters where that cannot be said."""

    model_config = ConfigDict(frozen=True)

    clusters: tuple[ClusterUsageOut, ...]
    measured_count: int
    found_count: int


class ClusterInventoryOut(BaseModel):
    """One cluster: its fleet, its Spot ratio and its bin packing, where readable."""

    model_config = ConfigDict(frozen=True)

    cluster_name: str
    account_id: str
    region_id: str
    platform: str
    enhanced_observability: bool
    node_count: int | None
    #: Fractions of one. None where the fleet could not be read or does not exist.
    spot_ratio: Decimal | None
    packing_efficiency: Decimal | None
    #: Why a fleet figure is missing, where one is.
    unmeasurable_reason: str | None


class ClustersOut(BaseModel):
    """Every cluster, and how many of those with nodes could be measured."""

    model_config = ConfigDict(frozen=True)

    clusters: tuple[ClusterInventoryOut, ...]
    measured_count: int
    found_count: int


class CostDayOut(BaseModel):
    """Effective cost on one day, for the chart on the cost screen."""

    model_config = ConfigDict(frozen=True)

    day: date
    effective_cost: Decimal


class CostPointOut(BaseModel):
    """What one query cost on one day. ISS-172.

    Provenance is on the point rather than on the series, because a run that
    saw evidence and one that did not produce different grades of number, and a
    line drawn through both without saying so asserts a confidence that only
    part of it has.
    """

    model_config = ConfigDict(frozen=True)

    run_date: date
    cost_month_usd: Decimal
    provenance: str


class QueryCostDayOut(BaseModel):
    """What every query audited on one day cost each month, summed. The trend on Query cost.

    Every query audited that day rather than only those audited today, so a dashboard deleted
    after a fix leaves its earlier days behind and the fall it caused is on the chart. Measured
    only when every query that day was measured, the rule the per query trend keeps.
    """

    model_config = ConfigDict(frozen=True)

    run_date: date
    cost_month_usd: Decimal
    queries: int
    provenance: str
    as_of: datetime
    collected_at: datetime


class QueryFindingOut(BaseModel):
    """One expensive query, as the findings list shows it."""

    model_config = ConfigDict(frozen=True)

    finding_id: UUID
    dashboard_uid: str | None
    dashboard_title: str | None
    panel_title: str | None
    folder_uid: str | None
    engine: str
    origin: str
    refresh_seconds: int | None
    window_seconds: int
    runs_per_day: Decimal
    scan_bytes_per_run: int | None
    #: Decimal, never float. A float total over a month of findings is wrong in
    #: the last places, and a figure that will not reconcile is not used twice.
    monthly_cost: Decimal
    #: measured or modelled. Never absent, and never inferred by the reader.
    provenance: str
    #: Null on a modelled row, a count on a measured one. The database refuses
    #: either half alone, so this pair is always consistent.
    measured_runs: int | None
    severity: str
    #: Which group this row is filed under. Sent on the row as well as on
    #: the group, so a reader looking at one finding can see the systemic
    #: problem it belongs to without fetching the groups separately.
    cause: str
    #: Null when nothing could attribute it. The API does not invent a
    #: placeholder: "unattributed" is a word a screen chooses, and an API that
    #: returned it would make an absence indistinguishable from a real owner
    #: whose name happens to be that.
    owner: str | None
    owner_source: str | None
    #: What drives the cost, in words. It is what makes a finding actionable
    #: rather than a number, so it is a field and not a tooltip.
    why: str
    #: Cost per audited day, oldest first, bounded to thirty days. Defaulted so
    #: an API that predates ISS-172 answers with an empty series rather than a
    #: missing field, and one point is not a trend.
    history: list[CostPointOut] = []
    as_of: datetime
    collected_at: datetime


class RemediationOut(BaseModel):
    """What a remediation did, or why it did not.

    `applied` false is a normal answer and carries a reason. The common case is
    a deployment whose write level is `none`, which is the default and is a
    decision rather than a fault, and the second most common is a finding that
    is not an explicit policy violation. A judgement call is a recommendation,
    not a remediation.
    """

    model_config = ConfigDict(frozen=True)

    finding_id: UUID
    applied: bool
    #: Set when the write did not take and was put back. The estate is
    #: unchanged, and this says so rather than leaving a reader to infer it.
    reverted: bool = False
    detail: str = ""
    #: Null unless something was recorded. An undo needs it, and a refusal has
    #: nothing to undo.
    change_id: UUID | None = None


class QueryGroupOut(BaseModel):
    """One cause, with the money behind it summed across every finding.

    The group exists because ADR-0016 requires aggregation before ranking. Four
    hundred findings at 15 USD each are LOW individually and 6,000 USD together,
    and a list ranked by individual severity puts the systemic problem below a
    single noisy panel.
    """

    model_config = ConfigDict(frozen=True)

    cause: str
    #: A sentence a reader can act on. The code is what groups; this is what is
    #: read, and neither is derived from the other at render time.
    label: str
    findings: int
    monthly_cost: Decimal
    #: Derived from the summed money like any other finding, so a group of LOW
    #: rows that adds up to a CRITICAL figure says CRITICAL.
    severity: str
    as_of: datetime
    collected_at: datetime


class QueryFindingDetailOut(QueryFindingOut):
    """One finding with its full working, for the detail screen."""

    model_config = ConfigDict(frozen=True)

    #: The query as written. Shown whole: a summary of a query is not evidence.
    query_text: str
    targets: list[str]
    region: str | None
    last_editor: str | None
    #: The published price the working is derived from. Sent rather than
    #: hardcoded in the screen, so the arithmetic it publishes has no constant
    #: the reader cannot see.
    rate_usd_per_gib: Decimal
    #: The change still applied to this finding, if any. Null means there is
    #: nothing to undo, and a screen uses it to decide whether the control
    #: exists at all rather than rendering one that does nothing.
    applied_change_id: UUID | None = None
    #: Null until FEAT-018 publishes a calibration. Never invented, because the
    #: honest rendering of an unpublished accuracy is to say it is unpublished.
    accuracy_percent: Decimal | None = None


class AdhocQueryOut(BaseModel):
    """One Logs Insights query that ran and belongs to no panel or alert rule.

    FEAT-051. There is no provenance field, and its absence is the claim: an ad
    hoc query exists only in the evidence, so there is nothing to model it from
    and every figure here is measured.
    """

    model_config = ConfigDict(frozen=True)

    adhoc_id: UUID
    account_id: str
    region_id: str
    #: The query as it ran, whole. A person has to recognise their own query in
    #: it, so it is never truncated on the way out.
    query_text: str
    runs: int
    scan_bytes: int
    cost_usd: Decimal
    #: Null when CloudTrail did not name the caller. The row is still reported:
    #: an expensive query nobody owns is the case this feature exists for.
    principal: str | None
    as_of: datetime
    collected_at: datetime


class SurfaceInstanceOut(BaseModel):
    """One place queries live, reachable or not."""

    model_config = ConfigDict(frozen=True)

    instance_id: UUID
    name: str
    kind: str
    endpoint: str
    account_id: str | None
    region_id: str | None
    reachable: bool
    #: One of the six causes when reachable is false, and never free text.
    unreachable_reason: str | None
    #: Null when the instance could not be read. Null is not zero: an instance
    #: Meter cannot reach has an unknown number of queries, and a zero would
    #: make the estate look smaller than it is.
    #: The smallest refresh this instance accepts from anybody. Null means it
    #: enforces none at all, which is not zero and is the estate FEAT-014 exists
    #: to find.
    refresh_floor_seconds: int | None
    query_count: int | None
    as_of: datetime
    collected_at: datetime


# --- P4, the graph and how much of it is real ---------------------------------
#
# The shape worth noticing is that `SubgraphOut` carries its coverage rather than
# leaving a screen to ask for it. That is section 6 of the P4 specification reaching
# the wire: a map that renders without knowing which regions were unreadable draws
# them as sparse, and sparse is indistinguishable from well connected on a diagram.


class NodeOut(BaseModel):
    """One resource on the map."""

    model_config = ConfigDict(frozen=True)

    node_id: UUID
    #: The ARN. On the wire because a person has to be able to find the thing in
    #: their own console, and the kind alone does not let them.
    provider_id: str
    account_id: str
    #: One of the fourteen kinds, and OTHER for a type the adapter cannot name.
    node_kind: str
    #: The provider's own word for the type, beside the lossy kind. Ten of the
    #: generated estate's twenty four types are OTHER, so without this the map is a
    #: field of unlabelled boxes. ISS-201.
    resource_type: str
    #: Null means global rather than regional: an IAM role belongs to an account and
    #: to no region. Never a region Meter could not read, which is a coverage row.
    region_id: str | None
    #: Null means regional rather than zonal, never that the zone is unknown.
    availability_zone: str | None
    name: str | None
    as_of: datetime
    collected_at: datetime


class EdgeOut(BaseModel):
    """One directed relationship. The direction is part of what it is."""

    model_config = ConfigDict(frozen=True)

    from_node_id: UUID
    to_node_id: UUID
    edge_kind: str
    #: True where the two ends are in different accounts. Materialised at write time,
    #: because it is the expensive question to ask repeatedly and the interesting one
    #: to answer.
    is_cross_account: bool
    #: The API call that supplied it. On the wire so a reader seeing no peering edges
    #: can tell an estate with no peering from a slice where the peering call refused.
    source: str
    #: True where the far end has no node in this payload. The map draws it as a
    #: boundary rather than as a line to nowhere, and the coverage rows say why.
    leaves_the_graph: bool


class SliceCoverageOut(BaseModel):
    """How much of one account's one region the graph was built from."""

    model_config = ConfigDict(frozen=True)

    account_id: str
    #: Null is the account's global slice, where the IAM roles live.
    region_id: str | None
    #: COMPLETE, PARTIAL or UNREAD. Unread is not a synonym for partial: partial
    #: means a read happened and fell short, unread means none has been attempted.
    state: str
    #: One of the seven causes, null only when COMPLETE. Never free text. ADR-0023.
    cause: str | None
    node_count: int
    edge_count: int
    as_of: datetime
    collected_at: datetime


class SubgraphOut(BaseModel):
    """A bounded neighbourhood, and everything it could not see."""

    model_config = ConfigDict(frozen=True)

    root_id: UUID
    nodes: tuple[NodeOut, ...]
    edges: tuple[EdgeOut, ...]
    #: Every slice this subgraph crossed, complete or not. Not optional and not
    #: behind a second call, so a screen cannot draw the map without it.
    coverage: tuple[SliceCoverageOut, ...]
    #: How far the walk actually got, which is at most the bound.
    depth_reached: int
    max_depth: int
    #: Nodes inside the depth bound that did not fit under the cap. Non zero means
    #: the map is showing part of a neighbourhood and has to say so.
    omitted_nodes: int
    #: False only when the traversal hit the ceiling, in which case the number above is a
    #: floor and the screen says "at least". True in every real neighbourhood so far.
    omitted_is_exact: bool
    max_nodes: int


class CoverageOutList(BaseModel):
    """Every incomplete slice a reader can see, for the estate wide banner."""

    model_config = ConfigDict(frozen=True)

    incomplete: tuple[SliceCoverageOut, ...]


class InventoryRootOut(BaseModel):
    """One node a reader can start a map from."""

    model_config = ConfigDict(frozen=True)

    node_id: UUID
    provider_id: str
    account_id: str
    node_kind: str
    resource_type: str
    region_id: str | None
    name: str | None


class InventoryRootsOut(BaseModel):
    """What there is to look at, before anybody has picked a root."""

    model_config = ConfigDict(frozen=True)

    roots: tuple[InventoryRootOut, ...]


class BlastPartOut(BaseModel):
    """One thing counted, and what it means. FEAT-044."""

    model_config = ConfigDict(frozen=True)

    name: str
    count: int
    why: str


class BlastRadiusOut(BaseModel):
    """What a change to one resource can reach, or why we will not say. FEAT-044.

    **Both halves are on one payload and exactly one of them is populated.** A refusal is an
    answer here, not an error, so it travels as a field rather than as a status code: a 409 or a
    500 would make the screen render a failure, and the graph having a hole in it is a fact
    about the estate rather than a fault in the request.

    `refused_because` names the slices when it is set. "The graph is incomplete" sends nobody
    anywhere, and the whole reason this refuses at all is that a low score over a graph missing
    a region reads as "this change is safe".
    """

    model_config = ConfigDict(frozen=True)

    #: CONTAINED, WIDE or CROSS_ACCOUNT. Null when refused.
    band: str | None
    parts: tuple[BlastPartOut, ...]
    reach: int | None
    accounts: int | None
    boundary_edges: int | None
    #: True where the walk reached its depth bound, so `reach` is a floor for that reason too.
    depth_bound_reached: bool
    #: Always true when a band is given. An infrastructure graph cannot see that one service
    #: reads another's queue, so every radius is at least this wide and possibly wider.
    is_lower_bound: bool
    #: The slices that stopped us, by name and state. Empty when a band is given.
    refused_because: tuple[str, ...]
    #: How far the walk was allowed, so a reader can tell a bounded answer from a finished one.
    max_depth: int


class FacetCountOut(BaseModel):
    """One filter value and how many resources in the scope carry it. TASK-P8-013.

    Null is a value like any other here: a null region is the account's global slice, and a
    null type is a resource the provider gave no type, both counted rather than dropped.
    """

    model_config = ConfigDict(frozen=True)

    value: str | None
    resources: int


class ResourceFiltersOut(BaseModel):
    """The filter values that occur in this scope, read from the data rather than listed.

    FEAT-056. Offering all fourteen node kinds when the estate holds four teaches a reader
    that ten of the filters return nothing, and `resource_type` has no enumeration at all: it
    is the provider's own word, so the data is the only place the list exists.
    """

    model_config = ConfigDict(frozen=True)

    account_id: tuple[str, ...]
    #: Never an empty string. A null region is the account's global slice and the screen
    #: offers it under that name, because a blank option in a select reads as a defect.
    region_id: tuple[str, ...]
    node_kind: tuple[str, ...]
    resource_type: tuple[str, ...]
    #: How many resources each region and each type holds, largest first, over the scope
    #: rather than under the list's own filters, the rule the values above follow. Defaulted,
    #: so a payload built before the counts existed still validates.
    region_counts: tuple[FacetCountOut, ...] = ()
    type_counts: tuple[FacetCountOut, ...] = ()


class RegionOut(BaseModel):
    """One region inside a geography. FEAT-061, ISS-213.

    `direction` is the compass word the region's own name carries, or None where it carries
    none. It is what lets a drawing put `eu-west-1` and `eu-central-1` in different parts of
    Europe with no table of regions to go stale, and it is a word rather than a coordinate
    because where a compass point lands in a picture is the picture's business.
    """

    model_config = ConfigDict(frozen=True)

    region_id: str
    resources: int
    direction: str | None


class GeographyOut(BaseModel):
    """One continent's worth of the estate. FEAT-061.

    `regions` is listed rather than counted, because the geography is continental and a reader
    who sees Europe wants to know whether that means Dublin, Frankfurt or both. It is the
    honest way to admit what the prefix cannot tell us.

    `accounts` is a distinct count across the whole geography and not the sum of its regions'
    counts. ISS-214: adding per region counts double counts an account present in two regions of
    one continent, which is the common case rather than the odd one, because a platform account
    with a disaster recovery copy is exactly that.
    """

    model_config = ConfigDict(frozen=True)

    #: The region name prefix, which is also the stable key the drawing positions by.
    key: str
    name: str
    #: Every region inside it that this reader can see, largest first.
    regions: tuple[RegionOut, ...]
    resources: int
    accounts: int


class GeographyLinkOut(BaseModel):
    """Two regions joined by edges whose two ends this reader can read. FEAT-061, TASK-P8-017.

    **Undirected, and counted once per pair of resources.** A peering is often recorded from
    both of its ends, as one edge each way, and a line on a map has no direction to give either
    of them. So `one_region` sorts before `other_region` and `links` counts distinct pairs of
    resources, not edges.

    **Both ends readable, or no link.** The far end's region is a fact about the far end, so a
    reader narrowed away from it learns nothing about where it is, the same rule the geography
    counts follow.

    `one_geography` and `other_geography` come from the region name prefix through the same rule
    as the geographies themselves, and are None where a prefix is not one the table knows. A
    link inside one geography carries the same key twice: it is real, and a map at continent
    grain cannot draw it, so the table under the map is where it is said.
    """

    model_config = ConfigDict(frozen=True)

    one_region: str
    other_region: str
    one_geography: str | None
    other_geography: str | None
    #: Distinct pairs of resources, measured.
    links: int
    #: The kinds of edge that join them, such as PEERS_WITH, so a line says what it stands for.
    kinds: tuple[str, ...]


class GeographiesOut(BaseModel):
    """The estate by continent, with everything the continent view cannot hold. FEAT-061.

    **Three kinds of leftover, kept apart on purpose.** Collapsing them would be the easy thing
    and each needs a different sentence and a different remedy.

    `global_resources` have no region at all. IAM, Route 53, CloudFront and the organization
    itself, and that is a fact about the service rather than a hole in the inventory. Nobody
    should be asked to fix it.

    `unplaceable` are regions whose name carries a prefix the geography table does not know.
    That is the one a reader can act on: a provider has opened a geography we have not heard of,
    and the table needs one more row.

    `refused` are regions a collection could not read. Their resources are not zero, they are
    unknown, and constraint 5 is that a failure is never rendered as the number zero.

    Every count here is measured, and the total of every geography plus the three leftovers is
    the estate this reader can see. A screen that shows the geographies alone is reporting a
    smaller estate than exists.
    """

    model_config = ConfigDict(frozen=True)

    geographies: tuple[GeographyOut, ...]
    global_resources: int
    #: Regions whose prefix is unknown, named so somebody can widen the table, with their count.
    unplaceable: tuple[str, ...]
    unplaceable_resources: int
    #: Regions a collection could not read, from the same slice coverage the map uses.
    refused: tuple[str, ...]
    #: Pairs of regions joined across a region boundary, both ends readable. TASK-P8-017.
    links: tuple[GeographyLinkOut, ...] = ()


class ResourceListOut(BaseModel):
    """A page of resources, and the denominator. FEAT-056, closing ISS-204.

    The navigation has promised this screen since P4 began and the P4 specification never
    scheduled one, so a delivered sub project was named as the thing that would bring a screen
    nobody planned.

    `total` is the count of rows matching the filter **that this reader may see**, counted
    through the same scope guard as the page. A count over everything beside a page of the
    readable rows is the arithmetic that tells a narrowed reader how much they are not
    allowed to look at.
    """

    model_config = ConfigDict(frozen=True)

    resources: tuple[NodeOut, ...]
    #: Matching rows in scope, which is the denominator the screen shows. Not the size of the
    #: estate, and not the size of the page.
    total: int
    limit: int
    offset: int
    filters: ResourceFiltersOut


class EntityOut(BaseModel):
    """One resource, and everything Meter knows about it. FEAT-053.

    The destination every list in the product needed and did not have. Adopted from the
    2026-09-26 IBM Turbonomic review, whose entity detail view is the thing their Supply Chain
    drills into.

    Five things, and two of them are admissions rather than facts. `coverage` says whether the
    slice this resource came from was read whole, because a page drawn from a PARTIAL slice may
    be missing the neighbour that matters. `unmatched_findings` says how many findings in the
    same account could not be matched to any resource, because an empty finding list otherwise
    reads as a clean resource when the truth may be that nothing could be joined to it.
    """

    model_config = ConfigDict(frozen=True)

    node: NodeOut
    #: Null means no coverage row exists for the slice, which should be impossible because the
    #: collector writes one per enrolled slice on every run. Reported rather than assumed
    #: complete, because assuming it is the failure P4 exists to prevent.
    coverage: SliceCoverageOut | None
    #: One hop. Enough to answer what this is attached to without drawing the estate.
    neighbours: tuple[NodeOut, ...]
    edges: tuple[EdgeOut, ...]
    #: Open and closed both, worst money first. A reader looking at a resource wants to know
    #: what was already decided about it as much as what is outstanding.
    findings: tuple[RecommendationOut, ...]
    #: Findings in the same account whose resource this tenant holds no node for. Non zero
    #: means the list above may be short for a reason that is nothing to do with this
    #: resource, and the screen says so.
    unmatched_findings: int
    #: What it cost in the latest billing period, effective, measured from the bill. Null
    #: where no line item joined, and null is not zero: a resource the bill does not mention
    #: is not a free one.
    monthly_cost: Decimal | None
    #: The period that cost belongs to. Null when the scope has no cost at all.
    cost_period: date | None
    #: FEAT-057. MANAGED, UNMANAGED or NOT_DETERMINED, derived rather than stored.
    #: NOT_DETERMINED is the default and is not a synonym for UNMANAGED: the first says we did
    #: not find the resource in the state we read, the second says nobody manages it, and only
    #: the second is an instruction. Telling somebody to import a resource that is already
    #: inside a module produces a duplicate or a state conflict.
    management_state: str
    #: The infrastructure as code address, where there is one. `module.network.aws_vpc.main`.
    iac_address: str | None
    #: Which state it was read from, so a reader can find the file rather than being told
    #: something unnamed manages their resource.
    iac_state_reference: str | None


class QuotaOut(BaseModel):
    """One quota with a usage figure, and what measured it. FEAT-033.

    Every quota in this shape has a `used` and a `source`. The ones that do not are
    `UnmeasurableQuotaOut`, and the two are separate types rather than one type with
    nullable fields, because a single list has to sort the nulls somewhere and wherever
    they sort is a claim nobody has earned. P5 spec section 9.
    """

    model_config = ConfigDict(frozen=True)

    account_id: str
    #: None where the quota is global rather than regional. A screen showing a placeholder
    #: here would display one account level limit once per region and add them up.
    region_id: str | None
    service_code: str
    quota_code: str
    quota_name: str
    #: None where the provider publishes no limit. Zero is a real and different value and
    #: means the thing is switched off here.
    limit: Decimal | None
    used: Decimal
    #: AWS_USAGE_METRIC, TRUSTED_ADVISOR or SERVICE_API. Never NONE in this shape: a
    #: measured figure names what measured it, so a reader can weigh the two differently.
    source: str
    #: The fraction still free, or None where the limit is absent or zero. Not a percentage
    #: and not rounded, so the interface decides how to render it and nothing is lost here.
    headroom: Decimal | None
    #: Whether an increase can be requested at all. FEAT-034 has to know before it drafts
    #: one, because a hard limit cannot be raised and a draft against it wastes an afternoon.
    is_adjustable: bool


class UnmeasurableQuotaOut(BaseModel):
    """One quota nothing measured, and why. FEAT-033, and the point of the sub project.

    It carries no `used` field at all rather than a null one. A null would invite a screen
    to render it as zero and a caller to treat it as a number, and the honest statement is
    that the figure does not exist rather than that it is empty.
    """

    model_config = ConfigDict(frozen=True)

    account_id: str
    region_id: str | None
    service_code: str
    quota_code: str
    quota_name: str
    limit: Decimal | None
    #: The sentence saying which of the three sources declined and why. Required, and the
    #: database refuses a row without one: a blank here teaches a reader the explanations in
    #: this product are empty, and they stop reading the ones that are not.
    reason: str
    is_adjustable: bool


class QuotasOut(BaseModel):
    """Two lists, because one would have to sort the nulls. P5 spec section 9.

    `measured_count` and `found_count` are stated rather than left to be counted off the
    two lists, because both are truncated: a reader given eight of forty cannot derive the
    ratio, and the ratio is the honest summary of how much of this problem AWS lets anybody
    solve. They are also what the envelope's coverage figure is built from.
    """

    model_config = ConfigDict(frozen=True)

    measurable: tuple[QuotaOut, ...]
    unmeasurable: tuple[UnmeasurableQuotaOut, ...]
    measured_count: int
    found_count: int


class RequestTransitionOut(BaseModel):
    """One status an increase request passed through, and when. FEAT-034."""

    model_config = ConfigDict(frozen=True)

    status: str
    changed_at: datetime


class QuotaRequestOut(BaseModel):
    """An increase somebody asked AWS for. Read, never written. Spec section 6.

    `submitted_by_meter` travels on the wire although it is always false, and that is the
    point: the screen says Meter did not submit this, and a field it reads is better than a
    sentence somebody could delete without failing a test.
    """

    model_config = ConfigDict(frozen=True)

    request_id: str
    account_id: str
    region_id: str | None
    service_code: str
    quota_code: str
    quota_name: str
    desired_value: Decimal
    #: AWS's own vocabulary, all seven values. DENIED and NOT_APPROVED are both here and are
    #: kept apart, because collapsing two of somebody else's values into one of ours makes
    #: the vocabulary a guess.
    status: str
    #: Whether anything is still going to happen to it. INVALID_REQUEST is not open: the
    #: action there is to ask again, which is a different thing to tell somebody than to wait.
    is_open: bool
    requested_at: datetime
    last_updated_at: datetime
    submitted_by_meter: bool = False


class QuotaRequestsOut(BaseModel):
    """Outstanding increase requests and what became of them. FEAT-034.

    Settled requests are included, refusals especially. A list showing only what is open
    answers the question it exists for with silence: somebody waiting on an increase wants
    to know it was denied three weeks ago more than they want a shorter list.
    """

    model_config = ConfigDict(frozen=True)

    requests: tuple[QuotaRequestOut, ...]
    open_count: int


class QuotaDetailOut(BaseModel):
    """One quota, everywhere it applies, with every request against it. FEAT-033, FEAT-034.

    `measurable` and `unmeasurable` are both lists here, for one quota code, and that is not
    redundancy. A quota code is per region, so the same limit can be measured in one region
    and unmeasured in another: one field would have to choose, and choosing means answering
    a question about a region nobody named.

    `history` is keyed by request id rather than being a field on each request, because a
    request with no recorded transitions is a real state, and an empty tuple hanging off
    every request reads as a history nobody found rather than one nobody has yet.
    """

    model_config = ConfigDict(frozen=True)

    service_code: str
    quota_code: str
    quota_name: str
    is_adjustable: bool
    measurable: tuple[QuotaOut, ...]
    unmeasurable: tuple[UnmeasurableQuotaOut, ...]
    requests: tuple[QuotaRequestOut, ...]
    history: dict[str, tuple[RequestTransitionOut, ...]]
    #: The increase Meter would ask for, per slice, and the slices it would not ask for.
    #: Two fields rather than one nullable one, for the reason the two quota lists are two
    #: lists: an empty draft reads as a feature that failed rather than a decision.
    drafts: tuple[QuotaDraftOut, ...] = ()
    draft_refusals: tuple[DraftRefusalOut, ...] = ()


class QuotaDraftOut(BaseModel):
    """An increase Meter would ask for, with its working. FEAT-034.

    One per slice, because each region has its own limit and its own observed peak: a single
    draft for a quota code would be sized from whichever row the query returned first.

    `submits` is not a field here, and that is deliberate. There is no endpoint to submit
    this, no method on the port and no IAM permission, so a flag saying Meter will not do it
    would be describing a capability that does not exist. The sentence on the screen and the
    `submitted_by_meter` column on a request are where the claim lives.
    """

    model_config = ConfigDict(frozen=True)

    account_id: str
    region_id: str | None
    current_limit: Decimal
    observed_usage: Decimal
    suggested_value: Decimal
    #: How the suggestion was reached, so a reader can disagree with the target rather than
    #: with the number. A figure with no derivation is one a reader accepts or ignores, and
    #: both are bad.
    working: str
    #: Exact, and copyable. The human step is a paste rather than a piece of research.
    console_url: str
    cli_command: str


class DraftRefusalOut(BaseModel):
    """Why no draft was offered for a slice. FEAT-034.

    Separate from `QuotaDraftOut` rather than a nullable field on it, for the reason the two
    quota lists are separate: a draft with a null suggestion invites a screen to render an
    empty one, and an empty draft is worse than a stated refusal because it looks like a
    feature that failed rather than a decision somebody made.
    """

    model_config = ConfigDict(frozen=True)

    account_id: str
    region_id: str | None
    reason: str


# --- the assistant, P7 ---------------------------------------------------------

#: The longest question accepted. An unbounded question is an unbounded prompt, and an
#: unbounded prompt is unbounded spend on the first paste of a log file.
QUESTION_MAX_LENGTH = 2000


class AskIn(BaseModel):
    """A question, carried in the body and never in the URL, where it would be logged."""

    model_config = ConfigDict(frozen=True)

    question: str = Field(min_length=1, max_length=QUESTION_MAX_LENGTH)


class CitationOut(BaseModel):
    """Where one figure in an answer came from, so a reader can check it on the page."""

    model_config = ConfigDict(frozen=True)

    placeholder: str
    tool: str
    call_id: str
    field: str
    #: As text, so a figure is the figure that was cited and never a float's idea of it.
    value: str
    kind: Literal["figure", "label"]
    #: What a figure counts, as the tool that returned it declares, ISS-231. None on a label,
    #: and on a figure stored before citations carried a unit, which a screen draws as
    #: unrecognised rather than guessing. Required, so a builder that forgets it fails.
    unit: Literal["usd", "count"] | None
    provenance: Literal["measured", "modelled"]
    as_of: datetime


class AnswerOut(BaseModel):
    """Prose with placeholders, and the citation behind each one."""

    model_config = ConfigDict(frozen=True)

    prose: str
    citations: tuple[CitationOut, ...]


class AssistantRefusalOut(BaseModel):
    """What is missing, and the screen that would show it once it is not."""

    model_config = ConfigDict(frozen=True)

    gap: str
    reason: str
    screen: str | None


class ExchangeFailureOut(BaseModel):
    """One of the seven typed causes, with what to do about it."""

    model_config = ConfigDict(frozen=True)

    cause: str
    detail: str | None
    remediation: str


class ToolCallOut(BaseModel):
    """One call the model asked for, in order."""

    model_config = ConfigDict(frozen=True)

    call_id: str
    tool: str
    returned: bool


class ExchangeOut(BaseModel):
    """One question and which of three things came back, as three different shapes.

    Exactly one of `answer`, `refusal` and `failure` is present and it is the one the
    outcome names, so a screen cannot render a refusal as an answer with nothing in it.
    Spec section 5.3: the three are three, and a product that blurs two of them is one a
    reader learns to distrust.
    """

    model_config = ConfigDict(frozen=True)

    exchange_id: UUID
    question: str
    outcome: Literal["ANSWERED", "REFUSED", "FAILED"]
    answer: AnswerOut | None
    refusal: AssistantRefusalOut | None
    failure: ExchangeFailureOut | None
    tool_calls: tuple[ToolCallOut, ...]
    model_id: str | None
    input_tokens: int
    output_tokens: int
    #: Modelled, at list prices. The bill is the measurement.
    est_cost: Decimal
    asked_at: datetime
    answered_at: datetime

    @model_validator(mode="after")
    def _exactly_the_shape_the_outcome_names(self) -> ExchangeOut:
        present = {"ANSWERED": self.answer, "REFUSED": self.refusal, "FAILED": self.failure}
        if [name for name, shape in present.items() if shape is not None] != [self.outcome]:
            raise ValueError("an exchange carries exactly the shape its outcome names")
        return self


class DigestOut(BaseModel):
    """One week's digest, its citations, and whether it went anywhere. FEAT-041."""

    model_config = ConfigDict(frozen=True)

    digest_id: UUID
    audience: Literal["team", "executive"]
    #: The bill's team tag, and None on the organization's digest.
    team: str | None
    period_start: date
    period_end: date
    prose: str
    citations: tuple[CitationOut, ...]
    composed_at: datetime
    #: None means composed and not sent, which is a real state and is said, with the reason.
    sent_at: datetime | None
    unsent_reason: str | None


class RedactionOut(BaseModel):
    """What redaction did to one question: the rule and the action. FEAT-046.

    There is no field for the secret, its position or its length, and no route could add
    one, because the table holds none of them.
    """

    model_config = ConfigDict(frozen=True)

    event_id: UUID
    exchange_id: UUID
    #: A gitleaks rule identifier, such as `aws-access-token`.
    rule_id: str
    action: Literal["BLOCKED", "REDACTED"]
    occurred_at: datetime
    #: Where the rule fired: the question typed, or what a tool returned to the model. ISS-085.
    found_in: Literal["question", "tool_result"] = "question"


class ExploreGroupingOut(BaseModel):
    """What one Cost Explorer axis groups by: a FOCUS column, or `tag` and one tag key."""

    model_config = ConfigDict(frozen=True)

    dimension: str
    tag_key: str | None = None


class ExploreWindowOut(BaseModel):
    """A run of days, inclusive at both ends."""

    model_config = ConfigDict(frozen=True)

    start: date
    end: date


class ExplorePointOut(BaseModel):
    """What one named group cost in one day or month. A null series is everything else."""

    model_config = ConfigDict(frozen=True)

    bucket: date
    series: str | None
    cost: Decimal


class GeographyRefOut(BaseModel):
    """Which geography a region is in, by the rule the geography map uses. FEAT-061."""

    model_config = ConfigDict(frozen=True)

    key: str
    name: str


class ExploreRowOut(BaseModel):
    """One row of the explorer's table: a value of each grouping, this period and the last.

    `previous_period` is null where the period before was never collected, which is not the
    same as a group that cost nothing then, and is never sent as zero.
    """

    model_config = ConfigDict(frozen=True)

    first: str
    second: str | None
    this_period: Decimal
    previous_period: Decimal | None


class ExploreOut(BaseModel):
    """FEAT-065. Cost grouped two ways over a period, set against the period before it.

    A total is null where nothing was billed in the window, rather than zero. The table holds
    at most `row_limit` rows, and `rows_omitted` with the two omitted sums says what the rest
    add up to, so the rows and the omissions always reconcile to the totals.
    """

    model_config = ConfigDict(frozen=True)

    metric: str
    metrics_available: list[str]
    period: str
    granularity: str
    current: ExploreWindowOut
    previous: ExploreWindowOut
    #: The window ends today, so its last day is still being billed and its total is not whole.
    is_open: bool
    #: The first billing month the scope holds line items for, or null for none.
    collected_from: date | None
    #: False where the previous window starts before `collected_from`.
    previous_collected: bool
    group_by: ExploreGroupingOut
    then_by: ExploreGroupingOut | None
    #: The allow list: the most used tag keys on this period's line items.
    tag_keys: list[str]
    total_this_period: Decimal | None
    total_previous_period: Decimal | None
    #: The groups the chart names, in stacking order. Points outside them carry a null series.
    series: list[str]
    points: list[ExplorePointOut]
    rows: list[ExploreRowOut]
    row_limit: int
    rows_omitted: int
    omitted_this_period: Decimal
    omitted_previous_period: Decimal | None
    #: Where the first grouping is region, the geography each row's region is in, by region,
    #: resolved here by the region name prefix rule so a screen that adds cost up by continent
    #: carries no second copy of it. A region no table knows is absent. Beside the rows rather
    #: than on each, so the export's columns stay the screen's. TASK-P8-017.
    region_geographies: dict[str, GeographyRefOut] = Field(default_factory=dict)


class ForecastRangeOut(BaseModel):
    """A forecast: a low and a high. Never a point, which is ADR-0015's second condition."""

    model_config = ConfigDict(frozen=True)

    low: Decimal
    high: Decimal


class ForecastMonthOut(BaseModel):
    """One month's forecast, or the sentence saying why there is none.

    `median_miss` is how far off the method was at the median over the months it was tested on,
    as a share of what each month cost, measured by backtest. `held_out` is how many months.
    """

    model_config = ConfigDict(frozen=True)

    month: date
    figure: ForecastRangeOut | None
    withheld: str | None
    median_miss: Decimal | None
    held_out: int


class ForecastDayOut(BaseModel):
    """One day of this month: cost billed to date, cumulative, or the band. Never both."""

    model_config = ConfigDict(frozen=True)

    day: date
    billed: Decimal | None
    low: Decimal | None
    high: Decimal | None


class ForecastTestOut(BaseModel):
    """One held out month of the month end backtest.

    The range is the band the method draws today applied to what it forecast for that month, so
    `within` says whether today's band would have held the month that happened. Both are null
    where the forecast is withheld.
    """

    model_config = ConfigDict(frozen=True)

    month: date
    actual: Decimal
    miss: Decimal
    low: Decimal | None
    high: Decimal | None
    within: bool | None


class ForecastOut(BaseModel):
    """FEAT-066. This month's total and the next three months', each a range or the reason.

    Every figure here is a forecast, said once in `provenance` and again on screen, and every
    figure is a range. The method is named, and its accuracy is published beside it.
    """

    model_config = ConfigDict(frozen=True)

    provenance: Literal["forecast"] = "forecast"
    method: str
    method_detail: str
    interval_percent: int
    #: The median miss above which a forecast is withheld, as a share.
    max_median_miss: Decimal
    #: The complete months a forecast is tested on before it is shown.
    min_held_out: int
    #: The last day with line items. Billed cost runs to here, and the forecast from the day after.
    billed_through: date
    billed_to_date: Decimal
    month_end: ForecastMonthOut
    days: list[ForecastDayOut]
    ahead: list[ForecastMonthOut]
    backtest: list[ForecastTestOut]


# --- saved views, FEAT-068 and TASK-P8-010 -------------------------------------------------

#: P8 spec section 6, and the database's `ck_saved_view__named`.
VIEW_NAME_MAX_LENGTH = SAVED_VIEW_NAME_MAX_LENGTH
#: How much query a view keeps: keys, characters in a key, values under one key, and characters
#: in a value. A screen's own parameters fit with room to spare, and a body cannot fill a row
#: with anything else.
VIEW_QUERY_MAX_KEYS = 40
VIEW_QUERY_MAX_KEY_LENGTH = 64
VIEW_QUERY_MAX_VALUES = 100
VIEW_QUERY_MAX_VALUE_LENGTH = 2000

ViewVisibility = Literal["PRIVATE", "SHARED"]
#: A screen's query string as an object: a parameter given once is a string, and one given more
#: than once is the list of its values, as the browser's own `URLSearchParams` holds them.
ViewQuery = dict[str, str | list[str]]


def view_name(name: str) -> str:
    """A view's name without its surrounding space, refused when nothing else is left."""
    stripped = name.strip()
    if not stripped:
        raise ValueError("a saved view needs a name that is not blank")
    if any(character < " " for character in stripped):
        raise ValueError("a saved view's name is one line of text")
    return stripped


def bounded_query(query: ViewQuery) -> ViewQuery:
    """The query, refused when it holds more than any screen's parameters could."""
    if len(query) > VIEW_QUERY_MAX_KEYS:
        raise ValueError(f"a saved view keeps at most {VIEW_QUERY_MAX_KEYS} query parameters")
    for key, value in query.items():
        if not key or len(key) > VIEW_QUERY_MAX_KEY_LENGTH:
            raise ValueError(
                f"a query parameter's name is 1 to {VIEW_QUERY_MAX_KEY_LENGTH} characters"
            )
        values = [value] if isinstance(value, str) else value
        if len(values) > VIEW_QUERY_MAX_VALUES:
            raise ValueError(f"{key} has more than {VIEW_QUERY_MAX_VALUES} values")
        if any(len(item) > VIEW_QUERY_MAX_VALUE_LENGTH for item in values):
            raise ValueError(f"{key} has a value over {VIEW_QUERY_MAX_VALUE_LENGTH} characters")
    return query


class SavedViewIn(BaseModel):
    """A screen and its query, named, kept for oneself or shared with the tenant. FEAT-068.

    Configuration and never data, P8 spec section 5.6. Nothing here is a figure, so opening the
    view reads its screen afresh in the opener's own scope, and a view saved by a reader of the
    whole estate shows a narrowed colleague only what their scope reaches.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1, max_length=VIEW_NAME_MAX_LENGTH)
    screen_path: str
    query: ViewQuery = Field(default_factory=dict)
    visibility: ViewVisibility = "PRIVATE"

    @field_validator("name")
    @classmethod
    def _named(cls, name: str) -> str:
        return view_name(name)

    @field_validator("screen_path")
    @classmethod
    def _known(cls, path: str) -> str:
        if path not in SCREEN_PATHS:
            raise ValueError(f"{path} is not a screen the navigation knows")
        return path

    @field_validator("query")
    @classmethod
    def _bounded(cls, query: ViewQuery) -> ViewQuery:
        return bounded_query(query)


class SavedViewPatchIn(BaseModel):
    """A new name, a new visibility, or both, for a view the reader saved.

    The screen and the query are what a view is, so a different one is a different view, saved
    anew, and this refuses them rather than ignoring them.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=VIEW_NAME_MAX_LENGTH)
    visibility: ViewVisibility | None = None

    @field_validator("name")
    @classmethod
    def _named(cls, name: str | None) -> str | None:
        return None if name is None else view_name(name)

    @model_validator(mode="after")
    def _changes_something(self) -> Self:
        if self.name is None and self.visibility is None:
            raise ValueError("a change names a new name, a new visibility, or both")
        return self


class SavedViewOut(BaseModel):
    """One saved view, as the person reading it sees it. FEAT-068.

    `owned` says whether the reader saved it, which decides whether they may rename, share or
    delete it. Who saved somebody else's shared view is not said: the owner is a person, as in
    ADR-0029, and sharing a view shares the view, not who made it.
    """

    model_config = ConfigDict(frozen=True)

    view_id: UUID
    name: str
    screen_path: str
    query: ViewQuery
    visibility: ViewVisibility
    owned: bool
    created_at: datetime
    updated_at: datetime


# --- report schedules and runs, FEAT-069 and TASK-P8-011 -------------------------------------

ReportFormat = Literal["xlsx", "csv"]
ReportCadence = Literal["DAILY", "WEEKLY", "MONTHLY", "MONTH_CLOSE"]
ReportRunStatus = Literal["STREAMED", "RENDERED", "SENT", "FAILED"]
#: The longest identifier a recipient may have: an email address's limit, which is the longest
#: form a principal's identifier takes.
RECIPIENT_MAX_LENGTH = 320
#: The longest route and query a schedule keeps. A screen's query fits many times over.
EXPORT_PATH_MAX_LENGTH = 2000


def recipients_of(recipients: Sequence[str]) -> list[str]:
    """Each person once, in the order given, without surrounding space, refused when blank."""
    people: list[str] = []
    for recipient in recipients:
        person = recipient.strip()
        if not person:
            raise ValueError("a recipient is a person's identifier and cannot be blank")
        if len(person) > RECIPIENT_MAX_LENGTH or any(character < " " for character in person):
            raise ValueError(f"{person[:40]} is not a person's identifier")
        if person not in people:
            people.append(person)
    return people


class ScheduleIn(BaseModel):
    """A saved view, one route its screen exports, a format, a cadence and who it is for.

    The route comes from the screen's own Export list, so it is one the screen reads. Each run
    renders it once per recipient in that recipient's scope, P8 spec section 5.7.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    view_id: UUID
    export_path: str = Field(min_length=1, max_length=EXPORT_PATH_MAX_LENGTH)
    format: ReportFormat
    cadence: ReportCadence
    recipients: list[str] = Field(min_length=1, max_length=REPORT_RECIPIENTS_MAX)

    @field_validator("recipients")
    @classmethod
    def _people(cls, recipients: list[str]) -> list[str]:
        return recipients_of(recipients)


class SchedulePatchIn(BaseModel):
    """Pause or resume a schedule, or change its format, cadence or recipients.

    The view and the route are what a schedule is, so another one is a new schedule.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    enabled: bool | None = None
    format: ReportFormat | None = None
    cadence: ReportCadence | None = None
    recipients: list[str] | None = Field(
        default=None, min_length=1, max_length=REPORT_RECIPIENTS_MAX
    )

    @field_validator("recipients")
    @classmethod
    def _people(cls, recipients: list[str] | None) -> list[str] | None:
        return None if recipients is None else recipients_of(recipients)

    @model_validator(mode="after")
    def _changes_something(self) -> Self:
        if (
            self.enabled is None
            and self.format is None
            and self.cadence is None
            and self.recipients is None
        ):
            raise ValueError("a change names something to change")
        return self


class ScheduleOut(BaseModel):
    """One of the reader's schedules. A schedule is its owner's alone, ADR-0029."""

    model_config = ConfigDict(frozen=True)

    schedule_id: UUID
    #: None once the view is deleted, which a run reports before the schedule pauses.
    view_id: UUID | None
    #: The view's name, or None where its owner can no longer open it, which a run reports.
    view_name: str | None
    screen_path: str | None
    export_path: str
    format: ReportFormat
    cadence: ReportCadence
    recipients: list[str]
    enabled: bool
    next_run_at: datetime
    created_at: datetime
    updated_at: datetime


class SchedulesOut(BaseModel):
    """The reader's schedules, and what the deployment does with what they render."""

    model_config = ConfigDict(frozen=True)

    #: False where no bucket is configured, so nothing renders, which the screen says.
    rendering: bool
    #: How long a rendered file is kept, in the server's words so the screen cannot drift. OPEN-15.
    retention: str
    #: Where a rendered file goes. Until OPEN-11 names a channel, nowhere: it is kept and listed.
    delivery: str
    schedules: list[ScheduleOut]


class ReportRunOut(BaseModel):
    """One run made for the reader: a file they exported, or one a schedule rendered for them."""

    model_config = ConfigDict(frozen=True)

    run_id: UUID
    schedule_id: UUID | None
    #: The route the file was made from, and its query without the format.
    view_path: str
    view_query: str
    format: ReportFormat
    status: ReportRunStatus
    rows: int
    bytes: int
    truncated: bool
    failure_cause: str | None
    failure_detail: str | None
    #: True when a file is kept and can be fetched again through the file route.
    has_file: bool
    made_at: datetime
    finished_at: datetime | None
    as_of: datetime | None
    collected_at: datetime | None


class LedgerMonthOut(BaseModel):
    """One closed month after a credited saving verified. FEAT-078, TASK-P11-008."""

    model_config = ConfigDict(frozen=True)

    #: The first of the month judged.
    month: date
    #: HELD, REGRESSED or UNOBSERVED.
    state: str
    #: Measured. Both absent exactly when the month is unobserved, never a zero.
    cost: Decimal | None
    saving: Decimal | None
    as_of: datetime
    collected_at: datetime


class LedgerCreditOut(BaseModel):
    """One verified saving, credited to its owner and team, with the months it held. FEAT-078.

    The owner and the person who closed it are named on their own credits and nowhere ranked:
    the ledger ranks teams, OPEN-27.
    """

    model_config = ConfigDict(frozen=True)

    credit_id: UUID
    recommendation_id: UUID
    account_id: str
    #: Null where the reader cannot see the recommendation's resource.
    resource_id: str | None
    #: The strongest team named for the resource when the credit was written, or none.
    team: str | None
    owner: str
    closed_by: str
    #: Measured, FEAT-029's before less after, thirty days each.
    verified_monthly_saving: Decimal
    verified_on: date
    #: Measured: the sum of the held months, never a projection.
    saving_held: Decimal
    months_held: int
    #: True once a month regressed, which stops the credit.
    regressed: bool
    months: list[LedgerMonthOut] = Field(default_factory=list)
    as_of: datetime
    collected_at: datetime


class LedgerCreditsOut(BaseModel):
    """One team's credits, or every credit the reader can see. FEAT-078."""

    model_config = ConfigDict(frozen=True)

    #: The team asked for; null with `every_team` when none was named.
    team: str | None
    every_team: bool
    credits: list[LedgerCreditOut]


class LedgerTeamOut(BaseModel):
    """A team by the savings it holds. FEAT-078. A team, never a person, OPEN-27."""

    model_config = ConfigDict(frozen=True)

    #: Null for the credits whose resource no source named a team for.
    team: str | None
    credits: int
    #: Measured: every held month of every credit, summed.
    saving_held: Decimal
    months_held: int
    #: How many of its credits a month regressed.
    regressed: int
    latest_month: date | None
    as_of: datetime
    collected_at: datetime


class LedgerOut(BaseModel):
    """Teams by the savings they hold, most first. FEAT-078, TASK-P11-008."""

    model_config = ConfigDict(frozen=True)

    teams: list[LedgerTeamOut]


# --- FinOps for AI, P13 ----------------------------------------------------------------------

#: How a figure was arrived at, P13 spec section 5.7: read from a report, or derived from two.
Basis = Literal["measured", "modelled"]


class AiSpendRowOut(BaseModel):
    """One group of the bill's AI lines, every figure with how it was arrived at. FEAT-085."""

    model_config = ConfigDict(frozen=True)

    #: The provider, model, token type, feature or caller the group is, as asked.
    name: str
    #: The provider of the group's lines, or `(several)` where they come from more than one.
    provider: str
    #: Measured: the bill's effective cost.
    cost: Decimal
    #: Null where nothing counted the group's tokens, which is unknown and never none.
    tokens: Decimal | None
    tokens_basis: Basis | None
    #: Null where no usage report or invocation log counted the group's requests.
    requests: int | None
    cost_per_1k_tokens: Decimal | None
    cost_per_1k_tokens_basis: Basis | None
    #: Modelled, always: the cost is the bill's and the requests are another report's.
    cost_per_request: Decimal | None
    cost_per_request_basis: Basis | None


class AiConnectionOut(BaseModel):
    """An AI provider organization the tenant connected. Never its key or the key's name."""

    model_config = ConfigDict(frozen=True)

    provider: str
    organization_id: str
    name: str


class AiSpendOut(BaseModel):
    """AI spend for a billing period, grouped as asked. FEAT-081, 083 and 085, TASK-P13-007."""

    model_config = ConfigDict(frozen=True)

    #: Null where the bill holds no AI line this reader can see.
    period: date | None
    group_by: str
    #: Measured. Null with the period, which is no AI spend seen and never nought.
    total_cost: Decimal | None
    rows: list[AiSpendRowOut]
    connected: list[AiConnectionOut]


class AiCallerOut(BaseModel):
    """One caller's tokens and requests on one model, and what they cost. FEAT-082."""

    model_config = ConfigDict(frozen=True)

    source: str
    account_id: str
    #: The Region for the invocation logs; a provider's project or workspace, empty for its default.
    workspace: str
    #: A provider's key, by its id and never the key; empty for the invocation logs.
    api_key_id: str
    #: An IAM ARN or a provider's user, either of which can name a person: class P. Empty where
    #: the source names no one, which a provider's key then stands for.
    caller: str
    application: str
    model: str
    tokens: int
    requests: int | None
    #: Modelled: the bill's unit cost for the same model, token type and day, spread over the
    #: caller's tokens. Null where the bill priced none of them, which is unknown, never free.
    modelled_cost: Decimal | None
    modelled_cost_basis: Basis


class AiCallersOut(BaseModel):
    """Who called which model in a billing period. FEAT-082, TASK-P13-007."""

    model_config = ConfigDict(frozen=True)

    period: date | None
    callers: list[AiCallerOut]


class AiGpuOut(BaseModel):
    """One GPU instance's hours and cost, and how busy it was. FEAT-084, TASK-P13-007."""

    model_config = ConfigDict(frozen=True)

    account_id: str
    region_id: str | None
    instance_id: str
    instance_type: str
    #: Measured, from the bill.
    hours: Decimal
    cost: Decimal
    days_billed: int
    days_published: int
    #: Measured, from the agent: the mean of the published days' averages and the highest peak.
    #: Null where the agent published nothing, which is not published and never nought percent.
    average_percent: Decimal | None
    peak_percent: Decimal | None
    #: published, partly published or not published.
    utilization: str


class AiGpuFleetOut(BaseModel):
    """The GPU instances the bill names in a billing period. FEAT-084, TASK-P13-007."""

    model_config = ConfigDict(frozen=True)

    period: date | None
    instances: list[AiGpuOut]


class SavingsRateMonthOut(BaseModel):
    """One billing month's effective savings rate, measured from the bill. FEAT-087."""

    model_config = ConfigDict(frozen=True)

    period: date
    #: Over the usage lines carrying a List Cost, so the two sums are over the same lines.
    effective_cost: Decimal
    list_cost: Decimal
    #: One minus Effective over List Cost. Null where no line carries a List Cost, never nought.
    rate: Decimal | None
    rate_basis: Basis
    lines: int
    lines_without_list_cost: int
    #: What the lines the rate leaves out cost, so a reader sees how much of the bill it covers.
    effective_cost_without_list_cost: Decimal
    reason: str | None


class SavingsRateOut(BaseModel):
    """The effective savings rate by billing month, the oldest first. FEAT-087, TASK-P14-004."""

    model_config = ConfigDict(frozen=True)

    months: list[SavingsRateMonthOut]


class HeldCommitmentOut(BaseModel):
    """One commitment the organization holds, as the service that sold it says. FEAT-086."""

    model_config = ConfigDict(frozen=True)

    kind: str
    commitment_id: str
    program: str
    account_id: str
    region_id: str | None
    applies_to: str | None
    #: A reservation's count, or a Savings Plan's amount an hour: exactly one, never both.
    quantity: int | None
    hourly_commitment: Decimal | None
    term_months: int
    payment_option: str
    upfront_amount: Decimal
    recurring_hourly: Decimal
    currency: str
    starts_at: datetime
    ends_at: datetime
    state: str


class CommitmentInventoryOut(BaseModel):
    """Every commitment held, the soonest ending first, and what cannot be read. TASK-P14-005."""

    model_config = ConfigDict(frozen=True)

    commitments: list[HeldCommitmentOut]
    #: Reserved services no API reads, named so none is mistaken for none held, ISS-295.
    unreadable: list[str]


class CalendarMonthOut(BaseModel):
    """What ends in one month, and its share of the hourly commitment held. FEAT-088."""

    model_config = ConfigDict(frozen=True)

    month: date
    commitments: list[str]
    hourly_value: Decimal
    #: Null where nothing is held to take a share of, never nought for want of a denominator.
    share: Decimal | None
    #: Measured for Savings Plans; modelled where a reservation's hourly value is in the month.
    basis: Basis
    over_limit: bool


class CommitmentCalendarOut(BaseModel):
    """The next months' endings against the tenant's ladder limit. FEAT-088, TASK-P14-005."""

    model_config = ConfigDict(frozen=True)

    months: list[CalendarMonthOut]
    ladder_limit: Decimal
    total_hourly_value: Decimal
    total_basis: Basis


class CommitmentPolicyOut(BaseModel):
    """What the tenant's purchase plans aim for. FEAT-088, OPEN-38."""

    model_config = ConfigDict(frozen=True)

    target_coverage: Decimal
    term_years: int
    payment_option: str
    ladder_limit: Decimal
    reason: str
    #: The person who set it, or None for the default nobody has changed.
    updated_by: str | None
    updated_at: datetime | None
    is_default: bool


class CommitmentPolicyIn(BaseModel):
    """A change to the policy. A reason is required, because a policy is a decision."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    target_coverage: Decimal = Field(gt=0, le=1)
    term_years: Literal[1, 3]
    payment_option: Literal["No Upfront", "Partial Upfront", "All Upfront"]
    ladder_limit: Decimal = Field(gt=0, le=1)
    reason: str = Field(min_length=3, max_length=500)


class PlanLineOut(BaseModel):
    """One purchase in one tranche of Meter's plan. Every figure modelled. FEAT-089."""

    model_config = ConfigDict(frozen=True)

    line_no: int
    program: str
    #: A family bound line's family and Region; null on a flexible line.
    instance_family: str | None
    region_id: str | None
    tranche_month: date
    hourly_commitment: Decimal
    discount_percent: Decimal
    #: The on demand spend an hour the commitment pays for.
    covers_hourly: Decimal
    monthly_saving: Decimal
    #: Below this share of today's usage the commitment costs more than it saves, FEAT-055.
    usage_floor_percent: Decimal
    upfront_cost: Decimal
    #: The commitment the inventory holds that is this line's purchase, once one is seen, FEAT-090.
    matched_commitment_id: str | None = None
    basis: Basis = "modelled"


class UnpricedShareOut(BaseModel):
    """A steady share no rate prices, named rather than priced at nothing. FEAT-089."""

    model_config = ConfigDict(frozen=True)

    #: Null for usage that moves between families and has no flexible rate.
    instance_family: str | None
    region_id: str | None
    steady_hourly: Decimal
    reason: str


class PurchasePlanOut(BaseModel):
    """Meter's plan for one month, under the policy it was drafted with. FEAT-089."""

    model_config = ConfigDict(frozen=True)

    plan_id: UUID
    plan_month: date
    status: str
    target_coverage: Decimal
    term_years: int
    payment_option: str
    ladder_limit: Decimal
    window_start: date
    window_end: date
    days_held: int
    #: Null where the bill held too few days for a baseline to mean anything.
    steady_hourly: Decimal | None
    held_hourly: Decimal | None
    target_hourly: Decimal | None
    #: What twelve tranches under the ladder could not place, said rather than dropped.
    beyond_hourly: Decimal | None
    no_purchase_reason: str | None
    currency: str
    unpriced: list[UnpricedShareOut]
    as_of: datetime
    collected_at: datetime


class ProviderRecommendationOut(BaseModel):
    """The provider's own purchase recommendation; its saving is its estimate. FEAT-089."""

    model_config = ConfigDict(frozen=True)

    kind: str
    program: str
    term_years: int
    payment_option: str
    lookback_days: int
    #: False where the provider looked and advises buying nothing; null where it failed.
    recommended: bool | None
    hourly_commitment: Decimal | None
    units: Decimal | None
    estimated_monthly_savings: Decimal | None
    estimated_savings_percent: Decimal | None
    upfront_cost: Decimal | None
    currency: str | None
    failure_cause: str | None
    failure_detail: str | None
    as_of: datetime
    collected_at: datetime


class PlanEventOut(BaseModel):
    """One step of a plan's lifecycle and who took it. FEAT-090, OPEN-36."""

    model_config = ConfigDict(frozen=True)

    from_status: str | None
    to_status: str
    #: The person, or the collector for a draft, a lapse or a verification.
    principal: str
    at: datetime
    note: str | None


class PurchasePlansOut(BaseModel):
    """Meter's plan beside the provider's recommendations, and why they differ. OPEN-35."""

    model_config = ConfigDict(frozen=True)

    plan: PurchasePlanOut | None
    #: Why there is no plan to show, where there is none.
    no_plan_reason: str | None
    lines: list[PlanLineOut]
    provider: list[ProviderRecommendationOut]
    difference: list[str]
    events: list[PlanEventOut] = []


class PlanTransitionIn(BaseModel):
    """A person's step in a plan's lifecycle. A note is required, because it is a decision."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    note: str = Field(min_length=3, max_length=500)
