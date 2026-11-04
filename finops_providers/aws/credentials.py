"""Assuming the collector role in a member account, with caching and typed failure.

ADR-0004. The hub assumes a role each member account trusts, so the only long
lived credential in the system belongs to the hub and every member account can
revoke us by deleting one role.

Two behaviours are worth stating because getting either wrong is quiet.

A session is reused until shortly before it expires, never past it. Serving an
expired session produces errors that read like permission problems, and the
person debugging spends an afternoon on a trust policy that was fine.

The ExternalId is read once from the secret store and never written anywhere
else. It is the thing that stops a confused deputy, so it does not belong in a
log line, an error detail, or a cache key.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from finops_core.config import Settings
from finops_core.constants import SESSION_REFRESH_MARGIN_SECONDS
from finops_core.domain.account import AccountKey
from finops_providers.aws.client import botocore_config, role_arn, translate

Clock = Callable[[], datetime]
ClientFactory = Callable[[str, str], object]

COLLECTOR = "credential_broker"
SESSION_NAME = "meter-collector"


def _system_clock() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class AwsSession:
    """An assumed role session. Satisfies `ProviderSession`, opaque to the domain."""

    account: AccountKey
    region: str
    session: boto3.Session
    expires_at: datetime


class AwsCredentialBroker:
    """Produces a scoped session for a target account, and caches it sensibly."""

    def __init__(
        self,
        settings: Settings,
        client_factory: ClientFactory | None = None,
        clock: Clock = _system_clock,
    ) -> None:
        self._settings = settings
        self._clock = clock
        self._config = botocore_config(settings)
        self._factory = client_factory or self._default_client
        self._cache: dict[tuple[str, str], AwsSession] = {}
        self._external_id: str | None = None

    def _default_client(self, service: str, region: str) -> object:
        return boto3.client(service, region_name=region, config=self._config)

    def external_id(self, region: str) -> str:
        """Read the ExternalId once. Never logged, never put in an error detail."""
        if self._external_id is None:
            client = self._factory("secretsmanager", region)
            try:
                response = client.get_secret_value(  # type: ignore[attr-defined]
                    SecretId=self._settings.external_id_secret
                )
            except (ClientError, BotoCoreError) as failure:
                raise translate(
                    failure,
                    scope_key=f"secret:{self._settings.external_id_secret}",
                    collector=COLLECTOR,
                ) from failure
            self._external_id = str(response["SecretString"])
        return self._external_id

    def session_for(self, account: AccountKey, region: str) -> AwsSession:
        key = (account.account_id, region)
        cached = self._cache.get(key)
        if cached is not None and self._is_fresh(cached):
            return cached

        scope_key = f"{account}:{region}"
        client = self._factory("sts", region)
        try:
            response = client.assume_role(  # type: ignore[attr-defined]
                RoleArn=role_arn(account.account_id, self._settings.collector_role_name, region),
                RoleSessionName=SESSION_NAME,
                ExternalId=self.external_id(region),
            )
        except (ClientError, BotoCoreError) as failure:
            raise translate(failure, scope_key=scope_key, collector=COLLECTOR) from failure

        credentials = response["Credentials"]
        built = AwsSession(
            account=account,
            region=region,
            session=boto3.Session(
                aws_access_key_id=credentials["AccessKeyId"],
                aws_secret_access_key=credentials["SecretAccessKey"],
                aws_session_token=credentials["SessionToken"],
                region_name=region,
            ),
            expires_at=_as_utc(credentials["Expiration"]),
        )
        self._cache[key] = built
        return built

    def _is_fresh(self, session: AwsSession) -> bool:
        margin = timedelta(seconds=SESSION_REFRESH_MARGIN_SECONDS)
        return session.expires_at - margin > self._clock()


def _as_utc(value: datetime) -> datetime:
    """botocore returns aware datetimes, but a naive one would compare wrongly."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
