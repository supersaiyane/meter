"""Health, and the one distinction that decides who gets paged.

A StackSet that never reached an account and a trust policy with the wrong
principal both produce AccessDenied from STS. They need completely different
fixes from completely different people, so collapsing them into one state sends
half the cases to the wrong owner, confidently.

Since the provider genuinely cannot tell them apart, this check does not guess.
With a deployment probe it answers precisely. Without one it says UNKNOWN and
records what the provider actually said. That is the honest answer, and these
tests exist to keep it honest when somebody later decides a confident guess
would look better on a dashboard.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from finops_core.domain.account import AccountKey, Provider, RoleHealth
from finops_core.errors import (
    AccessDenied,
    NotOptedIn,
    SchemaDrift,
    Throttled,
    Unreachable,
)
from finops_providers.aws.health import AccountHealthCheck

AT = datetime(2026, 8, 24, 6, 0, tzinfo=UTC)
REGION = "eu-west-1"
ACCOUNT = AccountKey(provider=Provider.AWS, account_id="111122223333")


class StubStsClient:
    def __init__(self, failure: Exception | None = None) -> None:
        self.failure = failure
        self.calls = 0

    def get_caller_identity(self) -> dict[str, str]:
        self.calls += 1
        if self.failure is not None:
            raise self.failure
        return {"Account": ACCOUNT.account_id}


class StubBotoSession:
    def __init__(self, sts: StubStsClient) -> None:
        self._sts = sts

    def client(self, _service: str, **_kwargs: Any) -> StubStsClient:
        return self._sts


class StubBrokerSession:
    def __init__(self, sts: StubStsClient) -> None:
        self.session = StubBotoSession(sts)


class StubBroker:
    """Fails on assume, or hands back a session whose cheap call may still fail."""

    def __init__(
        self, assume_failure: Exception | None = None, call_failure: Exception | None = None
    ) -> None:
        self.assume_failure = assume_failure
        self.sts = StubStsClient(call_failure)
        self.assume_calls = 0

    def session_for(self, _account: AccountKey, _region: str) -> StubBrokerSession:
        self.assume_calls += 1
        if self.assume_failure is not None:
            raise self.assume_failure
        return StubBrokerSession(self.sts)


def denied(message: str = "not authorized") -> AccessDenied:
    return AccessDenied(scope_key=str(ACCOUNT), collector="credential_broker", detail=message)


def check(broker: StubBroker, probe: Any = None) -> Any:
    return AccountHealthCheck(broker, deployment_probe=probe, clock=lambda: AT).check(
        ACCOUNT, REGION
    )


# --- the healthy path --------------------------------------------------------


def test_a_usable_role_is_healthy() -> None:
    broker = StubBroker()
    result = check(broker)
    assert result.health is RoleHealth.HEALTHY
    assert result.is_usable is True
    assert result.error == ""


def test_the_check_makes_one_cheap_call_beyond_the_assume() -> None:
    """A session object proves the assume worked and nothing else."""
    broker = StubBroker()
    check(broker)
    assert broker.assume_calls == 1
    assert broker.sts.calls == 1


def test_a_role_that_assumes_but_cannot_read_is_not_healthy() -> None:
    """A broken onboarding that only fails on the first real call is still broken."""
    broker = StubBroker(call_failure=denied("cannot call sts"))
    assert check(broker, probe=lambda _a: True).health is RoleHealth.ACCESS_DENIED


def test_the_result_carries_both_timestamps() -> None:
    result = check(StubBroker())
    assert result.as_of == AT
    assert result.collected_at == AT


# --- the distinction that matters -------------------------------------------


def test_a_deployed_role_that_refuses_is_access_denied() -> None:
    """The role is there and the policy is wrong. That owner fixes the policy."""
    broker = StubBroker(assume_failure=denied())
    assert check(broker, probe=lambda _a: True).health is RoleHealth.ACCESS_DENIED


def test_a_role_that_was_never_deployed_is_not_deployed() -> None:
    """The StackSet never arrived. That owner fixes the deployment."""
    broker = StubBroker(assume_failure=denied())
    assert check(broker, probe=lambda _a: False).health is RoleHealth.NOT_DEPLOYED


def test_without_a_probe_a_refusal_is_unknown_rather_than_a_guess() -> None:
    """STS returns the same code for both, so naming one would be wrong half the time."""
    broker = StubBroker(assume_failure=denied())
    assert check(broker).health is RoleHealth.UNKNOWN


def test_the_two_states_are_never_collapsed_into_one() -> None:
    broker = StubBroker(assume_failure=denied())
    deployed = check(broker, probe=lambda _a: True).health
    absent = check(broker, probe=lambda _a: False).health
    assert deployed is not absent


# --- the other outcomes ------------------------------------------------------


def test_throttling_is_not_a_verdict_on_the_role() -> None:
    """The next run decides. Marking it broken would page somebody for nothing."""
    broker = StubBroker(
        assume_failure=Throttled(scope_key=str(ACCOUNT), collector="credential_broker")
    )
    assert check(broker, probe=lambda _a: True).health is RoleHealth.THROTTLED


@pytest.mark.parametrize(
    "failure",
    [
        NotOptedIn(scope_key=str(ACCOUNT), collector="credential_broker"),
        Unreachable(scope_key=str(ACCOUNT), collector="credential_broker"),
        SchemaDrift(scope_key=str(ACCOUNT), collector="credential_broker"),
    ],
)
def test_anything_that_is_not_a_refusal_or_a_throttle_is_unknown(failure: Exception) -> None:
    assert check(StubBroker(assume_failure=failure)).health is RoleHealth.UNKNOWN


def test_an_unexpected_exception_becomes_unknown_rather_than_escaping() -> None:
    """One account failing must never fail the run. Constraint 5."""
    broker = StubBroker(assume_failure=RuntimeError("something nobody predicted"))
    result = check(broker)
    assert result.health is RoleHealth.UNKNOWN
    assert "RuntimeError" in result.error


# --- what the user is told ---------------------------------------------------


def test_the_error_is_recorded_so_nobody_has_to_read_logs() -> None:
    broker = StubBroker(assume_failure=denied("trust policy names another principal"))
    result = check(broker, probe=lambda _a: True)
    assert "trust policy names another principal" in result.error
    assert result.error.strip().endswith(".")


def test_an_undecided_refusal_says_to_check_both_causes() -> None:
    broker = StubBroker(assume_failure=denied("not authorized"))
    error = check(broker).error
    assert "StackSet" in error
    assert "trust policy" in error


def test_a_decided_refusal_carries_the_remediation_for_that_cause() -> None:
    broker = StubBroker(assume_failure=denied("not authorized"))
    error = check(broker, probe=lambda _a: True).error
    assert "StackSet" in error or "trust policy" in error
    assert error != ""
