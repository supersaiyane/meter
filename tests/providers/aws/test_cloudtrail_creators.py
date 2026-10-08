"""The CloudTrail creators adapter over a stubbed client in CloudTrail's own shapes. TASK-P11-004.

The stub answers `LookupEvents` as CloudTrail would: only the events inside the window asked for,
newest first, one a page so every lookup pages, and a planned failure with the code AWS would send,
so it reaches `translate` as AWS's would. `creators_backed` is what the contract test holds to the
same assertions as the fake, over the fake estate's creations, each followed by a `CreateTags`
that names the resource and created nothing.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator, Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any

import pytest
from botocore.exceptions import ClientError

from finops_core.domain.account import AccountKey, Provider
from finops_core.domain.ownership import BeforeHistory, Creator, OwnerKind
from finops_core.errors import AccessDenied, CollectionError, SchemaDrift
from finops_fakes import fixtures
from finops_fakes.ownership import CREATED
from finops_providers.aws.cloudtrail_creators import (
    HISTORY_DAYS,
    PAGE_SIZE,
    AwsResourceCreators,
    names_of,
    type_of,
)
from finops_query.parser import GrafanaQueryParser

#: The code AWS answers each cause with.
CODES = {
    "AccessDenied": "AccessDeniedException",
    "Throttled": "ThrottlingException",
    "NotOptedIn": "OptInRequired",
}
ACCOUNT = AccountKey(provider=Provider.AWS, account_id="fake-product-b")
REGION = "us-fake-1"
#: A role IAM Identity Center gives a person who signs in.
SSO = "AWSReservedSSO_Developer_0a1b2c"
#: The resource the fake says is older than the history.
OLDER = "amazonec2/fake-product-b/0002"
INSTANCE = f"arn:aws:ec2:{REGION}:fake-product-b:instance/i-0fake"


def person(name: str) -> dict[str, Any]:
    """A person signed in through IAM Identity Center, as CloudTrail records the session."""
    return {
        "type": "AssumedRole",
        "principalId": f"FAKEROLEID:{name}",
        "arn": f"arn:aws:sts::fake-product-b:assumed-role/{SSO}/{name}",
        "sessionContext": {"sessionIssuer": {"type": "Role", "userName": SSO}},
    }


def pipeline(role: str) -> dict[str, Any]:
    """A pipeline's session under its own role."""
    return {
        "type": "AssumedRole",
        "principalId": "FAKEROLEID:build-4411",
        "arn": f"arn:aws:sts::fake-product-b:assumed-role/{role}/build-4411",
        "sessionContext": {"sessionIssuer": {"type": "Role", "userName": role}},
    }


