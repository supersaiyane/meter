"""The assistant's toolbox, against a transport that records what it was asked.

TASK-P7-006. The evaluation sets prove the toolbox against the real routes. These pin what
it refuses on its own: an argument, which it does not repeat back; a status other than
success; and a body that is not the route's envelope, which never reaches a model. And the
two fields of the tool table only the assistant reads, held to what they promise.
"""

from __future__ import annotations

import types
import typing
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

import pytest
from pydantic import BaseModel

from finops_api.toolbox import ApiToolbox
from finops_api.tools import TOOLS, TOOLS_BY_NAME, ToolSpec
from finops_core.domain.insight import SCREEN_PATH, Provenance
from finops_query.insight import META as ENVELOPE_META
from finops_query.insight import ToolUnavailableError

TOKEN = "a-session-token"
SLICE = {"name": "AmazonEC2", "effective_cost": "812.40", "billed_cost": "900.00", "line_items": 40}
META = {
    "as_of": "2026-07-31T00:00:00Z",
    "collected_at": "2026-08-01T06:00:00Z",
    "scope_coverage": {"visible": 2, "total": 5, "unit": "accounts"},
    "failures": [],
}


@dataclass
class Response:
    status_code: int
    body: Any

    def json(self) -> Any:
        return self.body


@dataclass
class Recording:
    response: Response
    asked: list[tuple[str, dict[str, str]]] = field(default_factory=list)

    def get(self, url: str, *, headers: dict[str, str], params: dict[str, Any]) -> Response:
        assert params == {}, "every tool takes no arguments, so none reach a route"
        self.asked.append((url, headers))
        return self.response


def toolbox(response: Response) -> tuple[ApiToolbox, Recording]:
    transport = Recording(response)
    return ApiToolbox(transport, TOKEN), transport


def test_a_call_reads_the_route_as_the_asker_and_types_what_it_returns() -> None:
    tools, transport = toolbox(Response(200, {"data": [SLICE], "meta": META}))

    output = tools.call("get_cost_by_service", {})

    ((url, headers),) = transport.asked
    assert url == TOOLS_BY_NAME["get_cost_by_service"].path
    assert headers == {"Authorization": f"Bearer {TOKEN}"}
    assert output.envelope["data"][0]["effective_cost"] == Decimal("812.40")
    assert '"effective_cost":"812.40"' in output.text
    assert (output.provenance, output.screen) == (Provenance.MEASURED, "/cost")
    assert output.units == TOOLS_BY_NAME["get_cost_by_service"].units


def test_an_argument_is_refused_and_not_repeated_back() -> None:
    tools, transport = toolbox(Response(200, {"data": [], "meta": META}))

    with pytest.raises(ToolUnavailableError) as refused:
        tools.call("get_cost_by_account", {"account_id": "fake-product-a"})

    assert "fake-product-a" not in str(refused.value)
    assert transport.asked == [], "nothing reached the API"


def test_a_refusal_from_the_api_is_not_data() -> None:
    tools, _ = toolbox(Response(403, {"detail": "out of scope"}))
    with pytest.raises(ToolUnavailableError, match="403"):
        tools.call("get_cost_by_service", {})


def test_a_success_without_its_envelope_is_not_data() -> None:
    tools, _ = toolbox(Response(200, {"data": [SLICE]}))
    with pytest.raises(ToolUnavailableError, match="not its envelope"):
        tools.call("get_cost_by_service", {})


def test_a_tool_that_does_not_exist_is_not_called() -> None:
    tools, transport = toolbox(Response(200, {}))
    with pytest.raises(ToolUnavailableError):
        tools.call("forecast_next_month", {})
    assert transport.asked == []


def test_every_tool_is_offered_with_no_arguments() -> None:
    tools, _ = toolbox(Response(200, {}))
    schemas = tools.schemas()
    assert {schema.name for schema in schemas} == set(TOOLS_BY_NAME)
    assert all(schema.parameters == {"type": "object", "properties": {}} for schema in schemas)


def test_every_screen_a_tool_names_is_one_a_refusal_will_link_to() -> None:
    """A refusal carries its tool's screen, and `Refusal` refuses anything looser than a plain
    path. A tool naming one that does not match fails here, not when somebody is refused."""
    named = {spec.name: spec.screen for spec in TOOLS_BY_NAME.values() if spec.screen}
    assert named, "no tool names a screen, so this proves nothing"
    assert {name: path for name, path in named.items() if not SCREEN_PATH.fullmatch(path)} == {}


# --- what each figure counts, ISS-231 -----------------------------------------------------

#: Leaf types that hold no figure. A type outside these, the numbers and the shapes walked
#: below fails the walk, so a new kind of field is looked at rather than skipped.
NOT_FIGURES = (str, bool, date, datetime, UUID, type(None))

#: Every number the envelope's meta holds. The loop cites each as a count with no lookup, so
#: a number added to meta that is not a count has to change that rule before this list.
META_COUNTS = frozenset(
    {"meta.scope_coverage.visible", "meta.scope_coverage.total", "meta.failures.occurrences"}
)


def numeric_paths(annotation: Any, path: str) -> set[str]:
    """Every path under `path` whose value is a number, written as a citation names it with
    its row selectors taken out: `data.clusters.workloads.cost` for every workload's cost."""
    origin = typing.get_origin(annotation)
    if origin in (typing.Union, types.UnionType, list, tuple):
        arguments = [arg for arg in typing.get_args(annotation) if arg is not Ellipsis]
        return set().union(*(numeric_paths(arg, path) for arg in arguments))
    if origin is Literal:
        return set()
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        fields = {name: info.annotation for name, info in annotation.model_fields.items()}
        computed = annotation.model_computed_fields.items()
        fields |= {name: info.return_type for name, info in computed}
        return set().union(
            *(numeric_paths(kind, f"{path}.{name}") for name, kind in fields.items())
        )
    # A bool is an int to Python and never a figure, so it is decided before the numbers.
    if annotation in NOT_FIGURES:
        return set()
    if annotation in (int, float, Decimal):
        return {path}
    pytest.fail(f"{path} is a {annotation!r}, which this walk does not know how to read")


def data_of(spec: ToolSpec) -> Any:
    return spec.envelope.model_fields["data"].annotation


@pytest.mark.parametrize("spec", TOOLS, ids=[spec.name for spec in TOOLS])
def test_every_number_a_tool_returns_has_its_unit_declared_and_nothing_else_does(
    spec: ToolSpec,
) -> None:
    """Exhaustive on purpose. A numeric field added to a route's model without a unit in the
    tool table fails here, rather than reaching the screen with no unit, and a unit left
    behind for a field that is gone fails too."""
    assert set(spec.units) == numeric_paths(data_of(spec), "data")


def test_the_walk_finds_both_units_somewhere_so_the_test_above_is_not_vacuous() -> None:
    declared = {unit for spec in TOOLS for unit in spec.units.values()}
    found = set().union(*(numeric_paths(data_of(spec), "data") for spec in TOOLS))
    assert declared == {"usd", "count"}
    assert "data.clusters.workloads.cost" in found, "the walk reaches into nested lists"


def test_every_number_in_the_envelope_meta_is_one_the_loop_may_call_a_count() -> None:
    for spec in TOOLS:
        meta = spec.envelope.model_fields[ENVELOPE_META].annotation
        assert numeric_paths(meta, ENVELOPE_META) == META_COUNTS, spec.name
