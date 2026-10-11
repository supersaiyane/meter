"""The AppRegistry adapter over a stubbed client in AppRegistry's own shapes. TASK-P11-003.

The stub serves the fake catalogue's applications one item a page, so every list is paged, and
answers a planned failure with the code AWS would, so it reaches `translate` as AWS's would.
`catalogue_backed` is what the contract test holds to the same assertions as the fake: one adapter
per account, as composition binds them, each over the stub serving that account.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from datetime import datetime
from typing import Any

import pytest
from botocore.exceptions import ClientError

from finops_core.domain.account import AccountKey, Provider
from finops_core.domain.ownership import CatalogueApplication
from finops_core.errors import AccessDenied, CollectionError, SchemaDrift
from finops_fakes import fixtures
from finops_fakes.ownership import APPLICATION_TAG, CATALOGUE, STACK_TAG
from finops_providers.aws.appregistry import AwsServiceCatalogue

#: The code AWS answers each cause with.
CODES = {
    "AccessDenied": "AccessDeniedException",
    "Throttled": "ThrottlingException",
    "NotOptedIn": "OptInRequired",
}
ACCOUNT = AccountKey(provider=Provider.AWS, account_id="fake-product-b")
REGION = "us-fake-1"

Application = tuple[str, str, str | None, frozenset[tuple[str, str]], str | None]


class StubAppRegistry:
    """AppRegistry's five reads over a list of applications: name, id, owner, marks, attributes.

    `attributes` replaces the owner's JSON when given, to plant a group that cannot be read.
    """

    def __init__(self, applications: Sequence[Application], code: str | None = None) -> None:
        self._applications = {one[1]: one for one in applications}
        self._order = [one[1] for one in applications]
        self._code = code
        self.calls: list[str] = []

    def _fail(self, operation: str) -> None:
        self.calls.append(operation)
        if self._code is not None:
            raise ClientError({"Error": {"Code": self._code, "Message": "stubbed"}}, operation)

    def get_paginator(self, operation: str) -> _Paginator:
        return _Paginator(self, operation)

    def get_application(self, *, application: str) -> dict[str, Any]:
        self._fail("GetApplication")
        _, _, _, marks, _ = self._applications[application]
        tags = {key: value for key, value in marks if key == APPLICATION_TAG}
        return {"id": application, "applicationTag": tags}

    def get_attribute_group(self, *, attributeGroup: str) -> dict[str, Any]:  # noqa: N803
        self._fail("GetAttributeGroup")
        _, _, owner, _, attributes = self._applications[attributeGroup.removeprefix("group-")]
        if attributes is not None:
            return {"attributes": attributes}
        return {"attributes": json.dumps({"owner": owner} if owner else {"cost-center": "4410"})}

    def items(self, operation: str, request: dict[str, Any]) -> tuple[str, list[Any]]:
        self._fail(operation)
        if operation == "list_applications":
            return "applications", [
                {"id": one, "name": self._applications[one][0]} for one in self._order
            ]
        name, _, _, marks, _ = self._applications[request["application"]]
        if operation == "list_associated_resources":
            stacks = [
                {"name": value.rsplit("/", 2)[-2], "arn": value, "resourceType": "CFN_STACK"}
                for key, value in marks
                if key == STACK_TAG
            ]
            # The application's own tag value is an associated resource too, and names no stack.
            own = {"name": name, "arn": "tag-value", "resourceType": "RESOURCE_TAG_VALUE"}
            return "resources", [*stacks, own]
        return "attributeGroupsDetails", [{"id": f"group-{request['application']}"}]


class _Paginator:
    def __init__(self, client: StubAppRegistry, operation: str) -> None:
        self._client = client
        self._operation = operation

    def paginate(self, **request: Any) -> Iterator[dict[str, Any]]:
        key, found = self._client.items(self._operation, request)
        if not found:
            yield {key: []}
        for index, item in enumerate(found):
            page: dict[str, Any] = {key: [item]}
            if index + 1 < len(found):
                page["nextToken"] = str(index + 1)
            yield page


def planted(account: str, region: str) -> list[Application]:
    return [
        (name, application_id, owner, marks, None)
        for held, where, name, application_id, owner, marks in CATALOGUE
        if held == account and where == region
    ]


def adapter(client: StubAppRegistry, owner_key: str = "owner") -> AwsServiceCatalogue:
    return AwsServiceCatalogue(
        client_factory=lambda _service, _region: client,
        owner_key=owner_key,
        clock=lambda: fixtures.COLLECTED_AT,
    )


class _PerAccount:
    """One adapter per account, as composition binds them, behind the port."""

    def __init__(self, failure: type[CollectionError] | None, accounts: Sequence[str]) -> None:
        self._failure = failure
        self._accounts = frozenset(accounts)

    def applications(self, account: AccountKey, region: str) -> tuple[CatalogueApplication, ...]:
        failing = self._failure is not None and (
            not self._accounts or account.account_id in self._accounts
        )
        code = CODES[self._failure.cause] if failing and self._failure is not None else None
        client = StubAppRegistry(planted(account.account_id, region), code)
        return tuple(adapter(client).applications(account, region))


def catalogue_backed(
    *, failure: type[CollectionError] | None = None, accounts: Sequence[str] = ()
) -> _PerAccount:
    """The AWS adapter for the contract test, over the stub serving the fake's applications."""
    return _PerAccount(failure, accounts)