def event(
    event_id: str,
    name: str,
    at: datetime,
    identity: Mapping[str, Any],
    request: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    detail = {"eventName": name, "userIdentity": identity, "requestParameters": request}
    return {
        "EventId": event_id,
        "EventName": name,
        "EventTime": at,
        "ReadOnly": "false",
        "CloudTrailEvent": json.dumps(detail),
    }


def tagged(resource: str, at: datetime) -> dict[str, Any]:
    """A tag put on an existing resource: a creating verb that created nothing."""
    request = {"resourcesSet": {"items": [{"resourceId": resource}]}}
    return event(f"tag-{resource}", "CreateTags", at, person("tagger@fake.example"), request)


def planted() -> dict[str, list[dict[str, Any]]]:
    """The fake estate's history as CloudTrail would hold it, by the name each is recorded under."""
    history: dict[str, list[dict[str, Any]]] = {
        OLDER: [tagged(OLDER, fixtures.AS_OF - timedelta(days=3))]
    }
    for resource, (who, kind, days) in CREATED.items():
        at = fixtures.AS_OF - timedelta(days=days)
        person_made = kind is OwnerKind.PERSON
        creating = "RunInstances" if person_made else "CreateNatGateway"
        identity = person(who) if person_made else pipeline(who)
        history[resource] = [
            tagged(resource, at + timedelta(hours=2)),
            event(f"evt-{days}", creating, at, identity, {"subnetId": "subnet-fake"}),
        ]
    return history


class StubTrail:
    """`LookupEvents` over a history, keyed by the name CloudTrail records each resource under.

    `raw` serves the history as it is, unfiltered, to plant an event CloudTrail would not send.
    """

    def __init__(
        self,
        history: Mapping[str, Sequence[dict[str, Any]]],
        code: str | None = None,
        raw: bool = False,
    ) -> None:
        self.history = history
        self.code = code
        self.raw = raw
        self.requests: list[dict[str, Any]] = []

    def get_paginator(self, operation: str) -> _Paginator:
        assert operation == "lookup_events"
        return _Paginator(self)


class _Paginator:
    def __init__(self, trail: StubTrail) -> None:
        self._trail = trail

    def paginate(self, **request: Any) -> Iterator[dict[str, Any]]:
        self._trail.requests.append(request)
        if self._trail.code is not None:
            raise ClientError(
                {"Error": {"Code": self._trail.code, "Message": "stubbed"}}, "LookupEvents"
            )
        (attribute,) = request["LookupAttributes"]
        found = list(self._trail.history.get(attribute["AttributeValue"], ()))
        if not self._trail.raw:
            window = (request["StartTime"], request["EndTime"])
            inside = (one for one in found if window[0] <= one["EventTime"] <= window[1])
            found = sorted(inside, key=lambda one: one["EventTime"], reverse=True)
        if not found:
            yield {"Events": []}
        for index, one in enumerate(found):
            page: dict[str, Any] = {"Events": [one]}
            if index + 1 < len(found):
                page["NextToken"] = str(index + 1)
            yield page


def adapter(
    trail: StubTrail,
    sleep: Callable[[float], None] = lambda _seconds: None,
    monotonic: Callable[[], float] = lambda: 0.0,
) -> AwsResourceCreators:
    return AwsResourceCreators(
        client_factory=lambda _service, _account, _region: trail,
        principal_of=GrafanaQueryParser().principal_from,
        clock=lambda: fixtures.AS_OF,
        sleep=sleep,
        monotonic=monotonic,
    )


class _PerAccount:
    """One adapter per account, as composition binds them, behind the port."""

    def __init__(self, failure: type[CollectionError] | None, accounts: Sequence[str]) -> None:
        self._failure = failure
        self._accounts = frozenset(accounts)

    def creator(
        self, account: AccountKey, region: str, resource_id: str
    ) -> Creator | BeforeHistory:
        failing = self._failure is not None and (
            not self._accounts or account.account_id in self._accounts
        )
        code = CODES[self._failure.cause] if failing and self._failure is not None else None
        return adapter(StubTrail(planted(), code)).creator(account, region, resource_id)


def creators_backed(
    *, failure: type[CollectionError] | None = None, accounts: Sequence[str] = ()
) -> _PerAccount:
    """The AWS adapter for the contract test, over the stub serving the fake's creations."""
    return _PerAccount(failure, accounts)


def lookup(history: Mapping[str, Sequence[dict[str, Any]]], resource: str = INSTANCE) -> Any:
    return adapter(StubTrail(history)).creator(ACCOUNT, REGION, resource)


# --- the names asked and the event that created ---------------------------------------


@pytest.mark.parametrize(
    ("resource", "names"),
    [
        (INSTANCE, ("i-0fake", INSTANCE)),
        ("arn:aws:rds:r:a:db:orders", ("orders", "arn:aws:rds:r:a:db:orders")),
        ("arn:aws:s3:::fake-bucket", ("fake-bucket", "arn:aws:s3:::fake-bucket")),
        ("amazonec2/fake-product-b/0003", ("amazonec2/fake-product-b/0003",)),
    ],
)
def test_an_arn_is_asked_by_its_own_id_and_then_whole(
    resource: str, names: tuple[str, ...]
) -> None:
    assert names_of(resource) == names


@pytest.mark.parametrize(
    ("resource", "typed"),
    [
        (INSTANCE, ("ec2", "instance")),
        ("arn:aws:rds:r:a:db:orders", ("rds", "db")),
        ("arn:aws:s3:::fake-bucket", ("s3", None)),
        ("arn:aws", None),
        ("i-0fake", None),
    ],
)
def test_an_arn_names_its_service_and_type(resource: str, typed: object) -> None:
    assert type_of(resource) == typed


@pytest.mark.parametrize(
    ("resource", "name", "creates"),
    [
        (INSTANCE, "RunInstances", True),
        (INSTANCE, "CreateImage", False),
        ("arn:aws:ec2:r:a:volume/vol-1", "CreateVolume", True),
        ("arn:aws:ec2:r:a:volume/vol-1", "CreateSnapshot", False),
        ("arn:aws:ec2:r:a:volume/vol-1", "CreateTags", False),
        ("arn:aws:ec2:r:a:natgateway/nat-1", "CreateNatGateway", True),
        ("arn:aws:ec2:r:a:elastic-ip/eipalloc-1", "AllocateAddress", True),
        ("arn:aws:rds:r:a:db:orders", "CreateDBInstance", True),
        ("arn:aws:rds:r:a:db:orders", "CreateDBSnapshot", False),
        ("arn:aws:s3:::fake-bucket", "CreateBucket", True),
        ("arn:aws:lambda:r:a:function:resize", "CreateFunction20150331", True),
        ("arn:aws:ec2:r:a:instance/i-1", "DescribeInstances", False),
    ],
)
def test_only_an_event_creating_the_resources_type_is_its_creation(
    resource: str, name: str, creates: bool
) -> None:
    # The request names the resource, as a bucket's or a database's does: a type needs no more.
    made = event("evt-1", name, fixtures.AS_OF - timedelta(days=5), pipeline("deploy"), {"id": 1})
    found = lookup({names_of(resource)[0]: [made]}, resource)
    assert isinstance(found, Creator) is creates


def test_without_a_type_an_event_whose_request_names_the_resource_did_not_create_it() -> None:
    resource = "amazonec2/fake-product-b/0009"
    found = lookup({resource: [tagged(resource, fixtures.AS_OF)]}, resource)
    assert isinstance(found, BeforeHistory)


def test_the_earliest_creation_in_the_history_is_the_one_named() -> None:
    earlier = event("evt-early", "RunInstances", fixtures.AS_OF - timedelta(days=20), person("a"))
    later = event("evt-late", "RunInstances", fixtures.AS_OF - timedelta(days=2), person("b"))
    found = lookup({"i-0fake": [later, earlier]})
    assert isinstance(found, Creator)
    assert (found.principal, found.event_id) == ("a", "evt-early")


def test_a_resource_cloudtrail_records_by_its_arn_is_found_by_it() -> None:
    balancer = "arn:aws:elasticloadbalancing:r:a:loadbalancer/app/web/50dc6c495c0c9188"
    made = event("evt-lb", "CreateLoadBalancer", fixtures.AS_OF, pipeline("deploy-pipeline"))
    trail = StubTrail({balancer: [made]})
    found = adapter(trail).creator(ACCOUNT, REGION, balancer)
    assert isinstance(found, Creator)
    asked = [one["LookupAttributes"][0]["AttributeValue"] for one in trail.requests]
    assert asked == ["50dc6c495c0c9188", balancer]


def test_a_creation_older_than_the_window_is_not_read() -> None:
    made = event("evt-old", "RunInstances", fixtures.AS_OF - timedelta(days=91), person("a"))
    found = lookup({"i-0fake": [made]})
    assert isinstance(found, BeforeHistory)
    assert found.history_starts == fixtures.AS_OF - timedelta(days=HISTORY_DAYS)


def test_the_window_and_page_size_asked_are_the_documented_ones() -> None:
    trail = StubTrail(planted())
    adapter(trail).creator(ACCOUNT, REGION, OLDER)
    (request,) = trail.requests
    assert request["EndTime"] - request["StartTime"] == timedelta(days=HISTORY_DAYS)
    assert request["PaginationConfig"] == {"PageSize": PAGE_SIZE}
    assert request["LookupAttributes"] == [
        {"AttributeKey": "ResourceName", "AttributeValue": OLDER}
    ]


# --- who created it -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("identity", "named"),
    [
        (person("dev.lead@fake.example"), ("dev.lead@fake.example", OwnerKind.PERSON)),
        (pipeline("deploy-pipeline"), ("deploy-pipeline", OwnerKind.AUTOMATION)),
        ({"type": "IAMUser", "userName": "ana"}, ("ana", OwnerKind.PERSON)),
        ({"type": "FederatedUser", "principalId": "fake:ben"}, ("ben", OwnerKind.PERSON)),
        ({"type": "Root", "arn": "arn:aws:iam::fake:root"}, ("root", OwnerKind.PERSON)),
        (
            {"type": "AWSService", "invokedBy": "autoscaling.amazonaws.com"},
            ("autoscaling.amazonaws.com", OwnerKind.AUTOMATION),
        ),
    ],
)
def test_a_creator_is_a_person_or_a_pipeline_by_who_signed_in(
    identity: dict[str, Any], named: tuple[str, OwnerKind]
) -> None:
    found = lookup({"i-0fake": [event("evt-1", "RunInstances", fixtures.AS_OF, identity)]})
    assert isinstance(found, Creator)
    assert (found.principal, found.kind) == named


