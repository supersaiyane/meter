"""Locating and reading billing data, already normalized to FOCUS 1.4.

ADR-0002. Normalization happens in the adapter, at ingest, so that every
consumer above this line reads one schema. A port that returned a provider's
own billing shape would push that mapping into every caller.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from typing import Protocol, runtime_checkable

from finops_core.domain.cost import CostRecord


@runtime_checkable
class CostExport(Protocol):
    """Finds the billing export and reads charge rows out of it."""

    def latest_available_period(self) -> date | None:
        """The most recent billing period the export actually holds.

        None where the export exists but has published nothing yet, which is a
        different thing from an export that is missing.

        Raises:
            AccessDenied: The export bucket or its key prefix is not readable.
            NotOptedIn: Data exports have never been configured for this payer.
            Unreachable: The storage endpoint did not answer.
        """
        ...

    def read_period(self, period_start: date, period_end: date) -> Iterable[CostRecord]:
        """Every charge row covering the period, normalized to FOCUS 1.4.

        Raises:
            AccessDenied: The export bucket or its key prefix is not readable.
            NoData: The export holds no rows for this period. This is the one
                cause a caller may render as a zero.
            Throttled: The provider rejected the read rate.
            Unreachable: The storage endpoint did not answer.
            SchemaDrift: A column is missing or has changed type, so the rows
                were not trusted rather than partially parsed.
        """
        ...
