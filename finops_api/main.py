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
from pathlib import Path
from typing import Any, get_origin

from fastapi import APIRouter, Depends, FastAPI
from fastapi.routing import APIRoute
from sqlalchemy import Engine, text
from sqlalchemy.engine import Connection

from finops_api.deps import get_connection
from finops_api.guards import ScopeViolationError
from finops_api.middleware import RequestIdMiddleware
from finops_api.schemas import CollectorHealth, Envelope, HealthOut
from finops_core.config import Settings, load_settings
from finops_core.constants import STALE_AFTER_CADENCE_MULTIPLE

LOGGER = logging.getLogger("meter.api")

#: Paths that legitimately do not carry the data envelope. Operational endpoints
#: describe the service rather than reporting a figure, and listing them here
#: means the exemption is a decision somebody made rather than a route that
#: quietly slipped through.
#: Routes that return something other than a data payload, so the envelope does not
#: apply to them.
#:
#: `/api/v1/cost/export` is the only one that returns tenant data, and it is exempt
#: because it returns a file rather than a payload: a JSON wrapper round a CSV is a
#: wrapper somebody has to strip by hand before a spreadsheet will open it. The
#: envelope exists so a reader can tell stale from fresh, and that requirement is met
#: instead by `as_of` and `collected_at` columns on every row of the file, which is
#: stronger than a header, because a spreadsheet gets mailed on and pasted into a deck
#: and the cells are what survive that. `tests/api/test_cost_export_route.py` asserts
#: the columns are there.
ENVELOPE_EXEMPT = frozenset(
    {
        "/healthz",
        "/openapi.json",
        "/docs",
        "/docs/oauth2-redirect",
        "/redoc",
        "/api/v1/cost/export",
    }
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


def p1_routers() -> tuple[APIRouter, ...]:
    """The cost surface, from the P1 spec's section 8 table.

    Four of the five screens the navigation group promises. Anomalies,
    commitments and the export read data no collector produces yet, and a route
    over an empty table answers a question with a confident nothing.
    """
    from finops_api.routes import cost

    return (cost.router,)


def p3_routers() -> tuple[APIRouter, ...]:
    """The rightsizing surface, from the P3 spec's section 8 table.

    All six. Unlike P1 and P2 at the same stage, every table behind these has a
    collector, so none of them answers a question with a confident nothing.
    """
    from finops_api.routes import waste

    return (waste.router,)


def p2_routers() -> tuple[APIRouter, ...]:
    """The query governance routes, from the P2 spec's section 8.2 table.

    Three of the eight it names. The rest read data no collector produces yet,
    and a route over an empty table answers a question with a confident nothing.
    """
    from finops_api.routes import query

    return (query.router,)


def p4_routers() -> tuple[APIRouter, ...]:
    """The inventory and topology routes, from the P4 spec's section 8 table.

    Three of them. All three read tables a collector writes, so none answers a question
    with a confident nothing, which is the test the P1 and P2 route sets did not all pass
    at the same stage.
    """
    from finops_api.routes import inventory

    return (inventory.router,)


def p5_routers() -> tuple[APIRouter, ...]:
    """The quota routes, from the P5 spec's section 8 table.

    All three, and none of them writes. The set has no counterpart to the two P2 routes
    that write, and that absence is spec section 6 rather than an omission: a quota
    increase is a write into a member account, so Meter drafts it and hands it over.
    """
    from finops_api.routes import quotas

    return (quotas.router,)


def p7_routers() -> tuple[APIRouter, ...]:
    """The assistant routes, from the P7 spec's section 8 table.

    All four: ask, the asker's exchanges, the digests and the asker's redactions. Each
    arrived with the table it reads, TASK-P7-010, 012 and 013.
    """
    from finops_api.routes import assistant

    return (assistant.router,)


def _assistant(app: FastAPI, settings: Settings, model: Any) -> Any:
    """The assistant this application answers with, or None where no model was given.

    The toolbox is built here, around this application, so a tool call goes back through
    the same routes, dependency and guard as the screens, as the asker. ADR-0009.
    """
    if model is None:
        return None
    if not settings.assistant_model_id.strip():
        raise RuntimeError(
            "a model was given with no METER_ASSISTANT_MODEL_ID, so no exchange could record "
            "what it was sent to"
        )
    from finops_api.assistant import Assistant
    from finops_api.toolbox import ApiToolbox, InProcessTransport

    return Assistant(
        model=model,
        model_id=settings.assistant_model_id,
        toolbox_for=lambda token: ApiToolbox(InProcessTransport(app), token),
        input_per_million=settings.assistant_input_usd_per_million_tokens,
        output_per_million=settings.assistant_output_usd_per_million_tokens,
        monthly_token_budget=settings.assistant_monthly_token_budget,
    )


def create_app(
    engine: Engine,
    entitlements: Any,
    signer: Any,
    settings: Settings | None = None,
    health_check: Any = None,
    remediation_control: Any = None,
    #: Where an accepted recommendation goes. None is the current default and
    #: is not a failure: OPEN-05 is unanswered and the lifecycle works without
    #: one, carrying no ticket reference.
    tickets: Any = None,
    #: The model behind the assistant. None is the default and is not a failure: no model
    #: has been chosen, OPEN-10, and every question then says the assistant is not enabled.
    language_model: Any = None,
    extra_routers: tuple[APIRouter, ...] = (),
    include_p0_routes: bool = True,
) -> FastAPI:
    """Build the application, refusing to start on a broken envelope contract."""
    # `load_settings`, not the request dependency of the same idea. Assembly
    # happens once and has no request, and calling the dependency here is what
    # stopped the container booting: every test passes settings explicitly, so
    # nothing caught it until the image ran.
    resolved = settings or load_settings()
    app = FastAPI(title="Meter", version="0", docs_url="/docs")
    app.state.engine = engine
    app.state.entitlements = entitlements
    app.state.signer = signer
    app.state.tickets = tickets
    app.state.settings = resolved
    app.state.health_check = health_check
    # Absent by default, and a route that needs it refuses rather than pretends.
    # No surface adapter can write today anyway, ISS-166, so a default that
    # silently reported success would be the worst of both.
    app.state.remediation_control = remediation_control
    app.state.assistant = _assistant(app, resolved, language_model)
    app.add_middleware(RequestIdMiddleware)
    routers = (
        build_router(),
        *(p0_routers() if include_p0_routes else ()),
        *(p1_routers() if include_p0_routes else ()),
        *(p3_routers() if include_p0_routes else ()),
        *(p2_routers() if include_p0_routes else ()),
        *(p4_routers() if include_p0_routes else ()),
        *(p5_routers() if include_p0_routes else ()),
        *(p7_routers() if include_p0_routes else ()),
        *extra_routers,
    )
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


def bootstrap() -> FastAPI:
    """Build the application the container runs, from the environment alone.

    A factory rather than a module level `app`, so importing this module for a
    test, a migration or the documentation gate does not open a database
    connection as a side effect of the import.

    The identity provider is chosen by configuration and the choice is not
    silent: an unrecognised one raises here rather than falling back to the
    local file, because a fallback to local authentication in an environment
    that asked for something else is an authentication bypass. `Settings`
    already refuses to load with the local provider in production.
    """
    from sqlalchemy import create_engine

    from finops_api.identity.local_config import LocalConfigIdentityProvider
    from finops_api.identity.session import SessionSigner
    from finops_core.constants import LOCAL_IDENTITY_PROVIDER
    from finops_providers.aws.language_model import language_model

    settings = load_settings()
    if settings.identity_provider != LOCAL_IDENTITY_PROVIDER:
        raise RuntimeError(
            f"identity provider {settings.identity_provider!r} is configured but not "
            "implemented. TASK-P0-012 delivered the local provider only."
        )

    provider = LocalConfigIdentityProvider(
        path=Path(settings.local_auth_file),
        tenant_id=settings.local_tenant_id,
        cache_ttl_minutes=settings.entitlement_cache_ttl_minutes,
    )
    return create_app(
        engine=create_engine(settings.database_url, pool_pre_ping=True),
        entitlements=provider,
        signer=SessionSigner(settings.session_signing_key, ttl_hours=settings.session_ttl_hours),
        settings=settings,
        language_model=language_model(settings),
    )
