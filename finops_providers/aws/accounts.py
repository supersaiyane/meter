"""Building the organization tree from the Organizations API.

The tree is read, never inferred. Probing for child accounts is slower, gives an
incomplete answer, and gets rate limited for the privilege. `ListRoots` and the
two per parent calls return the exact tree, so that is what this walks.

Nothing here returns a raw API shape. The moment an ARN or a boto dictionary
reaches a caller, the abstraction that makes a second provider a connector has
already failed, and nobody finds out until the second provider arrives.

No call is unpaginated. An organization at the scale this project targets does
not fit in one page, and an unpaginated call does not fail: it quietly returns
the first hundred accounts, which then become the denominator for every total on
every screen.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Iterator
from datetime import UTC, datetime
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from finops_core.config import Settings
from finops_core.constants import THROTTLE_BACKOFF_BASE_SECONDS
from finops_core.domain.account import AccountKey, AccountStatus, CloudAccount, Provider
from finops_core.domain.org import OrgNode, OrgNodeType
from finops_core.errors import Throttled
from finops_providers.aws.client import botocore_config, translate

Clock = Callable[[], datetime]
Sleeper = Callable[[float], None]
ClientFactory = Callable[[], Any]

COLLECTOR = "org_tree"
ORGANIZATION_SCOPE = "organization"

#: What the provider calls a status, and what the domain calls it. Anything not
#: listed becomes UNKNOWN rather than being dropped, because a dropped account
#: shrinks the denominator behind every organization total. ISS-016.
STATUS_MAP = {
    "ACTIVE": AccountStatus.ACTIVE,
    "SUSPENDED": AccountStatus.SUSPENDED,
    "PENDING_CLOSURE": AccountStatus.DEPARTED,
}


def _system_clock() -> datetime:
    return datetime.now(UTC)


class AwsAccountDiscovery:
    """Reads which accounts exist and how they are arranged.

    The client arrives already authenticated. How it was authenticated, whether
    by the hub's own credentials or by assuming the organization reader role, is
    the caller's business and not something this class should know.
    """

    def __init__(
        self,
        settings: Settings,
        client_factory: ClientFactory | None = None,
        clock: Clock = _system_clock,
        sleeper: Sleeper = time.sleep,
    ) -> None:
        self._settings = settings
        self._clock = clock
        self._sleeper = sleeper
        self._config = botocore_config(settings)
        self._factory = client_factory or self._default_client
        self._client: Any | None = None

    def _default_client(self) -> Any:
        return boto3.client("organizations", config=self._config)

    @property
    def client(self) -> Any:
        if self._client is None:
            self._client = self._factory()
        return self._client

    # -- the public ports --------------------------------------------------

    def list_accounts(self) -> Iterable[CloudAccount]:
        return self._walk()[1]

    def describe_organization(self) -> Iterable[OrgNode]:
        return self._walk()[0]

    # -- the walk ----------------------------------------------------------

    def _walk(self) -> tuple[tuple[OrgNode, ...], tuple[CloudAccount, ...]]:
        at = self._clock()
        nodes: list[OrgNode] = []
        accounts: list[CloudAccount] = []

        for root in self._paginate("list_roots", "Roots"):
            nodes.append(
                OrgNode(
                    node_id=str(root["Id"]),
                    node_type=OrgNodeType.ROOT,
                    name=str(root.get("Name", root["Id"])),
                    parent_id=None,
                    provider=Provider.AWS,
                    as_of=at,
                    collected_at=at,
                )
            )
            self._descend(str(root["Id"]), nodes, accounts, at)

        return tuple(nodes), tuple(accounts)

    def _descend(
        self,
        parent_id: str,
        nodes: list[OrgNode],
        accounts: list[CloudAccount],
        at: datetime,
    ) -> None:
        for unit in self._paginate(
            "list_organizational_units_for_parent",
            "OrganizationalUnits",
            ParentId=parent_id,
        ):
            nodes.append(
                OrgNode(
                    node_id=str(unit["Id"]),
                    node_type=OrgNodeType.OU,
                    name=str(unit.get("Name", unit["Id"])),
                    parent_id=parent_id,
                    provider=Provider.AWS,
                    as_of=at,
                    collected_at=at,
                )
            )
            self._descend(str(unit["Id"]), nodes, accounts, at)

        for entry in self._paginate("list_accounts_for_parent", "Accounts", ParentId=parent_id):
            account_id = str(entry["Id"])
            # A suspended or departing account is kept, with its real status. It
            # is still an account, and omitting it makes every total wrong by an
            # amount nobody can see.
            status = STATUS_MAP.get(str(entry.get("Status", "")), AccountStatus.UNKNOWN)
            nodes.append(
                OrgNode(
                    node_id=account_id,
                    node_type=OrgNodeType.ACCOUNT,
                    name=str(entry.get("Name", account_id)),
                    parent_id=parent_id,
                    provider=Provider.AWS,
                    as_of=at,
                    collected_at=at,
                )
            )
            accounts.append(
                CloudAccount(
                    key=AccountKey(provider=Provider.AWS, account_id=account_id),
                    name=str(entry.get("Name", account_id)),
                    status=status,
                    parent_node_id=parent_id,
                    as_of=at,
                    collected_at=at,
                )
            )

    # -- calling the provider ----------------------------------------------

    def _paginate(self, operation: str, key: str, **kwargs: Any) -> Iterator[dict[str, Any]]:
        """Every page, always. There is no unpaginated path through this class."""
        paginator = self.client.get_paginator(operation)
        attempt = 0
        while True:
            try:
                for page in paginator.paginate(**kwargs):
                    yield from page.get(key, [])
                return
            except (ClientError, BotoCoreError) as failure:
                typed = translate(failure, scope_key=ORGANIZATION_SCOPE, collector=COLLECTOR)
                if not isinstance(typed, Throttled) or attempt >= self._settings.aws_max_retries:
                    raise typed from failure
                # Wait rather than sprint. This API is throttled globally, so a
                # tight retry across three hundred accounts throttles harder.
                self._sleeper(THROTTLE_BACKOFF_BASE_SECONDS * (2**attempt))
                attempt += 1
