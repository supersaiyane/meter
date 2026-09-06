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
    #: What this query cost on each day it was audited, oldest first. One
    #: point means it has been seen once, which is not a flat trend and must
    #: not be drawn as one.
    history: list[CostPointOut]
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
