"""Reading service quotas and how much of each is used.

P0 does not implement this either. See `finops_core.ports.inventory` for why it
is defined anyway.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from finops_core.domain.account import AccountKey
from finops_core.domain.quota import QuotaUsage


@runtime_checkable
class QuotaSource(Protocol):
    """Reads the quotas that apply to an account and region."""

    def list_quotas(self, account: AccountKey, region: str) -> Iterable[QuotaUsage]:
        """Every quota for the account and region, with usage where published.

        Raises:
            AccessDenied: The session may not read quotas in this account.
            NotOptedIn: The quota service has never been enabled here.
            Throttled: The provider rejected the call rate.
            Unreachable: The quota endpoint did not answer.
            SchemaDrift: A quota arrived without the limit this adapter expects.
        """
        ...
