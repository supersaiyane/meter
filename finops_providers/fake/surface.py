"""A query surface in memory, with a configurable failure plan.

The same idea as `FakeProvider`: the estate and the failures are data, so a test
asks for the condition it wants rather than mocking a client. What is different
here is that this port has two shapes of failure and they must not be conflated.

`discover` raises only when nothing at all could be enumerated. A single
instance that could not be read comes back in the list with `reachable` false
and a named cause, because omitting it makes the estate look smaller and cheaper
than it is.

Deterministic. No clock and no randomness, so a golden file written today still
matches tomorrow.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime

from finops_core.domain.query import (
    ControlAction,
    ControlOutcome,
    ControlRequest,
    QueryDefinition,
    QueryOrigin,
    SurfaceInstance,
    SurfaceKind,
)
from finops_core.errors import (
    AccessDenied,
    CollectionError,
    NotOptedIn,
    SchemaDrift,
    Throttled,
    Unreachable,
)

COLLECTOR = "query_audit"

#: The five causes an instance can name. `NoData` is absent because it renders
#: as a number and is therefore never a reason an instance is unreadable.
_CAUSES: dict[str, type[CollectionError]] = {
    "AccessDenied": AccessDenied,
    "Throttled": Throttled,
    "NotOptedIn": NotOptedIn,
    "Unreachable": Unreachable,
    "SchemaDrift": SchemaDrift,
}

#: Fixed, because a fake that reads the clock is a fake that produces a
#: different golden file every run.
AS_OF = datetime(2026, 9, 11, 4, 0, tzinfo=UTC)
COLLECTED_AT = datetime(2026, 9, 11, 9, 54, tzinfo=UTC)

#: One instance of every kind, and one of them unreachable. The two reserved
#: kinds have no adapter, TASK-P2-007 and 008 being descoped, and they are
#: modelled here anyway: a fake that only knows the implemented kind lets an
#: adapter quietly assume one.
INSTANCES: tuple[SurfaceInstance, ...] = (
    SurfaceInstance(
        surface_id="ws-0a1b2c3d",
        name="meter-prod-eu-west-1",
        kind=SurfaceKind.MANAGED_GRAFANA,
        location="g-0a1b2c3d.grafana-workspace.eu-west-1.amazonaws.com",
        reachable=False,
        unreachable_cause="AccessDenied",
    ),
    SurfaceInstance(
        surface_id="ws-4e5f6a7b",
        name="meter-prod-eu-west-2",
        kind=SurfaceKind.SELF_HOSTED_GRAFANA,
        location="https://grafana.internal.example",  # allow-hardcoded: a fake estate
    ),
    SurfaceInstance(
        surface_id="ws-8c9d0e1f",
        name="meter-staging-eu-west-2",
        kind=SurfaceKind.GRAFANA_CLOUD,
        location="https://example.grafana.net",  # allow-hardcoded: a fake estate
    ),
)


def _query(
    surface_id: str,
    fingerprint: str,
    *,
    origin: QueryOrigin = QueryOrigin.PANEL,
    element: str = "Error rate by service",
    refresh_seconds: int = 10,
    window_seconds: int = 2592000,
) -> QueryDefinition:
    """One definition. Keywords rather than a kwargs bag, so a typo is an error."""
    return QueryDefinition(
        as_of=AS_OF,
        collected_at=COLLECTED_AT,
        surface_id=surface_id,
        fingerprint=fingerprint,
        origin=origin,
        engine="logs_insights",
        query="fields @timestamp, @message | filter @message like /ERROR/",
        container="Platform overview",
        container_id="abc123",
        element=element,
        refresh_seconds=refresh_seconds,
        window_seconds=window_seconds,
        targets=("/aws/ecs/meter-api",),
        region="eu-west-2",  # allow-hardcoded: a fake fixture, not a deployed region
    )


#: Two queries on the reachable self hosted instance, one panel and one alert.
#: The alert matters: an alert rule runs on its interval whether anybody is
#: watching or not, and that is usually two orders of magnitude more runs.
QUERIES: Mapping[str, tuple[QueryDefinition, ...]] = {
    "ws-4e5f6a7b": (
        _query("ws-4e5f6a7b", "fp-panel-0001"),
        _query(
            "ws-4e5f6a7b",
            "fp-alert-0002",
            origin=QueryOrigin.ALERT,
            element="Error budget burn",
            refresh_seconds=60,
            window_seconds=86400,
        ),
    ),
    "ws-8c9d0e1f": (),
}


class FakeQuerySurface:
    """`QuerySurface` in memory. Every failure is asked for, never incidental."""

    def __init__(
        self,
        instances: tuple[SurfaceInstance, ...] | None = None,
        queries: Mapping[str, tuple[QueryDefinition, ...]] | None = None,
        failures: Mapping[str, type[CollectionError]] | None = None,
        control_failures: Mapping[str, type[CollectionError]] | None = None,
        supports: frozenset[ControlAction] | set[ControlAction] | None = None,
        discovery_failure: type[CollectionError] | None = None,
    ) -> None:
        self._instances = INSTANCES if instances is None else instances
        self._queries = dict(QUERIES if queries is None else queries)
        self._failures = dict(failures or {})
        self._control_failures = dict(control_failures or {})
        self._supports = (
            frozenset({ControlAction.OBSERVE, ControlAction.THROTTLE, ControlAction.DENY})
            if supports is None
            else frozenset(supports)
        )
        self._discovery_failure = discovery_failure

    # -- the failure plan --------------------------------------------------

    def _fail_if_planned(
        self, instance: SurfaceInstance, plan: Mapping[str, type[CollectionError]]
    ) -> None:
        planned = plan.get(instance.scope_key)
        if planned is not None:
            raise planned(
                scope_key=instance.scope_key,
                collector=COLLECTOR,
                detail="planned by the fake query surface",
            )

    # -- the port ----------------------------------------------------------

    def discover(self) -> Iterable[SurfaceInstance]:
        if self._discovery_failure is not None:
            raise self._discovery_failure(
                scope_key="discovery",
                collector=COLLECTOR,
                detail="planned by the fake query surface",
            )
        return self._instances

    def list_queries(self, instance: SurfaceInstance) -> Iterable[QueryDefinition]:
        if not instance.reachable:
            # The instance already carries why. Raising the same cause here
            # keeps a caller from treating an unreadable instance as empty.
            cause = instance.unreachable_cause or "Unreachable"
            raise _CAUSES.get(cause, AccessDenied)(
                scope_key=instance.scope_key,
                collector=COLLECTOR,
                detail="the instance was discovered unreachable",
            )
        self._fail_if_planned(instance, self._failures)
        # Absent means genuinely empty. A read that failed raised above.
        return self._queries.get(instance.surface_id, ())

    def apply_control(self, instance: SurfaceInstance, request: ControlRequest) -> ControlOutcome:
        self._fail_if_planned(instance, self._control_failures)

        if request.action is ControlAction.DENY and request.fingerprint in request.never_deny:
            # ISS-092. Honoured here as well as in the caller, because a
            # guardrail that only one layer enforces is a guardrail one refactor
            # away from being gone.
            return ControlOutcome(
                surface_id=instance.surface_id,
                fingerprint=request.fingerprint,
                requested=request.action,
                applied=False,
                detail="on the never deny list",
            )

        if request.action not in self._supports:
            return ControlOutcome(
                surface_id=instance.surface_id,
                fingerprint=request.fingerprint,
                requested=request.action,
                applied=False,
                detail=f"this surface cannot {request.action}",
            )

        requester = request.requested_by or "nobody"
        previous = next(
            (
                str(query.refresh_seconds)
                for query in self._queries.get(instance.surface_id, ())
                if query.fingerprint == request.fingerprint
            ),
            None,
        )
        return ControlOutcome(
            surface_id=instance.surface_id,
            fingerprint=request.fingerprint,
            requested=request.action,
            applied=True,
            detail=f"applied by the fake query surface, asked for by {requester}",
            previous=previous,
        )
