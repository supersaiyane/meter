"""A fixture backed path must not be a real route.

The frontend renders invented numbers for every path in `FIXTURE_SURFACES` and
says so on screen. The moment a route is registered the invention has to stop,
and review is not a mechanism for noticing that. This test is.

Route modules are discovered rather than listed, so a sub project adding
`finops_api/routes/query.py` is covered without editing this file. The routers
are inspected rather than a built application, for the reason given in
`finops_api.main.iter_api_routes`: walking a finished app reaches through a
private attribute, and a walk that finds nothing reports success over an
application it never examined.
"""

from __future__ import annotations

import importlib
import pkgutil
import re
from pathlib import Path

from fastapi import APIRouter

import finops_api.routes
from finops_api.main import build_router, iter_api_routes

SEAM = Path(__file__).resolve().parents[2] / "finops-web" / "src" / "api" / "fixtureSeam.ts"


def declared_fixture_templates() -> set[str]:
    """The templates the frontend still serves from a fixture."""
    text = SEAM.read_text(encoding="utf-8")
    block = text.split("FIXTURE_SURFACES", 1)[1].split("]", 1)[0]
    return set(re.findall(r"'(/api/v1/[^']+)'", block))


def registered_route_templates() -> set[str]:
    """Every path template any route module in the application declares."""
    routers: list[APIRouter] = [build_router()]
    for module in pkgutil.iter_modules(finops_api.routes.__path__):
        imported = importlib.import_module(f"finops_api.routes.{module.name}")
        router = getattr(imported, "router", None)
        if isinstance(router, APIRouter):
            routers.append(router)
    return {route.path for route in iter_api_routes(routers)}


def test_the_guard_examined_something() -> None:
    """A check that finds nothing must not report success.

    Without this, deleting a route module or renaming `router` would turn the
    test below into a green light over an application it never looked at.
    """
    assert len(registered_route_templates()) >= 7


def test_the_seam_declares_at_least_one_template() -> None:
    """If parsing breaks, the set reads as empty and everything looks fine."""
    assert declared_fixture_templates()


def test_no_fixture_path_is_a_registered_route() -> None:
    still_invented = declared_fixture_templates() & registered_route_templates()
    assert not still_invented, (
        "These paths are live routes but the frontend still serves fixtures for "
        f"them: {sorted(still_invented)}. Remove them from FIXTURE_SURFACES in {SEAM}."
    )
