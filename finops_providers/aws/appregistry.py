"""AWS Service Catalog AppRegistry, as the owners of an account's applications. FEAT-077.

TASK-P11-003, P11 spec section 5.3 and OPEN-25. AppRegistry does not list an application's
resources one by one: it associates CloudFormation stacks and a tag value with an application, and
AppRegistry marks the application's own resources with the tag `awsApplication`, whose value is the
application's ARN, as AWS documents it. So this returns each application with the tags that mark
its resources, and the collector matches resources by the tags the inventory already holds.

Five reads per account and Region, each list paged by the paginator botocore ships for it:

- `ListApplications`, and for each application `GetApplication`, whose `applicationTag` holds the
  `awsApplication` value;
- `ListAssociatedResources`, whose `CFN_STACK` entries name the stacks whose resources
  CloudFormation marks with `aws:cloudformation:stack-id`;
- `ListAttributeGroupsForApplication` and `GetAttributeGroup`, whose `attributes` are a JSON
  object; the owner is the first non blank string under the configured key, `owner` by default.

An attribute group that is not a JSON object is SchemaDrift, and so is an application with no id
or name: either fails the account and Region, typed, rather than reading as nobody owning anything.

Read only, constraint 6. The client is the member account's, in its Region, made by the factory
composition binds to that account's session, as `quotas.py` is.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Iterator
from datetime import UTC, datetime
from typing import Any, Final

from botocore.exceptions import BotoCoreError, ClientError

from finops_core.domain.account import AccountKey
from finops_core.domain.ownership import CatalogueApplication
from finops_core.errors import SchemaDrift
from finops_providers.aws.client import translate

COLLECTOR: Final = "ownership"
#: The tag AppRegistry marks an application's resources with, and the one CloudFormation marks a
#: stack's resources with, as AWS names them.
APPLICATION_TAG: Final = "awsApplication"
STACK_TAG: Final = "aws:cloudformation:stack-id"
#: An associated resource of this type is a stack; the other, a tag value, is the application's own.
STACK: Final = "CFN_STACK"


def _system_clock() -> datetime:
    return datetime.now(UTC)


class AwsServiceCatalogue:
    """The applications AppRegistry holds in one account, Region by Region."""

    def __init__(
        self,
        *,
        client_factory: Callable[[str, str], Any],
        owner_key: str = "owner",
        clock: Callable[[], datetime] = _system_clock,
    ) -> None:
        self._client_for = client_factory
        self._owner_key = owner_key
        self._clock = clock

    def applications(self, account: AccountKey, region: str) -> Iterable[CatalogueApplication]:
        scope = f"{account.account_id}:{region}"
        client = self._client_for("servicecatalog-appregistry", region)
        at = self._clock()
        try:
            return tuple(
                self._application(client, summary, account, region, at, scope)
                for summary in _pages(client, "list_applications", "applications")
            )
        except (ClientError, BotoCoreError) as failure:
            raise translate(failure, scope_key=scope, collector=COLLECTOR) from failure

    def _application(
        self,
        client: Any,
        summary: Any,
        account: AccountKey,
        region: str,
        at: datetime,
        scope: str,
    ) -> CatalogueApplication:
        application_id = str(summary.get("id") or "")
        name = str(summary.get("name") or "")
        if not application_id or not name:
            raise SchemaDrift(
                scope_key=scope, collector=COLLECTOR, detail="an application with no id or name"
            )
        marks: set[tuple[str, str]] = set()
        tag = (client.get_application(application=application_id).get("applicationTag") or {}).get(
            APPLICATION_TAG
        )
        if tag:
            marks.add((APPLICATION_TAG, str(tag)))
        for resource in _pages(
            client, "list_associated_resources", "resources", application=application_id
        ):
            if resource.get("resourceType") == STACK and resource.get("arn"):
                marks.add((STACK_TAG, str(resource["arn"])))
        return CatalogueApplication(
            account_key=account,
            region_id=region,
            name=name,
            application_id=application_id,
            owner=self._owner(client, application_id, scope),
            marks=frozenset(marks),
            # The catalogue as it stood when it was read: AppRegistry dates its applications and
            # groups, but not the association that makes this owner true of a resource.
            as_of=at,
            collected_at=at,
        )

    def _owner(self, client: Any, application_id: str, scope: str) -> str | None:
        """The first non blank owner any of the application's attribute groups names."""
        for group in _pages(
            client,
            "list_attribute_groups_for_application",
            "attributeGroupsDetails",
            application=application_id,
        ):
            found = client.get_attribute_group(attributeGroup=group["id"])
            try:
                attributes = json.loads(found.get("attributes") or "{}")
            except ValueError as failure:
                raise _drift(scope, f"attribute group {group['id']} is not JSON") from failure
            if not isinstance(attributes, dict):
                raise _drift(scope, f"attribute group {group['id']} is not a JSON object")
            value = attributes.get(self._owner_key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None


def _pages(client: Any, operation: str, key: str, **request: Any) -> Iterator[Any]:
    """Every item of a list, through the paginator botocore ships for it."""
    for page in client.get_paginator(operation).paginate(**request):
        yield from page.get(key) or ()


def _drift(scope: str, detail: str) -> SchemaDrift:
    return SchemaDrift(scope_key=scope, collector=COLLECTOR, detail=detail)
