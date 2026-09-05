"""Reading the queries a tool holds, and changing what one of them does.

Named `QuerySurface`, not `GrafanaSource`. Naming an abstraction after its first
implementation is how it ends up shaped like one vendor: the second
implementation then arrives with a method it cannot satisfy and a caller that
assumes a workspace id. FEAT-019 exists because the failure mode is not Grafana
specific, and this protocol is the line that keeps that true.

Three methods, and the split matters.

`discover` and `list_queries` are separate because discovery is cheap and
listing is not. An estate with forty workspaces is forty calls to enumerate and
several thousand to read, so a caller that only needs to know what exists should
not pay for what is in it.

`apply_control` is here rather than in a second port because the thing that can
change a query is always the thing that could read it. Splitting them would
produce two connections, two tokens and two sets of credentials to the same
place, and the authorization question would have to be answered twice.

Every method says which of the six causes it may raise. That is not decoration:
the taxonomy is closed and a caller writes one branch per cause, so a method
raising something undocumented is a branch nobody wrote.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Protocol, runtime_checkable

from finops_core.domain.query import (
    ControlOutcome,
    ControlRequest,
    QueryDefinition,
    SurfaceInstance,
)


@runtime_checkable
class QuerySurface(Protocol):
    """A tool that holds saved queries which cost money when they run."""

    def discover(self) -> Iterable[SurfaceInstance]:
        """Every instance this surface can see, reachable or not.

        An instance that could not be reached comes back with `reachable` false
        and a named cause, never omitted. Omitting it makes the estate look
        smaller and cheaper than it is, and the reader has no way to tell an
        absent workspace from one that does not exist.

        That is why this does not raise for a single unreachable instance. It
        raises only when the discovery itself failed, meaning nothing at all
        could be enumerated.

        Raises:
            AccessDenied: The credential may not enumerate instances.
            NotOptedIn: The service is not enabled in this account or region.
            Throttled: The provider rejected the call rate.
            Unreachable: The discovery endpoint did not answer.
            SchemaDrift: The instance list arrived in a shape this adapter does
                not recognise.
        """
        ...

    def list_queries(self, instance: SurfaceInstance) -> Iterable[QueryDefinition]:
        """Every saved query in one instance, panels and alert rules alike.

        Returns definitions, never the tool's own objects. A caller given a
        Grafana dashboard would grow a dependency on its shape, and the second
        surface would then have to produce one.

        An empty result means the instance genuinely holds no queries. It never
        means the read failed: a failure raises, because zero queries and an
        unreadable instance look identical on a screen and only one of them is
        good news.

        Raises:
            AccessDenied: The token may not read this instance's queries.
            NotOptedIn: The instance has not enabled the API this needs.
            Throttled: The provider rejected the call rate.
            Unreachable: The instance did not answer.
            SchemaDrift: A query arrived in a shape this adapter cannot read, or
                a listing was truncated without saying so.
        """
        ...

    def apply_control(self, instance: SurfaceInstance, request: ControlRequest) -> ControlOutcome:
        """Change what one query does, and report what actually happened.

        Returns an outcome with `applied` false when the surface cannot do what
        was asked. That is a normal answer rather than an error: a surface with
        no throttle should say so, so the caller can try a different control
        instead of abandoning the run.

        The outcome carries `previous`, so the change can be undone.
        TASK-P2-019 requires every rewrite to be reversible, and a control that
        cannot say what it replaced is a control nobody will dare apply.

        Raises:
            AccessDenied: The token may read this instance but not change it,
                which is the common case and is distinct from an outcome of
                `applied` false.
            NotOptedIn: The instance exposes no write API at all.
            Throttled: The provider rejected the call rate.
            Unreachable: The instance did not answer.
            SchemaDrift: The instance accepted the change and returned something
                this adapter cannot confirm from.
        """
        ...


@runtime_checkable
class Classified(Protocol):
    """What one target turned out to be, as an adapter needs to see it.

    Read only members. Declared as variables they would be invariant, and a
    frozen dataclass, which is what every value in this domain is, could not
    satisfy the protocol.
    """

    @property
    def engine(self) -> str: ...

    @property
    def query(self) -> str: ...

    @property
    def region(self) -> str | None: ...

    @property
    def log_groups(self) -> tuple[str, ...]: ...


@runtime_checkable
class QueryParser(Protocol):
    """Reading meaning out of a vendor's saved query.

    Declared here, and implemented above, because of the layer order in
    `pyproject.toml`: `finops_query` sits above `finops_providers` precisely
    because it reads what an adapter fetched. An adapter that imported it would
    invert that, and the import contract says so out loud.

    So the adapter names the interface it needs and a collector supplies the
    implementation. The same inversion as every other port here: the thing that
    talks to a vendor depends on an abstraction, never on the layer above it.
    """

    def classify(self, target: Mapping[str, Any], panel_datasource: Any = None) -> Classified:
        """What engine this target runs on, and what it runs against."""
        ...

    def iter_panels(self, panels: Any) -> Iterable[Mapping[str, Any]]:
        """Every panel, including the ones nested inside a row."""
        ...

    def normalise(self, text: str | None) -> str:
        """Query text reduced to a comparison key.

        Comments, whitespace and case only. It is here because an adapter has to
        key what it observed the same way the analysis looks it up, and an
        adapter may not import the analysis: `finops_query` sits above
        `finops_providers` precisely because it reads what an adapter fetched.
        """
        ...

    def refresh_seconds(self, raw: Any) -> int:
        """A dashboard refresh interval in seconds. Zero means no auto refresh."""
        ...

    def relative_range_seconds(self, raw: Any) -> int | None:
        """How far back a range looks. None for an absolute range."""
        ...

    def fingerprint(
        self,
        *,
        account_id: str,
        workspace_name: str,
        dashboard_uid: str,
        panel: str,
        ref_id: str,
        query: str,
    ) -> str:
        """A stable identifier for one query, across days and variable values."""
        ...


@runtime_checkable
class QueryEvidence(Protocol):
    """What an account actually executed, as opposed to what it has defined.

    A definition says a panel refreshes every ten seconds. This says how many
    times it really ran. The difference between those two is the whole of
    FEAT-013: a modelled Logs Insights cost rests on an assumed ingestion rate
    that can be an order of magnitude out, and a measured one is what the
    account did.

    **Absent evidence is not zero.** A query with no observations comes back
    absent from the bundle, and the caller leaves the finding modelled. Writing
    a zero would say the query never ran, which is a claim, and the honest
    answer is that nobody watched.
    """

    def observations(
        self, *, account_id: str, region: str, lookback_days: int
    ) -> Mapping[str, Any]:
        """Executions seen in the window, in the shape `finops_query.ownership` reads.

        Three keys, and the shape is fixed by `match_observed` and the two
        `measure_*` functions rather than chosen here:

        `logs` maps a normalised query string to a record of what it did:
        `runs`, `bytes`, `runs_bytes` and `log_groups`. From CloudTrail
        `StartQuery` for the run count, and from `logs:DescribeQueries` for the
        bytes where history still holds them.

        `gmd_by_metric` maps `namespace|metric` to a `GetMetricData` call count.
        CloudTrail identifies those calls by account and region and never by
        panel, which is why this is the weakest attribution here and part of why
        ISS-093 exists.

        `lookback_days` is the window the counts cover, so a caller can turn a
        total into a rate without assuming the window it asked for is the window
        it got.

        Raises:
            AccessDenied: The credential may not read CloudTrail or query history.
            NotOptedIn: CloudTrail is not enabled in this account or region.
            Throttled: The provider rejected the call rate.
            Unreachable: The endpoint did not answer.
            SchemaDrift: An event arrived in a shape this adapter cannot read.
        """
        ...
