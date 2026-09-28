"""Reading service quotas, how much of each is used, and what was asked for.

Defined in P0 and implemented in P5. See `finops_core.ports.inventory` for why a
port exists before an adapter does.

**Two methods, and neither of them writes.** P5 spec section 4 adds the increase
request history, and it is a second method rather than a widening of the first for
the reason `CommitmentReport` keeps utilization and coverage apart: the two answer
different questions, and one method returning both would invite a caller to assume
the quota it is looking at is the quota a request names. Most requests are for
quotas nothing can measure, so that assumption would be wrong more often than right.

Nothing here can submit a request. Constraint 6 and spec section 6: the port has no
method for it, the AWS adapter never names the API, and the schema carries a column
that can only say Meter did not.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from finops_core.domain.account import AccountKey
from finops_core.domain.quota import QuotaIncreaseRequest, QuotaUsage


@runtime_checkable
class QuotaSource(Protocol):
    """Reads the quotas that apply to an account and region."""

    def list_quotas(self, account: AccountKey, region: str) -> Iterable[QuotaUsage]:
        """Every quota for the account and region, with usage where published.

        Every quota the provider returns produces one entry, including the ones nothing
        can measure. Those carry a null usage and a `usage_source` of NONE. They are
        never omitted and never reported as zero used.

        Raises:
            AccessDenied: The session may not read quotas in this account.
            NotOptedIn: The quota service has never been enabled here.
            Throttled: The provider rejected the call rate.
            Unreachable: The quota endpoint did not answer.
            SchemaDrift: A quota arrived without the limit this adapter expects.
        """
        ...

    def requests(self, account: AccountKey, region: str) -> Iterable[QuotaIncreaseRequest]:
        """Every increase request the provider has a record of, whatever became of it.

        A read, never a write. Includes the refused ones: a denial is the status a
        product is tempted to hide and the one a person most needs to see.

        Raises:
            AccessDenied: The session may not read the request history.
            NotOptedIn: The quota service has never been enabled here.
            Throttled: The provider rejected the call rate.
            Unreachable: The quota endpoint did not answer.
            SchemaDrift: A request arrived in a shape the adapter cannot read.
        """
        ...
