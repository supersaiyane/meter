"""A query somewhere costs money, and something can be done about it.

Deliberately says nothing about Grafana. The pattern is a visualisation tool
holding saved queries that re run on a timer against a metered backend, and
Grafana is the first instance of it rather than the shape of it. FEAT-019
exists because the failure mode is not Grafana specific: Kibana, Superset,
Looker and Athena saved queries all do the same thing, and a domain named after
the first one has to be rewritten for the second.

So the vocabulary here is `QuerySurface`, `SurfaceInstance` and
`QueryDefinition`. A Grafana workspace is a surface instance; a panel target and
an alert rule are both query definitions. Nothing in this module knows which.

`QueryDefinition` is a `Fact` because it is a claim about the world at a time.
The definition was true when it was read and can change five minutes later when
somebody edits the dashboard, which is exactly what constraint 4 exists for: a
figure computed from a definition read last week is not a figure about today.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from finops_core.domain.fact import Fact


class SurfaceKind(StrEnum):
    """What kind of tool holds the queries.

    A closed set, and it grows by adding a member here and an adapter, never by
    passing a free string. An unrecognised kind must be a value error at the
    boundary rather than a row nobody can group by later.
    """

    #: Amazon Managed Grafana. The only one implemented, per OPEN-04 re
    #: answered 2026-09-02.
    MANAGED_GRAFANA = "managed_grafana"
    #: Reserved. Both were planned as TASK-P2-007 and TASK-P2-008 and are
    #: descoped rather than deleted, so the shape they would take is recorded.
    SELF_HOSTED_GRAFANA = "self_hosted_grafana"
    GRAFANA_CLOUD = "grafana_cloud"


class QueryOrigin(StrEnum):
    """Why the query runs, which decides how often it runs.

    The single largest term in any cost figure. A panel runs while somebody is
    watching it; an alert rule runs on its interval whether anybody is watching
    or not, and the difference between those two is usually two orders of
    magnitude.
    """

    PANEL = "panel"
    ALERT = "alert"
    #: Run by a person, found in execution history with no definition behind it.
    #: Real cost with nothing to attribute it to, and dropping it understates
    #: the account.
    ADHOC = "adhoc"


class ControlAction(StrEnum):
    """What can be done to a query that costs too much.

    Ordered by how much it takes away. `OBSERVE` is the default and changes
    nothing, which matters: ISS-020 records that a tool which only reports is a
    post mortem, and the answer to that is not to make enforcement the default.
    """

    OBSERVE = "observe"
    #: Slow it down. The query still runs and still answers.
    THROTTLE = "throttle"
    #: Refuse it. Reversible, and it cuts somebody off mid incident if applied
    #: carelessly, which is ISS-092.
    DENY = "deny"


@dataclass(frozen=True, kw_only=True)
class SurfaceInstance:
    """One place queries live: a workspace, a cluster, a project.

    `reachable` is a first class field rather than an absence. An instance we
    could not read must appear in the list saying so, because leaving it out
    makes an estate look smaller and cheaper than it is. ISS-090 is the same
    argument for a self hosted instance in a private subnet.
    """

    surface_id: str
    name: str
    kind: SurfaceKind
    #: Where the queries are read from. An endpoint, a URL, a connection name.
    #: Opaque to the domain on purpose.
    location: str
    reachable: bool = True
    #: Why not, when `reachable` is false. One of the six causes, by name.
    unreachable_cause: str | None = None

    def __post_init__(self) -> None:
        if not self.reachable and not self.unreachable_cause:
            raise ValueError(
                f"{self.surface_id} is unreachable and names no cause. "
                "An unexplained absence is the failure this field exists to prevent."
            )

    @property
    def scope_key(self) -> str:
        """How a failure against this instance is recorded and reported."""
        return f"{self.kind}:{self.surface_id}"


@dataclass(frozen=True, kw_only=True)
class QueryDefinition(Fact):
    """One saved query, as it was defined when it was read.

    Carries no cost. Pricing is `finops_query.cost_model`'s job and it takes
    this as input, which is what stops a new surface needing a new cost model.
    """

    surface_id: str
    #: Stable across days and across the values a template variable takes. See
    #: `finops_query.policy.fingerprint`.
    fingerprint: str
    origin: QueryOrigin
    #: What executes it: logs_insights, metric_search, metrics_insights,
    #: prometheus. A string rather than an enum, because a surface can host an
    #: engine this project has never heard of and refusing to represent it would
    #: mean dropping the query rather than reporting it unpriced.
    engine: str
    query: str
    #: Where it came from, for a person to find and fix. A dashboard and a
    #: panel, or an alert rule and its title.
    container: str = ""
    container_id: str = ""
    #: The folder the container sits in. Ownership is mapped per folder, because
    #: a team owns a folder and edits many dashboards inside it, so a per
    #: dashboard mapping would be a list nobody keeps current.
    folder_uid: str = ""
    element: str = ""
    ref_id: str = ""
    #: How often it re runs, in seconds. Zero means no automatic refresh.
    refresh_seconds: int = 0
    #: How far back it looks, in seconds. None means an absolute range, which is
    #: an unknown window rather than a zero one.
    window_seconds: int | None = None
    #: What it reads. Log groups, a namespace, a data source name.
    targets: tuple[str, ...] = ()
    region: str | None = None
    #: The principal that last ran it, where execution history says so. None
    #: means unowned, which ISS-021 records as the state in which nothing is
    #: ever fixed.
    last_run_by: str | None = None


@dataclass(frozen=True, kw_only=True)
class ControlOutcome:
    """What a control actually did, which is not always what was asked.

    `applied` false with a reason is a normal answer, not an error. A surface
    that cannot throttle should say so rather than raise, because the caller's
    next move is to try a different control rather than to abandon the run.
    """

    surface_id: str
    fingerprint: str
    requested: ControlAction
    applied: bool
    detail: str = ""
    #: What the state was before, so the change can be undone. TASK-P2-019
    #: requires every rewrite to be reversible.
    previous: str | None = None


@dataclass(frozen=True, kw_only=True)
class ControlRequest:
    """An instruction to change one query's behaviour."""

    fingerprint: str
    action: ControlAction
    #: For THROTTLE, the floor to raise the refresh interval to. Ignored by the
    #: other actions.
    minimum_refresh_seconds: int = 0
    #: Who asked, recorded on the outcome. A control with no requester is a
    #: change nobody can be asked about.
    requested_by: str = ""
    reason: str = ""
    #: Queries a control must never be applied to, whatever the policy says.
    #: ISS-092: a deny that cuts an engineer off from Logs Insights during an
    #: incident is worse than the cost it prevented.
    never_deny: frozenset[str] = field(default_factory=frozenset)
