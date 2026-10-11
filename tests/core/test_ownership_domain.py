"""A suggested owner says where it came from, and is never a team where a person is meant.

TASK-P11-001, P11 spec sections 5.1 to 5.4.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from finops_core.domain.account import AccountKey, Provider
from finops_core.domain.ownership import (
    ORDER,
    BeforeHistory,
    CatalogueApplication,
    Creator,
    OwnerKind,
    OwnerSource,
    OwnerSuggestion,
    strongest_first,
)

AT = datetime(2026, 10, 8, 6, 0, tzinfo=UTC)
ACCOUNT = AccountKey(provider=Provider.AWS, account_id="111111111111")


def suggestion(**overrides: Any) -> OwnerSuggestion:
    fields: dict[str, Any] = {
        "account_key": ACCOUNT,
        "region_id": "eu-west-2",
        "resource_id": "i-0123",
        "source": OwnerSource.TAG,
        "owner": "platform",
        "kind": OwnerKind.TEAM,
        "detail": "team",
        "as_of": AT,
        "collected_at": AT,
        **overrides,
    }
    return OwnerSuggestion(**fields)


def test_the_catalogue_is_strongest_and_the_creator_weakest() -> None:
    assert ORDER == (OwnerSource.CATALOGUE, OwnerSource.TAG, OwnerSource.CREATOR)
    creator = suggestion(source=OwnerSource.CREATOR, kind=OwnerKind.PERSON, detail="event-1")
    tag = suggestion()
    catalogue = suggestion(source=OwnerSource.CATALOGUE, detail="checkout")
    assert strongest_first([creator, tag, catalogue]) == (catalogue, tag, creator)


@pytest.mark.parametrize(
    ("overrides", "says"),
    [
        ({"owner": " "}, "owner is blank"),
        ({"detail": ""}, "detail is blank"),
        ({"resource_id": ""}, "resource_id is blank"),
        ({"kind": OwnerKind.PERSON}, "a tag names a team"),
        (
            {"source": OwnerSource.CREATOR, "kind": OwnerKind.TEAM},
            "a creator is a person or a pipeline",
        ),
        ({"collected_at": AT - timedelta(seconds=1)}, "read before it was true"),
    ],
)
def test_a_suggestion_that_could_not_be_checked_is_refused(
    overrides: dict[str, Any], says: str
) -> None:
    with pytest.raises(ValueError, match=says):
        suggestion(**overrides)


def application(**overrides: Any) -> CatalogueApplication:
    fields: dict[str, Any] = {
        "account_key": ACCOUNT,
        "region_id": "eu-west-2",
        "name": "reporting",
        "application_id": "app-1",
        "owner": None,
        "marks": frozenset({("app", "reporting"), ("stack", "stack-1")}),
        "as_of": AT,
        "collected_at": AT,
        **overrides,
    }
    return CatalogueApplication(**fields)


def test_an_application_that_names_nobody_is_still_an_application() -> None:
    assert application().owner is None
    with pytest.raises(ValueError, match="owner is blank"):
        application(owner="")
    with pytest.raises(ValueError, match="application_id is blank"):
        application(application_id=" ")


def test_a_resource_is_an_applications_when_any_of_its_marks_is_on_it() -> None:
    reporting = application()
    assert reporting.holds({"stack": "stack-1", "team": "x"})
    assert reporting.holds({"app": "reporting"})
    assert not reporting.holds({"app": "checkout"})
    assert not reporting.holds({})


def test_a_creator_is_never_a_team() -> None:
    with pytest.raises(ValueError, match="never a team"):
        Creator(
            account_key=ACCOUNT,
            region_id="eu-west-2",
            resource_id="i-0123",
            principal="platform",
            kind=OwnerKind.TEAM,
            event_id="event-1",
            created_at=AT,
            as_of=AT,
            collected_at=AT,
        )


def test_a_resource_older_than_the_record_says_how_far_back_was_searched() -> None:
    older = BeforeHistory(
        account_key=ACCOUNT,
        region_id="eu-west-2",
        resource_id="i-0123",
        history_starts=AT - timedelta(days=90),
        as_of=AT,
        collected_at=AT,
    )
    assert older.history_starts == AT - timedelta(days=90)
