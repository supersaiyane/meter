"""One service quota and how much of it is in use.

`used` is optional because a quota whose usage the provider does not publish is
a real and common case. It is None rather than zero, because zero would read as
plenty of headroom on a quota that is in fact about to be hit.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from finops_core.domain.account import AccountKey
from finops_core.domain.fact import Fact


@dataclass(frozen=True, kw_only=True)
class QuotaUsage(Fact):
    """One quota for one account and region."""

    account_key: AccountKey
    region_id: str
    service_code: str
    quota_code: str
    quota_name: str
    quota_limit: Decimal
    #: None where the provider publishes no usage. Never zero as a stand in.
    used: Decimal | None
