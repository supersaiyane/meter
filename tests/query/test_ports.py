"""The QuerySurface port, and what it refuses to know about.

The load bearing test here is the vendor leak check. TASK-P2-004 says no Grafana
type appears in any signature, and the reason is FEAT-019: the failure mode this
product addresses is not Grafana specific, so an abstraction shaped like one
vendor has to be rewritten for the second. A protocol that returned a Grafana
dashboard would look fine and would have already made that decision.

The rest holds the domain honest about absence. An instance nobody could reach
must appear in the list saying why, because an omitted workspace and a workspace
that does not exist look identical to a reader, and only one of them is a
problem.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime
from typing import get_type_hints

import pytest

from finops_core import errors, ports
from finops_core.domain.query import (
    ControlAction,
    ControlOutcome,
    ControlRequest,
    QueryDefinition,
    QueryOrigin,
    SurfaceInstance,
    SurfaceKind,
)
from finops_core.ports.query import QuerySurface

AT = datetime(2026, 9, 5, 9, 0, tzinfo=UTC)

#: Words that would mean the abstraction had been shaped by its first
#: implementation. Checked against every signature and every type name the
#: protocol mentions.
VENDOR_WORDS = ("grafana", "dashboard", "panel", "workspace", "amg", "prometheus")

EXPECTED_METHODS = {"discover", "list_queries", "apply_control"}


def method_names() -> set[str]:
    return {
        name
        for name, value in inspect.getmembers(QuerySurface, inspect.isfunction)
        if not name.startswith("_")
    }


def test_the_port_has_exactly_the_three_methods_the_plan_names() -> None:
    assert method_names() == EXPECTED_METHODS


def test_it_is_a_runtime_checkable_protocol() -> None:
    """So an adapter can be checked at a boundary rather than at a call site."""
    assert getattr(QuerySurface, "_is_protocol", False)
    assert getattr(QuerySurface, "_is_runtime_protocol", False)


def test_it_is_exported_from_the_ports_package() -> None:
    assert "QuerySurface" in ports.__all__
    assert ports.QuerySurface is QuerySurface


@pytest.mark.parametrize("name", sorted(EXPECTED_METHODS))
def test_no_vendor_word_appears_in_a_signature(name: str) -> None:
    """Naming an abstraction after its first implementation is how it ends up
    shaped like one vendor. FEAT-019."""
    method = getattr(QuerySurface, name)
    hints = get_type_hints(method)

    rendered = " ".join(
        [name, *(getattr(hint, "__name__", str(hint)) for hint in hints.values())]
    ).lower()

    for word in VENDOR_WORDS:
        assert word not in rendered, f"{name} mentions {word!r} in its signature"


@pytest.mark.parametrize("name", sorted(EXPECTED_METHODS))
def test_every_method_names_the_causes_it_raises(name: str) -> None:
    """A method that does not say leaves the caller to guess, and a caller that
    guesses writes `except Exception` and collapses the taxonomy."""
    doc = inspect.getdoc(getattr(QuerySurface, name)) or ""

    assert "Raises:" in doc, f"{name} documents no failure causes"

    # Taken from the taxonomy rather than listed here, so a seventh cause
    # cannot be added without this noticing.
    causes = {cause.__name__ for cause in errors.CollectionError.__subclasses__()}
    named = {cause for cause in causes if f"{cause}:" in doc}

    assert named, f"{name} has a Raises block naming none of {sorted(causes)}"


def test_the_domain_types_the_port_returns_carry_no_vendor_word() -> None:
    """The types leak the same way the signatures do, one level down."""
    for kind in (SurfaceInstance, QueryDefinition, ControlOutcome, ControlRequest):
        fields = " ".join(kind.__dataclass_fields__).lower()
        for word in VENDOR_WORDS:
            assert word not in fields, f"{kind.__name__} has a field mentioning {word!r}"


# --- what the domain refuses to represent ------------------------------------


def test_an_unreachable_instance_must_name_a_cause() -> None:
    """An unexplained absence is exactly the failure this field exists for."""
    with pytest.raises(ValueError, match="names no cause"):
        SurfaceInstance(
            surface_id="g-1",
            name="obs",
            kind=SurfaceKind.MANAGED_GRAFANA,
            location="host.invalid",
            reachable=False,
        )


def test_an_unreachable_instance_with_a_cause_is_valid() -> None:
    """It has to be representable. Omitting it makes the estate look cheaper."""
    instance = SurfaceInstance(
        surface_id="g-1",
        name="obs",
        kind=SurfaceKind.MANAGED_GRAFANA,
        location="host.invalid",
        reachable=False,
        unreachable_cause="AccessDenied",
    )

    assert instance.reachable is False
    assert instance.unreachable_cause == "AccessDenied"


def test_an_instance_names_the_scope_a_failure_is_recorded_under() -> None:
    instance = SurfaceInstance(
        surface_id="g-1", name="obs", kind=SurfaceKind.MANAGED_GRAFANA, location="host.invalid"
    )

    assert instance.scope_key == "managed_grafana:g-1"


def test_a_query_definition_carries_both_timestamps() -> None:
    """Constraint 4 and 10. A figure computed from a definition read last week
    is not a figure about today."""
    definition = QueryDefinition(
        as_of=AT,
        collected_at=AT,
        surface_id="g-1",
        fingerprint="abc",
        origin=QueryOrigin.PANEL,
        engine="logs_insights",
        query="fields @message",
    )

    assert definition.as_of == AT
    assert definition.collected_at == AT


def test_a_query_definition_carries_no_cost() -> None:
    """Pricing is the cost model's job. A definition that carried a figure would
    make a new surface need a new cost model."""
    fields = set(QueryDefinition.__dataclass_fields__)

    assert not {f for f in fields if "cost" in f or "price" in f}


def test_an_unowned_query_says_so_rather_than_guessing() -> None:
    """ISS-021: an unowned finding is never fixed, so it must read as unowned."""
    definition = QueryDefinition(
        as_of=AT,
        collected_at=AT,
        surface_id="g-1",
        fingerprint="abc",
        origin=QueryOrigin.PANEL,
        engine="metric_search",
        query="",
    )

    assert definition.last_run_by is None


def test_observe_is_the_default_shape_of_a_control() -> None:
    """ISS-020 says a tool that only reports is a post mortem. The answer to
    that is not to make enforcement the default."""
    assert ControlAction.OBSERVE.value == "observe"
    assert list(ControlAction) == [
        ControlAction.OBSERVE,
        ControlAction.THROTTLE,
        ControlAction.DENY,
    ]


def test_a_control_can_name_queries_it_must_never_deny() -> None:
    """ISS-092: a deny that cuts an engineer off from Logs Insights during an
    incident is worse than the cost it prevented."""
    request = ControlRequest(
        fingerprint="abc", action=ControlAction.DENY, never_deny=frozenset({"xyz"})
    )

    assert "xyz" in request.never_deny


def test_an_outcome_records_what_it_replaced() -> None:
    """TASK-P2-019 requires every rewrite to be reversible, and a control that
    cannot say what it replaced is one nobody will dare apply."""
    outcome = ControlOutcome(
        surface_id="g-1",
        fingerprint="abc",
        requested=ControlAction.THROTTLE,
        applied=True,
        previous="30s",
    )

    assert outcome.previous == "30s"


def test_a_refused_control_is_an_outcome_and_not_an_error() -> None:
    """A surface with no throttle should say so, so the caller can try a
    different control instead of abandoning the run."""
    outcome = ControlOutcome(
        surface_id="g-1",
        fingerprint="abc",
        requested=ControlAction.THROTTLE,
        applied=False,
        detail="this surface has no refresh control",
    )

    assert outcome.applied is False
    assert outcome.detail
