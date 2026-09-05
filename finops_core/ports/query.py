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

from collections.abc import Iterable
from typing import Protocol, runtime_checkable

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
