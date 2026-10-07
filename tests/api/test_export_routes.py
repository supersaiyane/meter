"""Every list route a screen reads answers as a file. FEAT-067, TASK-P8-009.

Held the way the MCP drift gate holds its tools: every GET route the API defines either carries
the export dependency or is named here with the reason it does not. A list route added without
`@exportable` fails here rather than in front of the person who pressed Export.
"""

from __future__ import annotations

import importlib
import pkgutil
import types
import typing
from collections.abc import Mapping

from fastapi.routing import APIRoute
from pydantic import BaseModel

import finops_api.routes as routes
from finops_api.exports import ExportDependency, ExportSpec
from finops_api.exports.cells import columns_of

#: Routes that answer with something other than a table of rows, and why.
EXEMPT: Mapping[str, str] = {
    "/api/v1/me": "The reader's own session, one object with nothing to tabulate",
    "/api/v1/inventory/topology/{node_id}": "A graph walk from one node, drawn and not tabled",
    "/api/v1/inventory/nodes/{node_id}/blast-radius": "One node's blast radius, a judgement",
    "/api/v1/inventory/nodes/{node_id}": "One resource's detail page",
    "/api/v1/inventory/coverage": "The coverage banner on every screen, not a screen's table",
    "/api/v1/inventory/roots": "The starting points the topology map offers, not a table",
    "/api/v1/query/findings/{finding_id}": "One finding's detail page",
    "/api/v1/governance/quotas/{service_code}/{quota_code}": "One quota's detail page",
    "/api/v1/waste/recommendations/{recommendation_id}": "One recommendation's detail page",
    "/api/v1/reports/views": "Saved views are configuration, and each exports from its own screen",
    "/api/v1/reports/views/{view_id}": "One saved view, configuration that opens a screen",
    "/api/v1/reports/schedules": "The reader's schedules, configuration that renders a route",
    "/api/v1/reports/runs": "The reader's run records, each of which is already a file of its own",
    "/api/v1/reports/runs/{run_id}/file": "A stored report, which is the file itself",
}


def every_get_route() -> list[APIRoute]:
    found: list[APIRoute] = []
    for module in pkgutil.iter_modules(routes.__path__):
        loaded = importlib.import_module(f"{routes.__name__}.{module.name}")
        router = getattr(loaded, "router", None)
        if router is not None:
            found.extend(
                route
                for route in router.routes
                if isinstance(route, APIRoute) and "GET" in (route.methods or set())
            )
    return found


def spec_of(route: APIRoute) -> ExportSpec | None:
    for dependency in route.dependant.dependencies:
        if isinstance(dependency.call, ExportDependency):
            return dependency.call.spec
    return None


def models_in(annotation: object) -> set[type[BaseModel]]:
    """The models an annotation holds, and the models their fields hold, one level down."""
    if isinstance(annotation, type) and not isinstance(annotation, types.GenericAlias):
        if not issubclass(annotation, BaseModel):
            return set()
        found: set[type[BaseModel]] = {annotation}
        for info in annotation.model_fields.values():
            for inner in (info.annotation, *typing.get_args(info.annotation)):
                if isinstance(inner, type) and issubclass(inner, BaseModel):
                    found.add(inner)
        return found
    found = set()
    for argument in typing.get_args(annotation):
        found |= models_in(argument)
    return found


def exported() -> list[tuple[APIRoute, ExportSpec]]:
    return [(route, spec) for route in every_get_route() if (spec := spec_of(route)) is not None]


def test_there_are_routes_to_hold() -> None:
    # A collection that found nothing would pass every test below.
    assert len(every_get_route()) > 30
    assert len(exported()) > 25


def test_every_list_route_a_screen_reads_answers_as_a_file() -> None:
    missing = [
        route.path
        for route in every_get_route()
        if route.path not in EXEMPT and spec_of(route) is None
    ]
    assert not missing, f"mark these @exportable or exempt them with a reason: {missing}"


def test_every_exemption_is_a_route_that_exists_and_is_not_exported() -> None:
    paths = {route.path: route for route in every_get_route()}
    assert not [path for path in EXEMPT if path not in paths], "an exemption outlived its route"
    assert not [path for path in EXEMPT if spec_of(paths[path]) is not None]
    assert all(len(reason) > 20 for reason in EXEMPT.values())


def test_every_export_is_of_rows_its_route_returns() -> None:
    wrong = []
    for route, spec in exported():
        assert route.response_model is not None
        data = route.response_model.model_fields["data"].annotation
        if spec.row_model not in models_in(data):
            wrong.append((route.path, spec.row_model.__name__))
    assert not wrong


def test_every_export_has_columns() -> None:
    assert all(columns_of(spec.row_model) for _, spec in exported())


def test_no_two_exports_share_a_title_because_the_title_names_the_file() -> None:
    titles = [spec.title for _, spec in exported()]
    assert len(titles) == len(set(titles))
