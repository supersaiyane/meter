"""Whether the collector role in a member account is actually usable.

Onboarding fails silently by default. A StackSet that never reached an account,
or a trust policy with the wrong principal, produces no error anywhere until a
collector runs and returns nothing, and nothing renders as zero. This check
turns that into a state on the account, visible before anyone trusts a number.

`NOT_DEPLOYED` versus `ACCESS_DENIED` is the whole point, and it needs saying
plainly: STS cannot tell them apart. Assuming a role that does not exist and
assuming a role whose trust policy refuses you both return `AccessDenied`, with
messages that differ by account and by day. Guessing from the message text would
produce a confident answer that is wrong for half the cases, and the two answers
send the fix to different people.

So the authoritative signal is the deployment itself. `deployment_probe` reports
whether the StackSet reached the account, and TASK-P0-014 supplies the real one.
Without it, a refusal is `UNKNOWN` with the provider's own message recorded,
which is honest: it says "one of these two, here is what it said" rather than
naming an owner at random.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from finops_core.domain.account import AccountHealth, AccountKey, RoleHealth
from finops_core.errors import (
    AccessDenied,
    CollectionError,
    NotOptedIn,
    Throttled,
    Unreachable,
)

Clock = Callable[[], datetime]
#: Reports whether the collector role has been deployed to this account.
DeploymentProbe = Callable[[AccountKey], bool]

COLLECTOR = "account_health"

UNDECIDED_REMEDIATION = (
    "The role could not be assumed, and the provider did not say whether it is "
    "missing or refusing. Check that the StackSet reached this account first, "
    "then check the trust policy on the role."
)


def _system_clock() -> datetime:
    return datetime.now(UTC)


class AccountHealthCheck:
    """Assumes the role and makes one cheap call, then names what went wrong."""

    def __init__(
        self,
        broker: Any,
        deployment_probe: DeploymentProbe | None = None,
        clock: Clock = _system_clock,
    ) -> None:
        self._broker = broker
        self._probe = deployment_probe
        self._clock = clock

    def check(self, account: AccountKey, region: str) -> AccountHealth:
        at = self._clock()
        try:
            session = self._broker.session_for(account, region)
            # One cheap call, because a session object proves the assume worked
            # and nothing else. A role that can be assumed but cannot read is
            # still a broken onboarding.
            session.session.client("sts", region_name=region).get_caller_identity()
        except CollectionError as failure:
            return AccountHealth(
                key=account,
                health=self._classify(account, failure),
                error=self._describe(failure),
                as_of=at,
                collected_at=at,
            )
        except Exception as failure:
            return AccountHealth(
                key=account,
                health=RoleHealth.UNKNOWN,
                error=f"{type(failure).__name__}: {failure}",
                as_of=at,
                collected_at=at,
            )
        return AccountHealth(
            key=account, health=RoleHealth.HEALTHY, error="", as_of=at, collected_at=at
        )

    def _classify(self, account: AccountKey, failure: CollectionError) -> RoleHealth:
        if isinstance(failure, Throttled):
            # Not a verdict on the role. The next run decides.
            return RoleHealth.THROTTLED
        if isinstance(failure, AccessDenied):
            if self._probe is None:
                return RoleHealth.UNKNOWN
            return RoleHealth.ACCESS_DENIED if self._probe(account) else RoleHealth.NOT_DEPLOYED
        if isinstance(failure, NotOptedIn | Unreachable):
            return RoleHealth.UNKNOWN
        return RoleHealth.UNKNOWN

    def _describe(self, failure: CollectionError) -> str:
        """The provider's own words plus what to do, so nobody has to read logs."""
        detail = failure.detail or failure.cause
        if isinstance(failure, AccessDenied) and self._probe is None:
            return f"{detail}. {UNDECIDED_REMEDIATION}"
        return f"{detail}. {failure.remediation}"
