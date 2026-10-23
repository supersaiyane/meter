"""Reading time series for a resource.

Batching is the adapter's problem, not the caller's. `METER_GETMETRICDATA_BATCH_SIZE`
exists because one provider charges per metric requested per call, and hiding
that behind the port is the point of having one.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Protocol, runtime_checkable

from finops_core.domain.account import AccountKey
from finops_core.domain.metrics import MetricPoint


@runtime_checkable
class MetricSource(Protocol):
    """Reads observed values for a resource over a window."""

    def read_series(
        self,
        account: AccountKey,
        region: str,
        namespace: str,
        metric_name: str,
        dimensions: Mapping[str, str],
        statistic: str,
        window_start: datetime,
        window_end: datetime,
    ) -> Iterable[MetricPoint]:
        """Every point for the metric over the window.

        Raises:
            AccessDenied: The session may not read metrics in this account.
            NoData: The metric exists but published nothing in the window. A
                resource that was switched off reaches here, and it is the one
                case where an empty series is the truth.
            Throttled: The provider rejected the call rate.
            Unreachable: The metrics endpoint did not answer.
            SchemaDrift: The response held a statistic or unit this adapter does
                not recognise.
        """
        ...
