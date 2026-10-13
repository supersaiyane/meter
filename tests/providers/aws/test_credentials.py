"""The broker, and above all the way it fails.

Every collector in the system reaches a member account through this class, so a
mistranslated error here becomes a mistranslated error everywhere. The one that
matters most is the unknown code: mapping it to NoData would render an unknown
failure as a zero, which is the single defect constraint 5 and ISS-015 exist to
prevent. It maps to SchemaDrift, which is loud.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import boto3
import pytest
from botocore.exceptions import ClientError, EndpointConnectionError
from moto import mock_aws

from finops_core.config import Settings
from finops_core.constants import SESSION_REFRESH_MARGIN_SECONDS
from finops_core.domain.account import AccountKey, Provider
from finops_core.errors import (
    AccessDenied,
    Misconfigured,
    NoData,
    NotOptedIn,
    SchemaDrift,
    Throttled,
    Unreachable,
)
from finops_providers.aws.client import botocore_config, partition_for, role_arn
from finops_providers.aws.credentials import AwsCredentialBroker

REGION = "eu-west-1"
ACCOUNT = AccountKey(provider=Provider.AWS, account_id="111122223333")
START = datetime(2026, 8, 24, 6, 0, tzinfo=UTC)
EXTERNAL_ID = "an-external-id-that-must-not-leak"


class MovableClock:
    def __init__(self, at: datetime) -> None:
        self.at = at

    def __call__(self) -> datetime:
        return self.at


class StubClient:
    """A client that answers with whatever the test wants, including a failure."""

    def __init__(self, expiration: datetime, failure: Exception | None = None) -> None:
        self.expiration = expiration
        self.failure = failure
        self.assume_calls = 0
        self.secret_calls = 0

    def get_secret_value(self, **_: Any) -> dict[str, str]:
        self.secret_calls += 1
        return {"SecretString": EXTERNAL_ID}

    def assume_role(self, **_: Any) -> dict[str, Any]:
        self.assume_calls += 1
        if self.failure is not None:
            raise self.failure
        return {
            "Credentials": {
                "AccessKeyId": "AK",
                "SecretAccessKey": "SK",
                "SessionToken": "ST",
                "Expiration": self.expiration,
            }
        }


def client_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": "from the test"}}, "AssumeRole")


def broker_with(settings: Settings, stub: StubClient, clock: MovableClock) -> AwsCredentialBroker:
    return AwsCredentialBroker(settings, client_factory=lambda _s, _r: stub, clock=clock)


# --- the happy path, against moto -------------------------------------------


@mock_aws
def test_assumes_the_collector_role_with_the_external_id(settings: Settings) -> None:
    boto3.client("secretsmanager", region_name=REGION).create_secret(
        Name=settings.external_id_secret, SecretString=EXTERNAL_ID
    )
    session = AwsCredentialBroker(settings).session_for(ACCOUNT, REGION)
    assert session.account == ACCOUNT
    assert session.region == REGION
    assert session.expires_at.tzinfo is not None


@mock_aws
def test_the_session_is_usable_and_scoped_to_the_region(settings: Settings) -> None:
    boto3.client("secretsmanager", region_name=REGION).create_secret(
        Name=settings.external_id_secret, SecretString=EXTERNAL_ID
    )
    session = AwsCredentialBroker(settings).session_for(ACCOUNT, REGION)
    assert session.session.region_name == REGION


# --- caching -----------------------------------------------------------------


def test_a_session_is_reused_until_the_refresh_margin(settings: Settings) -> None:
    clock = MovableClock(START)
    stub = StubClient(expiration=START + timedelta(hours=1))
    broker = broker_with(settings, stub, clock)

    broker.session_for(ACCOUNT, REGION)
    clock.at = START + timedelta(minutes=50)
    broker.session_for(ACCOUNT, REGION)
    assert stub.assume_calls == 1


def test_a_session_is_refreshed_inside_the_margin(settings: Settings) -> None:
    """Never served past expiry, and never served so close that a call dies mid flight."""
    clock = MovableClock(START)
    expiry = START + timedelta(hours=1)
    stub = StubClient(expiration=expiry)
    broker = broker_with(settings, stub, clock)

    broker.session_for(ACCOUNT, REGION)
    clock.at = expiry - timedelta(seconds=SESSION_REFRESH_MARGIN_SECONDS - 1)
    broker.session_for(ACCOUNT, REGION)
    assert stub.assume_calls == 2


def test_an_expired_session_is_never_served(settings: Settings) -> None:
    """An expired session produces errors that read like permission problems."""
    clock = MovableClock(START)
    stub = StubClient(expiration=START + timedelta(minutes=1))
    broker = broker_with(settings, stub, clock)
    broker.session_for(ACCOUNT, REGION)
    clock.at = START + timedelta(minutes=2)
    broker.session_for(ACCOUNT, REGION)
    assert stub.assume_calls == 2


def test_sessions_are_cached_per_account_and_region(settings: Settings) -> None:
    clock = MovableClock(START)
    stub = StubClient(expiration=START + timedelta(hours=1))
    broker = broker_with(settings, stub, clock)
    broker.session_for(ACCOUNT, REGION)
    broker.session_for(ACCOUNT, "eu-west-2")
    other = AccountKey(provider=Provider.AWS, account_id="444455556666")
    broker.session_for(other, REGION)
    assert stub.assume_calls == 3


def test_the_external_id_is_read_once_and_reused(settings: Settings) -> None:
    clock = MovableClock(START)
    stub = StubClient(expiration=START + timedelta(hours=1))
    broker = broker_with(settings, stub, clock)
    broker.session_for(ACCOUNT, REGION)
    broker.session_for(AccountKey(provider=Provider.AWS, account_id="444455556666"), REGION)
    assert stub.secret_calls == 1


# --- failure translation -----------------------------------------------------


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("AccessDenied", AccessDenied),
        ("AccessDeniedException", AccessDenied),
        ("UnauthorizedOperation", AccessDenied),
        ("Throttling", Throttled),
        ("ThrottlingException", Throttled),
        ("TooManyRequestsException", Throttled),
        ("RequestLimitExceeded", Throttled),
        ("AWSOrganizationsNotInUseException", NotOptedIn),
        ("OptInRequired", NotOptedIn),
    ],
)
def test_provider_codes_map_to_the_right_cause(
    settings: Settings, code: str, expected: type[Exception]
) -> None:
    stub = StubClient(expiration=START + timedelta(hours=1), failure=client_error(code))
    broker = broker_with(settings, stub, MovableClock(START))
    with pytest.raises(expected):
        broker.session_for(ACCOUNT, REGION)


def test_an_unknown_code_is_schema_drift_and_never_no_data(settings: Settings) -> None:
    """NoData renders as a zero, so an unknown failure mapped to it reads as free."""
    stub = StubClient(
        expiration=START + timedelta(hours=1), failure=client_error("SomethingBrandNew")
    )
    broker = broker_with(settings, stub, MovableClock(START))
    with pytest.raises(SchemaDrift) as caught:
        broker.session_for(ACCOUNT, REGION)
    assert not isinstance(caught.value, NoData)
    assert "SomethingBrandNew" in caught.value.detail


def test_a_network_failure_is_unreachable(settings: Settings) -> None:
    stub = StubClient(
        expiration=START + timedelta(hours=1),
        failure=EndpointConnectionError(endpoint_url="https://sts.example.invalid"),
    )
    broker = broker_with(settings, stub, MovableClock(START))
    with pytest.raises(Unreachable):
        broker.session_for(ACCOUNT, REGION)


def test_the_failure_names_the_account_and_region_it_was_for(settings: Settings) -> None:
    stub = StubClient(expiration=START + timedelta(hours=1), failure=client_error("AccessDenied"))
    broker = broker_with(settings, stub, MovableClock(START))
    with pytest.raises(AccessDenied) as caught:
        broker.session_for(ACCOUNT, REGION)
    assert caught.value.scope_key == f"{ACCOUNT}:{REGION}"
    assert caught.value.remediation.strip()


def test_the_external_id_never_reaches_an_error_message(settings: Settings) -> None:
    """It is what stops a confused deputy, so it belongs in no log and no error."""
    stub = StubClient(expiration=START + timedelta(hours=1), failure=client_error("AccessDenied"))
    broker = broker_with(settings, stub, MovableClock(START))
    with pytest.raises(AccessDenied) as caught:
        broker.session_for(ACCOUNT, REGION)
    rendered = f"{caught.value} {caught.value.detail} {caught.value.remediation}"
    assert EXTERNAL_ID not in rendered


# --- configuration -----------------------------------------------------------


def test_timeouts_and_retries_come_from_configuration(settings: Settings) -> None:
    """Default retries at three hundred accounts turn throttling into a herd."""
    config = botocore_config(settings)
    assert config.connect_timeout == settings.aws_connect_timeout_seconds
    assert config.read_timeout == settings.aws_read_timeout_seconds
    assert config.retries["max_attempts"] == settings.aws_max_retries
    assert config.retries["mode"] == "standard"


@pytest.mark.parametrize(
    ("region", "partition"),
    [
        ("eu-west-1", "aws"),
        ("us-east-1", "aws"),
        ("cn-north-1", "aws-cn"),
        ("us-gov-west-1", "aws-us-gov"),
    ],
)
def test_the_partition_is_derived_from_the_region(region: str, partition: str) -> None:
    """A literal partition only breaks where being wrong is most expensive."""
    assert partition_for(region) == partition
    assert role_arn("111122223333", "SomeRole", region).startswith(f"arn:{partition}:")


# --- the payer, ISS-294 and ISS-296 ---------------------------------------------


class RecordingSts(StubClient):
    """The stub, recording each role it is asked to assume and in which Region."""

    def __init__(self, expiration: datetime) -> None:
        super().__init__(expiration)
        self.roles: list[str] = []

    def assume_role(self, **kwargs: Any) -> dict[str, Any]:
        self.roles.append(str(kwargs["RoleArn"]))
        assert kwargs["ExternalId"] == EXTERNAL_ID
        return super().assume_role()


PAYER_ROLE = "arn:aws:iam::999988887777:role/MeterOrgReader"


def test_the_payer_session_assumes_the_org_reader_role_with_the_external_id(
    settings: Settings,
) -> None:
    stub = RecordingSts(START + timedelta(hours=1))
    regions: list[str] = []

    def factory(_service: str, region: str) -> RecordingSts:
        regions.append(region)
        return stub

    configured = settings.model_copy(update={"org_reader_role_arn": PAYER_ROLE})
    broker = AwsCredentialBroker(configured, client_factory=factory, clock=MovableClock(START))
    session = broker.payer_session()
    assert stub.roles == [PAYER_ROLE]
    assert session.account.account_id == "999988887777"
    # Through STS in the hub's first collection Region, where it already reaches STS.
    assert set(regions) == {configured.region_list[0]}


def test_the_payer_and_the_management_accounts_collector_role_are_never_confused(
    settings: Settings,
) -> None:
    stub = RecordingSts(START + timedelta(hours=1))
    configured = settings.model_copy(update={"org_reader_role_arn": PAYER_ROLE})
    broker = AwsCredentialBroker(
        configured, client_factory=lambda _s, _r: stub, clock=MovableClock(START)
    )
    region = configured.region_list[0]
    management = AccountKey(provider=Provider.AWS, account_id="999988887777")
    broker.payer_session()
    broker.session_for(management, region)
    broker.payer_session()
    assert stub.roles == [
        PAYER_ROLE,
        role_arn("999988887777", configured.collector_role_name, region),
    ]


def test_a_payer_setting_that_is_not_a_role_arn_is_misconfigured(settings: Settings) -> None:
    broken = settings.model_copy(update={"org_reader_role_arn": "meter-org-reader"})
    stub = StubClient(START + timedelta(hours=1))
    with pytest.raises(Misconfigured, match="METER_ORG_READER_ROLE_ARN"):
        broker_with(broken, stub, MovableClock(START)).payer_session()
    assert stub.assume_calls == 0
