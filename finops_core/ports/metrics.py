"""Reading time series for a resource.

Batching is the adapter's problem, not the caller's. `METER_GETMETRICDATA_BATCH_SIZE`
exists because one provider charges per metric requested per call, and hiding that
behind the port is the point of having one.

That claim was not true until 2026-09-21. The port declared only `read_series`,
which takes one metric, and an adapter handed one metric at a time cannot batch
anything: the setting existed, and nothing could honour it. `read_many` is the
method that makes the sentence above accurate, and `read_series` is now the
one metric case of it.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from finops_core.domain.account import AccountKey
from finops_core.domain.metrics import MetricPoint


@dataclass(frozen=True)
class MetricRequest:
    """One series a caller wants, named so a batch can be correlated back.

    `key` is the caller's own identifier and is returned untouched. A batch of five
    hundred series comes back as a mapping, and without a key the caller would have
    to match responses to requests by position, which is the kind of correspondence
    that survives exactly until somebody filters the list.
    """

    key: str
    account: AccountKey
    region: str
    namespace: str
    metric_name: str
    dimensions: Mapping[str, str]
    statistic: str


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

    def read_many(
        self,
        requests: Iterable[MetricRequest],
        window_start: datetime,
        window_end: datetime,
        period_seconds: int,
    ) -> Mapping[str, tuple[MetricPoint, ...]]:
        """Every point for many series, keyed by each request's own `key`.

        The method that lets an adapter honour `METER_GETMETRICDATA_BATCH_SIZE`.
        Reading a three hundred account estate one series at a time is a line item
        that shows up on our own platform cost screen.

        **A key absent from the result means unobserved, not zero.** A resource
        that published nothing is not a resource that used nothing, and a caller
        that read an absent key as zero would recommend terminating a running
        system. Callers must distinguish the two, and the return type makes the
        absence visible rather than filling it in.

        Raises:
            AccessDenied: The session may not read metrics in this account.
            Throttled: The provider rejected the call rate.
            Unreachable: The metrics endpoint did not answer.
            SchemaDrift: The response held a statistic or unit this adapter does
                not recognise.

        Note that `NoData` is **not** raised. A batch in which some series are
        empty is the normal case, and failing the whole read for it would make the
        method unusable at the scale it exists for.
        """
        ...