# --- the adapter ---------------------------------------------------------------------


def by_name(found: Any) -> dict[str, CatalogueApplication]:
    return {one.name: one for one in found}


def test_each_application_is_read_with_its_owner_and_the_tags_that_mark_its_resources() -> None:
    client = StubAppRegistry(planted(ACCOUNT.account_id, REGION))
    found = by_name(adapter(client).applications(ACCOUNT, REGION))
    assert set(found) == {"checkout", "reporting", "sandbox"}
    assert found["checkout"].owner == "payments"
    assert {key for key, _ in found["checkout"].marks} == {APPLICATION_TAG}
    # A stack association marks by the stack; the tag value association adds nothing more.
    assert {key for key, _ in found["reporting"].marks} == {STACK_TAG}
    assert found["sandbox"].owner is None


def test_every_list_is_read_to_its_last_page() -> None:
    client = StubAppRegistry(planted(ACCOUNT.account_id, REGION))
    assert len(tuple(adapter(client).applications(ACCOUNT, REGION))) == 3
    assert client.calls.count("GetApplication") == 3


def test_the_owner_is_read_under_the_key_the_deployment_names() -> None:
    application: Application = (
        "billing",
        "app-billing",
        None,
        frozenset(),
        json.dumps({"team-owner": " finance ", "owner": ""}),
    )
    found = adapter(StubAppRegistry([application]), owner_key="team-owner").applications(
        ACCOUNT, REGION
    )
    assert [one.owner for one in found] == ["finance"]


def test_an_application_with_no_marks_holds_no_resource() -> None:
    application: Application = ("empty", "app-empty", "x", frozenset(), None)
    (found,) = adapter(StubAppRegistry([application])).applications(ACCOUNT, REGION)
    assert found.marks == frozenset()
    assert not found.holds({APPLICATION_TAG: "anything"})


@pytest.mark.parametrize(
    ("attributes", "says"),
    [("not json", "is not JSON"), (json.dumps(["owner"]), "is not a JSON object")],
)
def test_an_attribute_group_this_cannot_read_is_schema_drift(attributes: str, says: str) -> None:
    application: Application = ("odd", "app-odd", None, frozenset(), attributes)
    with pytest.raises(SchemaDrift, match=says):
        tuple(adapter(StubAppRegistry([application])).applications(ACCOUNT, REGION))


def test_an_application_with_no_name_is_schema_drift() -> None:
    application: Application = ("", "app-nameless", None, frozenset(), None)
    with pytest.raises(SchemaDrift, match="no id or name"):
        tuple(adapter(StubAppRegistry([application])).applications(ACCOUNT, REGION))


def test_a_refused_call_is_raised_by_its_cause_with_the_account_and_region() -> None:
    client = StubAppRegistry(planted(ACCOUNT.account_id, REGION), "AccessDeniedException")
    with pytest.raises(AccessDenied) as raised:
        tuple(adapter(client).applications(ACCOUNT, REGION))
    assert raised.value.scope_key == f"{ACCOUNT.account_id}:{REGION}"


def test_the_catalogue_is_dated_when_it_was_read() -> None:
    client = StubAppRegistry(planted(ACCOUNT.account_id, REGION))
    for one in adapter(client).applications(ACCOUNT, REGION):
        assert one.as_of == one.collected_at == fixtures.COLLECTED_AT
        assert isinstance(one.as_of, datetime)