@pytest.mark.parametrize(
    "identity",
    [
        # The sign-in role with no session name is the role, not a person.
        {"type": "AssumedRole", "sessionContext": {"sessionIssuer": {"userName": SSO}}},
        {"type": "AssumedRole"},
        {"type": "AWSService"},
        {},
    ],
)
def test_a_creator_this_cannot_name_is_schema_drift(identity: dict[str, Any]) -> None:
    with pytest.raises(SchemaDrift, match="names its principal"):
        lookup({"i-0fake": [event("evt-1", "RunInstances", fixtures.AS_OF, identity)]})


@pytest.mark.parametrize(
    ("change", "says"),
    [
        ({"CloudTrailEvent": "not json"}, "cannot read"),
        ({"CloudTrailEvent": "[1]"}, "cannot read"),
        ({"EventId": ""}, "no time or id"),
        ({"EventTime": "yesterday"}, "no time or id"),
    ],
)
def test_a_creating_event_this_cannot_read_is_schema_drift(
    change: dict[str, Any], says: str
) -> None:
    made = {**event("evt-1", "RunInstances", fixtures.AS_OF, person("a")), **change}
    with pytest.raises(SchemaDrift, match=says):
        adapter(StubTrail({"i-0fake": [made]}, raw=True)).creator(ACCOUNT, REGION, INSTANCE)


