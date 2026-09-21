"""Role health in memory, so a demo estate shows the states the screen is for.

The Accounts screen exists to separate four answers that look alike from a
distance: the role works, the role is not there yet, the role is there and its
policy is wrong, and we could not tell which. A fake that reports every account
healthy would let that screen look finished while it renders one case.

The plan is data. A caller states which accounts are in which state rather than
patching a method, so a test reads as the estate it is describing.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from finops_core.domain.account import AccountHealth, AccountKey, RoleHealth
from finops_core.errors import Throttled
from finops_fakes import fixtures

COLLECTOR = "account_health"

#: The account the provider fixtures already refuse is refused here too, and one
#: more has no role at all. Two different fixes, two different owners, which is
#: the distinction `RoleHealth` exists to carry.
DEFAULT_PLAN: Mapping[str, tuple[RoleHealth, str]] = {
    str(fixtures.DENIED_ACCOUNT_KEY): (
        RoleHealth.ACCESS_DENIED,
        "the trust policy names another principal",
    ),
    str(fixtures.ACCOUNT_KEYS[3]): (
        RoleHealth.NOT_DEPLOYED,
        "no MeterCollector role in this account",
    ),
}


class FakeRoleHealth:
    """`RoleHealthCheck` in memory, with a stated plan."""

    def __init__(
        self,
        plan: Mapping[str, tuple[RoleHealth, str]] | None = None,
        refuse: str | None = None,
        at: datetime | None = None,
    ) -> None:
        # When the check was made. The fixture constants are right for a test
        # asserting a value and wrong for a demo estate. ISS-161.
        self._at = at
        self._plan = dict(DEFAULT_PLAN if plan is None else plan)
        # An account the check cannot complete at all, which is a different fact
        # from an account that answers `access denied`. The first is a failed
        # run, the second is a successful run recording bad news, and a screen
        # that showed them alike would send both to the same wrong owner.
        self._refuse = refuse

    def check(self, account: AccountKey, region: str) -> AccountHealth:
        if self._refuse is not None and str(account) == self._refuse:
            raise Throttled(
                scope_key=f"{account}:{region}",
                collector=COLLECTOR,
                detail="rate exceeded for sts:AssumeRole",
            )
        health, error = self._plan.get(str(account), (RoleHealth.HEALTHY, ""))
        # The region is named in the message rather than ignored. A role check
        # is per account and per region, and an error that does not say which
        # region was refused sends a reader to look in the wrong one.
        error = f"{error} in {region}" if error else ""
        return AccountHealth(
            key=account,
            health=health,
            error=error,
            as_of=self._at or fixtures.AS_OF,
            collected_at=self._at or fixtures.COLLECTED_AT,
        )
