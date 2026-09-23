"""The fake query surface, and the parts of the port that are easy to get wrong.

Most of these assert a distinction rather than a value. An unreachable instance
that is omitted, an empty listing that means a failed read, and a control that
raises when it should have answered `applied` false are all cases where the code
runs and the answer is wrong, which is the kind of defect a test has to be
written on purpose to catch.
"""

from __future__ import annotations

import pytest

from finops_core.domain.query import (
    ControlAction,
    ControlRequest,
    SurfaceKind,
)
from finops_core.errors import (
    AccessDenied,
    CollectionError,
    NotOptedIn,
    Throttled,
    Unreachable,
)
from finops_core.ports.query import QuerySurface
from finops_providers.fake.surface import FakeQuerySurface


def test_it_satisfies_the_port() -> None:
    assert isinstance(FakeQuerySurface(), QuerySurface)


def test_the_estate_has_one_instance_of_every_kind() -> None:
    # A fake that only models the implemented kind would let an adapter assume
    # one, which is the shape FEAT-019 exists to prevent.
    kinds = {instance.kind for instance in FakeQuerySurface().discover()}
    assert kinds == set(SurfaceKind)


def test_an_unreachable_instance_is_returned_rather_than_omitted() -> None:
    # Omitting it makes the estate look smaller and cheaper than it is.
    unreachable = [i for i in FakeQuerySurface().discover() if not i.reachable]
    assert len(unreachable) == 1
    assert unreachable[0].unreachable_cause


def test_discover_does_not_raise_for_a_single_unreachable_instance() -> None:
    instances = list(FakeQuerySurface().discover())
    assert len(instances) == 3


def test_discover_raises_only_when_discovery_itself_failed() -> None:
    # Nothing at all could be enumerated, which is a different condition from
    # one instance being unreadable and must not be reported the same way.
    surface = FakeQuerySurface(discovery_failure=Throttled)
    with pytest.raises(Throttled):
        list(surface.discover())


@pytest.mark.parametrize("cause", [AccessDenied, Throttled, NotOptedIn, Unreachable])
def test_any_cause_can_be_planned_per_instance(cause: type[CollectionError]) -> None:
    surface = FakeQuerySurface()
    instance = next(i for i in surface.discover() if i.reachable)
    planned = FakeQuerySurface(failures={instance.scope_key: cause})
    with pytest.raises(cause):
        list(planned.list_queries(instance))


def test_an_empty_listing_means_empty_and_never_a_failed_read() -> None:
    # Zero queries and an unreadable instance look identical on a screen, and
    # only one of them is good news.
    surface = FakeQuerySurface(queries={})
    instance = next(i for i in surface.discover() if i.reachable)
    assert list(surface.list_queries(instance)) == []


def test_listing_an_unreachable_instance_raises_its_own_cause() -> None:
    surface = FakeQuerySurface()
    instance = next(i for i in surface.discover() if not i.reachable)
    with pytest.raises(AccessDenied):
        list(surface.list_queries(instance))


def test_a_control_a_surface_cannot_do_answers_rather_than_raises() -> None:
    # The caller's next move is to try a different control, not to abandon the
    # run, so this is a normal answer.
    surface = FakeQuerySurface(supports={ControlAction.OBSERVE})
    instance = next(i for i in surface.discover() if i.reachable)
    query = next(iter(surface.list_queries(instance)))
    outcome = surface.apply_control(
        instance,
        ControlRequest(fingerprint=query.fingerprint, action=ControlAction.THROTTLE),
    )
    assert outcome.applied is False
    assert outcome.detail


def test_a_control_that_may_not_be_written_raises_instead() -> None:
    # Distinct from applied false: the token may read and may not write, which
    # is a permissions problem a person has to fix.
    surface = FakeQuerySurface()
    instance = next(i for i in surface.discover() if i.reachable)
    query = next(iter(surface.list_queries(instance)))
    denied = FakeQuerySurface(control_failures={instance.scope_key: AccessDenied})
    with pytest.raises(AccessDenied):
        denied.apply_control(
            instance,
            ControlRequest(fingerprint=query.fingerprint, action=ControlAction.THROTTLE),
        )


def test_an_applied_control_reports_what_it_replaced() -> None:
    # A control that cannot say what it replaced is a control nobody will dare
    # apply. TASK-P2-019 needs this to undo a rewrite.
    surface = FakeQuerySurface()
    instance = next(i for i in surface.discover() if i.reachable)
    query = next(iter(surface.list_queries(instance)))
    outcome = surface.apply_control(
        instance,
        ControlRequest(
            fingerprint=query.fingerprint,
            action=ControlAction.THROTTLE,
            minimum_refresh_seconds=300,
        ),
    )
    assert outcome.applied is True
    assert outcome.previous == str(query.refresh_seconds)


def test_never_deny_is_refused_rather_than_applied() -> None:
    # ISS-092. A deny that cuts an engineer off from Logs Insights during an
    # incident is worse than the cost it prevented.
    surface = FakeQuerySurface()
    instance = next(i for i in surface.discover() if i.reachable)
    query = next(iter(surface.list_queries(instance)))
    outcome = surface.apply_control(
        instance,
        ControlRequest(
            fingerprint=query.fingerprint,
            action=ControlAction.DENY,
            never_deny=frozenset({query.fingerprint}),
        ),
    )
    assert outcome.applied is False
    assert "never deny" in outcome.detail.lower()


def test_it_is_deterministic() -> None:
    # No clock and no randomness, so a golden file written today still matches
    # tomorrow.
    first = FakeQuerySurface()
    second = FakeQuerySurface()
    assert list(first.discover()) == list(second.discover())
    instance = next(i for i in first.discover() if i.reachable)
    assert list(first.list_queries(instance)) == list(second.list_queries(instance))