# --- the rate and refusals ------------------------------------------------------------


def test_requests_are_paced_to_two_a_second_in_one_account_and_region() -> None:
    slept: list[float] = []
    creators = adapter(StubTrail(planted()), sleep=slept.append)
    # Two pages, the creation and the tag after it, then a second lookup in the same place.
    creators.creator(ACCOUNT, REGION, "amazonec2/fake-product-b/0003")
    creators.creator(ACCOUNT, REGION, OLDER)
    assert slept == [0.5, 0.5]
    creators.creator(ACCOUNT, "us-fake-2", OLDER)
    assert slept == [0.5, 0.5], "another Region keeps its own pace"


def test_no_wait_is_added_once_the_rate_allows_the_next_request() -> None:
    slept: list[float] = []
    seconds = iter(float(second) for second in range(100))
    creators = adapter(StubTrail(planted()), sleep=slept.append, monotonic=lambda: next(seconds))
    creators.creator(ACCOUNT, REGION, "amazonec2/fake-product-b/0003")
    assert slept == []


def test_a_refused_lookup_is_raised_by_its_cause_with_the_account_and_region() -> None:
    trail = StubTrail(planted(), "AccessDeniedException")
    with pytest.raises(AccessDenied) as raised:
        adapter(trail).creator(ACCOUNT, REGION, OLDER)
    assert raised.value.scope_key == f"{ACCOUNT.account_id}:{REGION}"
