"""The application, and the two rules it refuses to start without.

Constraint 8 in CLAUDE.md makes the HTTP API the single enforcement point, so
what it guarantees has to be structural rather than remembered.

Every data route returns an `Envelope`, and `create_app` checks that at startup
rather than trusting review. The freshness contract is worth nothing unless it
is universal: one route returning bare data is one screen that shows a number
with no way to tell whether it is stale, partial or a failure wearing a zero.

`/healthz` reports whether the database is reachable and whether ingestion is
still running, not whether the process is alive. A process that answers while
the database is down, or while collection stopped six hours ago, will serve
confident and wrong numbers, and a liveness only probe makes that invisible to
exactly the system meant to notice.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Iterator
from typing import Any, get_origin

from fastapi import APIRouter, Depends, FastAPI
from fastapi.routing import APIRoute
from sqlalchemy import Engine, text
from sqlalchemy.engine import Connection

from finops_api.deps import get_connection, get_settings
from finops_api.guards import ScopeViolationError
from finops_api.middleware import RequestIdMiddleware
from finops_api.schemas import CollectorHealth, Envelope, HealthOut
from finops_core.config import Settings
from finops_core.constants import STALE_AFTER_CADENCE_MULTIPLE

LOGGER = logging.getLogger("meter.api")

#: Paths that legitimately do not carry the data envelope. Operational endpoints
#: describe the service rather than reporting a figure, and listing them here
#: means the exemption is a decision somebody made rather than a route that
#: quietly slipped through.
ENVELOPE_EXEMPT = frozenset(
    {"/healthz", "/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}
)

HEALTHY = "ok"
DEGRADED = "degraded"


class EnvelopeContractError(RuntimeError):
    """A data route was registered without the response envelope."""


def returns_envelope(response_model: Any) -> bool:
    """True when the declared model is the envelope, parameterised or not.

    `Envelope[list[str]]` is a pydantic generic, which builds a concrete model
    class rather than a typing alias, so `get_origin` reports nothing for it.
    Pydantic records the origin separately, and reading that is what makes the
    check see a parameterised envelope as one.
    """
    if response_model is Envelope or get_origin(response_model) is Envelope:
        return True
    metadata = getattr(response_model, "__pydantic_generic_metadata__", None)
    if metadata is None:
        return False
    return bool(metadata.get("origin") is Envelope)


def iter_api_routes(routers: Iterable[APIRouter]) -> Iterator[APIRoute]:
    """Every API route in the routers this application registers.

    The routers are inspected rather than the finished application. FastAPI
    wraps an included router instead of flattening its routes into
    `app.routes`, so walking the app means reaching through a private attribute
    that changes between versions. Worse, when that walk finds nothing it
    reports success over an application it never examined, which is the one
    failure a check like this must not have.
    """
    for router in routers:
        for route in router.routes:
            if isinstance(route, APIRoute):
                yield route


def assert_envelope_contract(routers: Iterable[APIRouter]) -> None:
    """Refuse to start if a data route returns something bare.

    Checked here rather than in review, because the route that breaks this is
    the one somebody adds in a hurry a year from now.
    """
    routes = list(iter_api_routes(routers))
    if not routes:
        raise EnvelopeContractError(
            "The envelope contract found no routes to check, so it would pass over "
            "anything. Something about how routes are registered has changed."
        )
    offenders = [
        route.path
        for route in routes
        if route.path not in ENVELOPE_EXEMPT and not returns_envelope(route.response_model)
    ]
    if offenders:
        raise EnvelopeContractError(
            "These routes return data without the meta envelope, so a reader cannot "
            "tell stale from fresh or a failure from a zero: " + ", ".join(sorted(offenders))
        )


def collector_health(connection: Connection) -> tuple[CollectorHealth, ...]:
    """How long since each enabled collector last succeeded, against its cadence.

    The worst tenant is the one reported. An operator needs to know that some
    tenant has stopped collecting, and an average across tenants hides exactly
    the case worth paging about.
    """
    rows = connection.execute(
        text(
            "SELECT s.collector, MAX(s.cadence_seconds) AS cadence, "
            "MIN(latest.finished_at) AS last_success, "
            "EXTRACT(EPOCH FROM (now() - MIN(latest.finished_at))) AS age "
            "FROM collector_schedule s LEFT JOIN LATERAL ("
            "  SELECT MAX(r.finished_at) AS finished_at FROM ingest_run r "
            "  WHERE r.tenant_id = s.tenant_id AND r.collector = s.collector "
            "  AND r.status IN ('SUCCEEDED', 'PARTIAL')"
            ") latest ON true WHERE s.is_enabled GROUP BY s.collector ORDER BY s.collector"
        )
    ).mappings()

    health: list[CollectorHealth] = []
    for row in rows:
        cadence = int(row["cadence"])
        age = None if row["age"] is None else float(row["age"])
        # Never collected is stale, not healthy. An absent number is the case
        # this endpoint exists to surface.
        stale = age is None or age > cadence * STALE_AFTER_CADENCE_MULTIPLE
        health.append(
            CollectorHealth(
                collector=str(row["collector"]),
                last_success_at=row["last_success"],
                cadence_seconds=cadence,
                age_seconds=age,
                is_stale=stale,
            )
        )
    return tuple(health)


def build_router() -> APIRouter:
    router = APIRouter()

    @router.get("/healthz", response_model=HealthOut)
    def healthz(connection: Connection = Depends(get_connection)) -> HealthOut:
        try:
            connection.execute(text("SELECT 1"))
            reachable = True
            collectors = collector_health(connection)
        except Exception:
            LOGGER.exception("health check could not reach the database")
            reachable = False
            collectors = ()
        stale = any(entry.is_stale for entry in collectors)
        return HealthOut(
            status=HEALTHY if reachable and not stale else DEGRADED,
            database_reachable=reachable,
            collectors=collectors,
        )

    return router


def p0_routers() -> tuple[APIRouter, ...]:
    """The seven P0 routes, from the spec's section 8 table."""
    from finops_api.routes import accounts, ingest, me, org, platform

    return (me.router, accounts.router, org.router, ingest.router, platform.router)


def create_app(
    engine: Engine,
    entitlements: Any,
    signer: Any,
    settings: Settings | None = None,
    health_check: Any = None,
    extra_routers: tuple[APIRouter, ...] = (),
    include_p0_routes: bool = True,
) -> FastAPI:
    """Build the application, refusing to start on a broken envelope contract."""
    resolved = settings or get_settings()
    app = FastAPI(title="Meter", version="0", docs_url="/docs")
    app.state.engine = engine
    app.state.entitlements = entitlements
    app.state.signer = signer
    app.state.settings = resolved
    app.state.health_check = health_check
    app.add_middleware(RequestIdMiddleware)
    routers = (build_router(), *(p0_routers() if include_p0_routes else ()), *extra_routers)
    # Checked before anything is registered, so a broken contract fails at
    # construction rather than at the first request.
    assert_envelope_contract(routers)
    for router in routers:
        app.include_router(router)

    @app.exception_handler(ScopeViolationError)
    async def _scope_violation(_request: Any, failure: ScopeViolationError) -> Any:
        # A programming error, not a client error. The response says nothing
        # useful on purpose, and the log carries the detail.
        from fastapi.responses import JSONResponse

        LOGGER.error("a read was attempted without a scope: %s", failure)
        return JSONResponse(status_code=500, content={"detail": "internal error"})

    return app
