"""Running the detector over what the estate actually spent.

The arithmetic is in `finops_query.anomaly` and has no database. This is the
part that reads days out of `cost_focus_daily`, asks for a verdict, and writes
the ones worth a row.

**It judges one day: the most recent one with data.** Re judging the whole
history every run would rewrite verdicts a person may already have acted on, and
an anomaly that disappears because the baseline caught up was still real at the
time. The unique constraint means a second run over the same day replaces rather
than duplicates.

**A pair with too little history gets no row, not a row saying no.** The
detector returns None there and this writes nothing. An empty table for a new
estate is the correct answer, and the screen is what has to tell the reader why
it is empty.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import text

from finops_ingest.registry import CollectorContext, CollectorOutcome
from finops_query.anomaly import MINIMUM_HISTORY, judge
from finops_query.severity import severity_for, thresholds_from

COLLECTOR = "cost_anomaly"
SCOPE = "billing"

#: Days the detector needs in hand: its baseline, plus the day being judged,
#: which is not part of its own baseline.
NEEDED = MINIMUM_HISTORY + 1

#: How far back to read, in calendar days. Twice what is needed, on purpose. A
#: fixed lookback that exactly matches the requirement starves the detector the
#: moment collection falls a day behind or a pair has a gap, which is precisely
#: when somebody wants it still working. The read is generous and the slice
#: below is what decides, so a quiet day costs nothing.
LOOKBACK_DAYS = NEEDED * 2

Clock = Callable[[], datetime]


def _system_clock() -> datetime:
    return datetime.now(UTC)


#: Daily cost by account and service, oldest first, across the window. Ordered
#: in SQL because the detector needs the days in order, and sorting them in
#: Python would be sorting a list that arrived sorted for free.
READ = text(
    "SELECT sub_account_id, service_name, date(charge_period_start) AS day, "
    "SUM(effective_cost) AS cost "
    "FROM cost_focus_daily "
    "WHERE tenant_id = :tenant AND sub_account_id IS NOT NULL "
    "AND date(charge_period_start) > :since "
    "GROUP BY sub_account_id, service_name, date(charge_period_start) "
    "ORDER BY sub_account_id, service_name, day"
)

WRITE = text(
    "INSERT INTO cost_anomaly (anomaly_id, tenant_id, sub_account_id, service_name, day, "
    "observed, baseline, delta, deviations, severity, why, as_of, collected_at) "
    "VALUES (:id, :tenant, :account, :service, :day, :observed, :baseline, :delta, "
    ":deviations, :severity, :why, :as_of, :now) "
    "ON CONFLICT (tenant_id, sub_account_id, service_name, day) DO UPDATE SET "
    "observed = EXCLUDED.observed, baseline = EXCLUDED.baseline, delta = EXCLUDED.delta, "
    "deviations = EXCLUDED.deviations, severity = EXCLUDED.severity, why = EXCLUDED.why, "
    "as_of = EXCLUDED.as_of, collected_at = EXCLUDED.collected_at"
)


def _by_pair(rows: Any) -> dict[tuple[str, str], list[tuple[date, Decimal]]]:
    """Group the flat read into one ordered series per pair.

    A dict of lists rather than a query per pair. At five accounts and five
    services that is twenty five queries saved, and at three hundred accounts it
    is the difference between one read and a fan out.
    """
    series: dict[tuple[str, str], list[tuple[date, Decimal]]] = {}
    for account, service, day, cost in rows:
        series.setdefault((account, service), []).append((day, Decimal(cost)))
    return series


class CostAnomalyCollector:
    """Judges the most recent day of each account and service pair."""

    def __init__(self, clock: Clock = _system_clock) -> None:
        self._clock = clock

    def __call__(self, context: CollectorContext) -> CollectorOutcome:
        if context.settings is None:
            # Not a typed collection failure: nothing about the provider is
            # wrong. Severity comes from the money, per ADR-0016, and the money
            # boundaries are settings. Defaulting them would put an invented
            # severity on a screen, which is worse than refusing to run.
            raise ValueError(
                "cost_anomaly needs settings. Its severity boundaries and its "
                "sensitivity are configuration, not constants."
            )

        at = self._clock()
        since = at.date() - timedelta(days=LOOKBACK_DAYS)
        rows = context.connection.execute(
            READ, {"tenant": context.unit.tenant_id, "since": since}
        ).all()

        tuning = self._tuning(context)
        thresholds = thresholds_from(context.settings)
        written = 0

        for (account, service), found in _by_pair(rows).items():
            # The last days that have data, not the last calendar days. A pair
            # that was quiet on a Sunday should still be judged on Monday
            # against the days it did bill, rather than against a window with a
            # hole in it.
            series = found[-NEEDED:]
            # The day being judged is never part of its own baseline. Including
            # it drags the baseline toward the value being tested, which makes
            # the detector least sensitive exactly when the move is largest.
            *history, latest = series
            verdict = judge(latest[1], [cost for _, cost in history], **tuning)
            if verdict is None or not verdict.is_anomaly:
                continue

            day = latest[0]
            context.connection.execute(
                WRITE,
                {
                    "id": uuid4(),
                    "tenant": context.unit.tenant_id,
                    "account": account,
                    "service": service,
                    "day": day,
                    "observed": verdict.observed,
                    "baseline": verdict.baseline,
                    "delta": verdict.delta,
                    "deviations": verdict.deviations,
                    # From the money, per ADR-0016, and through the same
                    # function the query findings use, so two screens do not
                    # mean different things by the word high.
                    "severity": severity_for(verdict.delta, thresholds),
                    "why": verdict.reason,
                    # The charge was true on its own day. `collected_at` is when
                    # the detector looked, per constraint 10.
                    "as_of": datetime(day.year, day.month, day.day, tzinfo=UTC),
                    "now": at,
                },
            )
            written += 1

        return CollectorOutcome(items_written=written)

    def _tuning(self, context: CollectorContext) -> dict[str, Decimal]:
        """Sensitivity and floor, from settings.

        Both reach the detector as arguments rather than living in it as
        constants, so meeting a real estate is a change of a number rather than
        a release.
        """
        return {
            "sensitivity": Decimal(str(context.settings.anomaly_sensitivity)),
            "floor": Decimal(str(context.settings.anomaly_floor_usd)),
        }
