"""One observed metric value. Deliberately thin.

The full shape of a time series belongs to the sub project that first reads
one. What has to exist now is a return type for `MetricSource` that names no
provider, because a port returning a provider shaped object is a port that has
already failed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from finops_core.domain.account import AccountKey
from finops_core.domain.fact import Fact


@dataclass(frozen=True, kw_only=True)
class MetricPoint(Fact):
    """One statistic of one metric, at one instant, for one account."""

    account_key: AccountKey
    namespace: str
    metric_name: str
    statistic: str
    unit: str
    value: Decimal
    #: The instant the value describes, which is not always `as_of`.
    at: datetime
