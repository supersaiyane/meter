"""Who created a resource, from CloudTrail's event history. FEAT-077, TASK-P11-004.

P11 spec section 5.4 and OPEN-26. `LookupEvents` by `ResourceName`, the ARN's own id and then the
whole ARN since CloudTrail records resources under either, across the history CloudTrail keeps,
90 days of management events as AWS documents it, paged by botocore's paginator and paced to the
rate AWS documents for it, two requests a second per account and Region.

**The creating event.** The earliest event about the resource that created it rather than acted on
it. Its name begins with a creating verb and the noun after the verb is the resource's type, from
the ARN: `RunInstances` creates an `instance`, `CreateNatGateway` a `natgateway`, and `CREATES`
holds the few whose names differ, `CreateDBInstance` for an RDS `db`. So `CreateTags` or
`CreateSnapshot` inside the history never names somebody as the creator of an older volume. An id
that is not an ARN carries no type, and then the creating event is the one whose request does not
name the resource, because a creating call learns the id from its response.

A resource with no creating event in the history is `BeforeHistory`, with where the history
begins, never a guess. One created by an event this does not recognise reads the same way, so a
type found to read as older than it is gets its noun added to `CREATES`.

**Person or pipeline.** The readable name is `principal_of`, the query parser's `principal_from`
handed in by composition, so the places CloudTrail can put a principal are read one way across
Meter. Whether that is a person is decided here, from the identity's type: an IAM user, a federated
user, the account root, and a session under IAM Identity Center's `AWSReservedSSO_` roles are
people; any other assumed role, and an AWS service acting for itself, are automation, named by the
role or the service, because a pipeline's role is not somebody to ask.

Read only, constraint 6. The client is the member account's, in its Region.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any, Final

from botocore.exceptions import BotoCoreError, ClientError

from finops_core.domain.account import AccountKey
from finops_core.domain.ownership import BeforeHistory, Creator, OwnerKind
from finops_core.errors import SchemaDrift
from finops_providers.aws.client import translate

COLLECTOR: Final = "ownership"
#: How far back the event history reaches, as AWS documents it.
HISTORY_DAYS: Final = 90
#: The rate AWS documents for `LookupEvents`, per account and Region.
REQUESTS_PER_SECOND: Final = 2
PAGE_SIZE: Final = 50
#: The verbs the name of an event that creates a resource begins with.
CREATING: Final = ("Create", "Run", "Allocate", "Launch", "Import", "Register", "Copy")
#: The noun an event creates, where it is not the type the ARN names. Keyed by service and type;
#: a type of None is a service whose ARNs name the resource with no type, a bucket or a queue.
CREATES: Final[dict[tuple[str, str | None], str]] = {
    ("rds", "db"): "DBInstance",
    ("rds", "cluster"): "DBCluster",
    ("ec2", "elastic-ip"): "Address",
    ("ec2", "dedicated-host"): "Hosts",
    ("elasticache", "cluster"): "CacheCluster",
    ("s3", None): "Bucket",
    ("sqs", None): "Queue",
    ("sns", None): "Topic",
}
#: The roles IAM Identity Center gives a person who signs in; a session under one is that person.
SSO_ROLE: Final = "AWSReservedSSO_"
#: Identity types that are a person whatever their name.
PEOPLE: Final = frozenset({"IAMUser", "FederatedUser"})

Found = tuple[dict[str, Any], dict[str, Any]]


def _system_clock() -> datetime:
    return datetime.now(UTC)


class AwsResourceCreators:
    """CloudTrail's record of who created each resource, account by account and Region by Region."""

    def __init__(
        self,
        *,
        client_factory: Callable[[str, str, str], Any],
        principal_of: Callable[[Mapping[str, Any]], str | None],
        clock: Callable[[], datetime] = _system_clock,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client_for = client_factory
        self._principal_of = principal_of
        self._clock = clock
        self._sleep = sleep
        self._monotonic = monotonic
        self._last: dict[str, float] = {}

    def creator(
        self, account: AccountKey, region: str, resource_id: str
    ) -> Creator | BeforeHistory:
        scope = f"{account.account_id}:{region}"
        now = self._clock()
        starts = now - timedelta(days=HISTORY_DAYS)
        client = self._client_for("cloudtrail", account.account_id, region)
        found: Found | None = None
        try:
            for name in names_of(resource_id):
                found = self._creating(client, scope, name, resource_id, (starts, now))
                if found is not None:
                    break
        except (ClientError, BotoCoreError) as failure:
            raise translate(failure, scope_key=scope, collector=COLLECTOR) from failure
        if found is None:
            return BeforeHistory(
                account_key=account,
                region_id=region,
                resource_id=resource_id,
                history_starts=starts,
                as_of=now,
                collected_at=now,
            )
        event, detail = found
        principal, kind = self._who(detail, scope)
        created: datetime = event["EventTime"]
        return Creator(
            account_key=account,
            region_id=region,
            resource_id=resource_id,
            principal=principal,
            kind=kind,
            event_id=str(event["EventId"]),
            created_at=created,
            as_of=created,
            collected_at=max(now, created),
        )

    def _creating(
        self,
        client: Any,
        scope: str,
        name: str,
        resource_id: str,
        window: tuple[datetime, datetime],
    ) -> Found | None:
        """The earliest event under this name that created the resource, or None."""
        pages = client.get_paginator("lookup_events").paginate(
            LookupAttributes=[{"AttributeKey": "ResourceName", "AttributeValue": name}],
            StartTime=window[0],
            EndTime=window[1],
            PaginationConfig={"PageSize": PAGE_SIZE},
        )
        earliest: Found | None = None
        self._pace(scope)
        for page in pages:
            for event in page.get("Events") or ():
                detail = _creation(event, resource_id, scope)
                if detail is not None and (
                    earliest is None or event["EventTime"] < earliest[0]["EventTime"]
                ):
                    earliest = (event, detail)
            if page.get("NextToken"):
                # The next page is another request, so the pace is kept between pages too.
                self._pace(scope)
        return earliest

    def _who(self, detail: Mapping[str, Any], scope: str) -> tuple[str, OwnerKind]:
        """The creator's name and whether it is a person, from the event's identity."""
        identity = detail.get("userIdentity") or {}
        kind = identity.get("type")
        role = ((identity.get("sessionContext") or {}).get("sessionIssuer") or {}).get("userName")
        if kind == "Root":
            return "root", OwnerKind.PERSON
        if kind == "AWSService" and identity.get("invokedBy"):
            return str(identity["invokedBy"]), OwnerKind.AUTOMATION
        if kind == "AssumedRole" and role and not str(role).startswith(SSO_ROLE):
            return str(role), OwnerKind.AUTOMATION
        named = self._principal_of(detail)
        # The parser's last resorts, the identity's type or the sign-in role, name nobody.
        somebody = bool(named) and named != kind and not str(named).startswith(SSO_ROLE)
        if named and somebody and (kind in PEOPLE or kind == "AssumedRole"):
            return named, OwnerKind.PERSON
        raise _drift(scope, "the creating event names its principal in no place this reads")

    def _pace(self, scope: str) -> None:
        """At most the documented rate of requests per account and Region."""
        last = self._last.get(scope)
        if last is not None:
            wait = 1 / REQUESTS_PER_SECOND - (self._monotonic() - last)
            if wait > 0:
                self._sleep(wait)
        self._last[scope] = self._monotonic()


def names_of(resource_id: str) -> tuple[str, ...]:
    """The names CloudTrail may record a resource under, the likelier first.

    The inventory holds an ARN. CloudTrail records most resources by their own id, the ARN's last
    segment, `i-0abc` or a bucket's name, and some by the whole ARN, so both are asked.
    """
    if not resource_id.startswith("arn:"):
        return (resource_id,)
    own = resource_id.split(":", 5)[-1].rsplit("/", 1)[-1].rsplit(":", 1)[-1]
    return tuple(dict.fromkeys(name for name in (own, resource_id) if name))


def type_of(resource_id: str) -> tuple[str, str | None] | None:
    """The service and resource type an ARN names, or None for an id that is not an ARN."""
    parts = resource_id.split(":", 5)
    if parts[0] != "arn" or len(parts) < 6:
        return None
    resource = parts[5]
    cuts = [at for at in (resource.find(":"), resource.find("/")) if at >= 0]
    return parts[2], (resource[: min(cuts)] if cuts else None)


def _creation(event: Mapping[str, Any], resource_id: str, scope: str) -> dict[str, Any] | None:
    """The event's detail if it created the resource rather than acted on it, else None."""
    name = str(event.get("EventName") or "")
    verb = next((one for one in CREATING if name.startswith(one)), None)
    if verb is None:
        return None
    typed = type_of(resource_id)
    if typed is not None and _plain(name[len(verb) :]) != _plain(CREATES.get(typed) or typed[1]):
        return None
    try:
        detail = json.loads(event.get("CloudTrailEvent") or "")
    except ValueError as failure:
        raise _drift(scope, "a creating event this cannot read") from failure
    if not isinstance(detail, dict):
        raise _drift(scope, "a creating event this cannot read")
    if typed is None and resource_id in json.dumps(detail.get("requestParameters") or {}):
        # It names the resource it acts on, so the resource existed before it.
        return None
    if not isinstance(event.get("EventTime"), datetime) or not event.get("EventId"):
        raise _drift(scope, "a creating event with no time or id")
    return detail


def _plain(noun: str | None) -> str:
    """A noun compared without case, punctuation, digits or a plural: `Instances` is `instance`."""
    return "".join(c for c in (noun or "").lower() if c.isalpha()).removesuffix("s")


def _drift(scope: str, detail: str) -> SchemaDrift:
    return SchemaDrift(scope_key=scope, collector=COLLECTOR, detail=detail)
