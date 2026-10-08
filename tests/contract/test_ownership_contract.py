"""What every service catalogue and creator record must do, fake or real. TASK-P11-001.

P11 spec sections 5.3 and 5.4. The fakes pass it now; TASK-P11-003 adds the AppRegistry adapter
and TASK-P11-004 the CloudTrail one, each over a stubbed client serving the fake's own planted
cases, to the same assertions. A contract one implementation is held to and another is not is a
description of the first.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest

from finops_core.domain.account import AccountKey, Provider
from finops_core.domain.ownership import BeforeHistory, Creator, OwnerKind
from finops_core.errors import AccessDenied, CollectionError, NotOptedIn, Throttled
from finops_core.ports import ResourceCreators, ServiceCatalogue
from finops_fakes import fixtures, utilization
from finops_fakes.ownership import (
    HISTORY_DAYS,
    FakeResourceCreators,
    FakeServiceCatalogue,
)
from tests.providers.aws.test_appregistry import catalogue_backed

#: TASK-P11-003 adds the AppRegistry adapter, one per account over a stub, to the same contract.
CATALOGUES: dict[str, Callable[..., Any]] = {"fake": FakeServiceCatalogue, "aws": catalogue_backed}
CREATORS: dict[str, Callable[..., Any]] = {"fake": FakeResourceCreators}

UNTAGGED = AccountKey(provider=Provider.AWS, account_id="fake-product-b")
TAGGED = AccountKey(provider=Provider.AWS, account_id="fake-platform-a")
REGION = "us-fake-1"
CAUSES = (AccessDenied, Throttled, NotOptedIn)


@pytest.fixture(params=sorted(CATALOGUES))
def make_catalogue(request: pytest.FixtureRequest) -> Callable[..., Any]:
    return CATALOGUES[request.param]


@pytest.fixture(params=sorted(CREATORS))
def make_creators(request: pytest.FixtureRequest) -> Callable[..., Any]:
    return CREATORS[request.param]


# --- the catalogue -------------------------------------------------------------------


def test_it_is_a_service_catalogue(make_catalogue: Callable[..., Any]) -> None:
    assert isinstance(make_catalogue(), ServiceCatalogue)


def test_each_application_names_its_owner_or_nobody(make_catalogue: Callable[..., Any]) -> None:
    found = {(one.name, one.owner) for one in make_catalogue().applications(UNTAGGED, REGION)}
    assert found == {("checkout", "payments"), ("reporting", "analytics"), ("sandbox", None)}


@pytest.mark.parametrize(
    ("application", "resource"),
    [
        # By the application's own tag, and by the tag of the stack that made the resource.
        ("checkout", "amazonec2/fake-product-b/0004"),
        ("reporting", "amazonrds/fake-product-b/0001"),
        ("sandbox", "amazonec2/fake-product-b/0001"),
    ],
)
def test_an_application_holds_the_resources_its_marks_are_on(
    make_catalogue: Callable[..., Any], application: str, resource: str
) -> None:
    by_name = {one.name: one for one in make_catalogue().applications(UNTAGGED, REGION)}
    tags = utilization.tags_of(resource)
    assert by_name[application].holds(tags)
    assert [name for name, one in by_name.items() if one.holds(tags)] == [application]


def test_an_account_with_no_applications_has_none(
    make_catalogue: Callable[..., Any],
) -> None:
    assert tuple(make_catalogue().applications(TAGGED, REGION)) == ()


def test_every_application_was_true_before_it_was_read(
    make_catalogue: Callable[..., Any],
) -> None:
    for one in make_catalogue().applications(UNTAGGED, REGION):
        assert one.as_of <= one.collected_at
        assert one.account_key == UNTAGGED and one.region_id == REGION


@pytest.mark.parametrize("cause", CAUSES)
def test_a_refused_catalogue_read_is_raised_by_its_cause(
    make_catalogue: Callable[..., Any], cause: type[CollectionError]
) -> None:
    with pytest.raises(cause):
        tuple(make_catalogue(failure=cause).applications(UNTAGGED, REGION))


def test_one_account_refusing_leaves_the_others_readable(
    make_catalogue: Callable[..., Any],
) -> None:
    catalogue = make_catalogue(failure=AccessDenied, accounts=[TAGGED.account_id])
    with pytest.raises(AccessDenied):
        tuple(catalogue.applications(TAGGED, REGION))
    assert len(tuple(catalogue.applications(UNTAGGED, REGION))) == 3


# --- the creators --------------------------------------------------------------------


def test_it_is_a_record_of_creators(make_creators: Callable[..., Any]) -> None:
    assert isinstance(make_creators(), ResourceCreators)


def test_a_person_is_named_with_the_event_and_the_day_it_created_the_resource(
    make_creators: Callable[..., Any],
) -> None:
    found = make_creators().creator(UNTAGGED, REGION, "amazonec2/fake-product-b/0003")
    assert isinstance(found, Creator)
    assert (found.principal, found.kind) == ("dev.lead@fake.example", OwnerKind.PERSON)
    assert found.created_at == fixtures.AS_OF - timedelta(days=9)
    # True at the source when the resource was created, which is the creation.
    assert found.as_of == found.created_at <= found.collected_at
    assert found.event_id


def test_a_pipeline_is_named_as_automation_and_never_as_a_person(
    make_creators: Callable[..., Any],
) -> None:
    found = make_creators().creator(UNTAGGED, REGION, "amazonvpc/fake-product-b/nat-0001")
    assert isinstance(found, Creator)
    assert (found.principal, found.kind) == ("deploy-pipeline", OwnerKind.AUTOMATION)


def test_a_resource_older_than_the_record_says_so_rather_than_naming_anybody(
    make_creators: Callable[..., Any],
) -> None:
    found = make_creators().creator(UNTAGGED, REGION, "amazonec2/fake-product-b/0002")
    assert isinstance(found, BeforeHistory)
    assert found.history_starts == fixtures.AS_OF - timedelta(days=HISTORY_DAYS)


@pytest.mark.parametrize("cause", CAUSES)
def test_a_refused_creator_read_is_raised_by_its_cause(
    make_creators: Callable[..., Any], cause: type[CollectionError]
) -> None:
    with pytest.raises(cause):
        make_creators(failure=cause).creator(UNTAGGED, REGION, "amazonec2/fake-product-b/0003")
