"""How the hub reaches AWS for a collector: its own clients, a member account's, and the relay.

FEAT-079, TASK-P12-002. Every adapter takes a client, or a function that makes one, so a test can
hand it a stub; this module is what hands it the real thing in a deployment. It holds no logic
an adapter does not already have, only which credentials and which endpoint each read uses.

**Every client is made on first use.** Building a collector for a unit happens before the unit
runs and inside no adapter's error handling, so a client made then would surface a missing Region
or an expired credential as an untyped exception outside the collector. Made on the adapter's
first call, the same failure arrives where the adapter translates it into a typed cause.

**A member account is reached through the credential broker**, the same path the worker takes
for an account scoped unit, so an organization wide collector that reads several accounts, the
ownership catalogue and the edge supplement, assumes exactly the role the worker would have.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any, Final

import boto3
from botocore.config import Config

from finops_core.config import Settings
from finops_core.domain.account import AccountKey, Provider
from finops_providers.aws.appregistry import AwsServiceCatalogue
from finops_providers.aws.client import botocore_config
from finops_providers.aws.credentials import AwsCredentialBroker
from finops_providers.aws.relay_client import RelayClient, lambda_invoke, s3_fetch

#: Where Budgets, Invoicing, the Price List and Savings Plans rates answer.
GLOBAL_REGION: Final = "us-east-1"  # allow-hardcoded: these services answer in one Region only

#: Makes a client for one service in one account and Region: (service, account_id, region).
MemberClients = Callable[[str, str, str], Any]


class LazyClient:
    """A client made the first time anything is asked of it, and once."""

    def __init__(self, make: Callable[[], Any]) -> None:
        self._make = make
        self._client: Any = None

    def __getattr__(self, name: str) -> Any:
        if self._client is None:
            self._client = self._make()
        return getattr(self._client, name)


def hub_client(settings: Settings, service: str, region: str | None = None) -> LazyClient:
    """A client on the hub's own credentials, in `region` or the hub's own when None."""
    return LazyClient(
        lambda: boto3.client(service, region_name=region, config=botocore_config(settings))
    )


def queue_client(settings: Settings, long_poll_seconds: int) -> Any:
    """The hub's SQS client, its read timeout outlasting the long poll it is used for.

    A receive holds the connection open for up to `long_poll_seconds`, so a read timeout shorter
    than that would fail every empty poll. Made at once: a worker that cannot make its queue
    client has nothing to do, and should fail at start rather than on its first receive.
    """
    config = botocore_config(settings).merge(
        Config(read_timeout=max(settings.aws_read_timeout_seconds, long_poll_seconds + 10))
    )
    return boto3.client("sqs", config=config)


def session_clients(settings: Settings, session: Any) -> Callable[[str, str], Any]:
    """Clients on one assumed session, the one the worker resolved for an account scoped unit."""

    def make(service: str, region: str) -> Any:
        return session.client(service, region_name=region, config=botocore_config(settings))

    return make


def member_clients(settings: Settings, broker: Any = None) -> MemberClients:
    """Clients in any member account, each on the role the broker assumes there."""
    resolved = broker if broker is not None else AwsCredentialBroker(settings)

    def make(service: str, account_id: str, region: str) -> Any:
        def assumed() -> Any:
            account = AccountKey(provider=Provider.AWS, account_id=account_id)
            return session_clients(settings, resolved.session_for(account, region).session)(
                service, region
            )

        return LazyClient(assumed)

    return make


def relay(settings: Settings, *, service: str, region: str, account_id: str | None) -> RelayClient:
    """A client in shape for a service the hub reaches only through the relay, ADR-0035.

    The caller checks `relay_function_name` and `s3_bucket` are set first, because only the
    caller knows which collector to name when they are not.
    """
    return RelayClient(
        service=service,
        region=region,
        account_id=account_id,
        invoke=lambda_invoke(hub_client(settings, "lambda"), settings.relay_function_name),
        fetch=s3_fetch(hub_client(settings, "s3"), settings.s3_bucket),
    )


def payer_of(settings: Settings) -> str | None:
    """The payer account: the management account, where the org reader role lives.

    In AWS Organizations the management account pays for every member, so the account in the
    org reader role's ARN is the payer. None when that setting is not an IAM role ARN.
    """
    parts = settings.org_reader_role_arn.split(":")
    if len(parts) != 6 or parts[2] != "iam" or not parts[5].startswith("role/"):
        return None
    account = parts[4]
    return account if len(account) == 12 and account.isdigit() else None


class PerAccountCatalogue:
    """The AppRegistry catalogue of whichever account is asked, on that account's role.

    `AwsServiceCatalogue` reads one account through the client it is handed. The ownership
    collector runs once for the organization and asks account by account, so this builds the
    adapter for the account in hand.
    """

    def __init__(self, *, member: MemberClients, owner_key: str) -> None:
        self._member = member
        self._owner_key = owner_key

    def applications(self, account: AccountKey, region: str) -> Iterable[Any]:
        catalogue = AwsServiceCatalogue(
            client_factory=lambda service, where: self._member(service, account.account_id, where),
            owner_key=self._owner_key,
        )
        return catalogue.applications(account, region)
