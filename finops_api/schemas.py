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
from uuid import UUID

from pydantic import BaseModel, ConfigDict, computed_field


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
    ) -> Meta:
        return cls(
            as_of=as_of,
            collected_at=collected_at,
            scope_coverage=CoverageOut(visible=visible, total=total, unit=unit),
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
    ticket_reference: str | None
    #: The working, so a reader can disagree with the verdict.
    rationale: str


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


class CommitmentsOut(BaseModel):
    """Both figures for one window, and never one derived from the other."""

    model_config = ConfigDict(frozen=True)

    window_start: date
    window_end: date
    commitments: list[CommitmentUseOut]
    coverage: list[CommitmentCoverageOut]
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
