"""A policy gate over dashboard JSON, for any pipeline. FEAT-014, TASK-P2-018.

The reporting side of P2 tells an organization what its existing dashboards
cost. This is the other half: it stops the next expensive one being merged, and
it is the only part of P2 that acts before the money is spent rather than after.

**It fails, it does not warn.** ISS-096 is the argument: this gate's reach
already depends on how many dashboards a team keeps as code, and a gate that
warns is ignored regardless of reach. A rule worth having is worth blocking on,
and a rule not worth blocking on should be deleted rather than downgraded.

**Every violation carries what the panel would have cost.** A message saying a
panel breaks a rule is an argument about policy. A message saying it would have
cost 1,400 USD a month is an argument about money, and only one of those gets
fixed on a Friday afternoon.

It takes dashboard JSON and nothing else: no database, no credentials, no
network. That is what lets it run in a pipeline that has none of those.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from finops_query.classify import LOGS_INSIGHTS
from finops_query.cost_model import ALERT, PANEL, IngestRate, Rates, price, runs_per_day
from finops_query.parser import GrafanaQueryParser

SECONDS_PER_HOUR = 3600


@dataclass(frozen=True)
class Rule:
    """One thing a dashboard may not do, and the numbers that define it.

    From settings rather than written here, so a tenant can tighten it. The
    defaults are the same thresholds the cost model warns on, which is
    deliberate: a gate that blocks at a different number from the one the
    reports warn at teaches people the reports are wrong.
    """

    max_refresh_seconds: int
    max_window_hours: float

    def broken_by(self, engine: str, refresh: int, window_seconds: int | None) -> bool:
        if engine != LOGS_INSIGHTS or not refresh or window_seconds is None:
            return False
        window_hours = window_seconds / SECONDS_PER_HOUR
        return refresh <= self.max_refresh_seconds and window_hours > self.max_window_hours


#: The rule TASK-P2-018 names: a sub minute refresh over a window wider than a
#: day. It is the shape that turns a dashboard into a standing charge.
DEFAULT_RULE = Rule(max_refresh_seconds=60, max_window_hours=24.0)


def rule_from(settings: Any) -> Rule:
    return Rule(
        max_refresh_seconds=int(settings.query_refresh_warn_seconds),
        max_window_hours=float(settings.query_timerange_warn_hours),
    )


@dataclass(frozen=True)
class Violation:
    """One panel that may not be merged, and what it would have cost."""

    dashboard: str
    panel: str
    engine: str
    refresh_seconds: int
    window_seconds: int
    monthly_cost: float

    def __str__(self) -> str:
        return (
            f"{self.dashboard} / {self.panel}: refreshes every "
            f"{self.refresh_seconds}s over a "
            f"{self.window_seconds / SECONDS_PER_HOUR:.0f} hour window. "
            f"Modelled at ${self.monthly_cost:,.2f} a month."
        )


def check(
    dashboard: dict[str, Any],
    *,
    rates: Rates,
    ingest_rate: IngestRate,
    rule: Rule = DEFAULT_RULE,
    parser: GrafanaQueryParser | None = None,
    region: str = "eu-west-2",  # allow-hardcoded: a price band default for a pipeline
) -> tuple[Violation, ...]:
    """Every panel in one dashboard that breaks the rule.

    An empty tuple is a pass. A dashboard this cannot read is a pass too: the
    gate refuses what it can prove is wrong, and blocking on a shape it does not
    understand would make every unrelated Grafana upgrade a pipeline failure.
    """
    reader = parser or GrafanaQueryParser()
    title = str(dashboard.get("title") or "untitled")
    refresh = reader.refresh_seconds(dashboard.get("refresh"))
    window = reader.relative_range_seconds((dashboard.get("time") or {}).get("from"))

    found: list[Violation] = []
    for panel in reader.iter_panels(dashboard.get("panels")):
        for target in panel.get("targets") or ():
            classified = reader.classify(target, panel.get("datasource"))
            if not rule.broken_by(classified.engine, refresh, window):
                continue
            origin = ALERT if panel.get("type") == "alertlist" else PANEL
            cost = price(
                classification=classified,
                origin=origin,
                refresh=refresh,
                window_seconds=window,
                per_day=runs_per_day(refresh, origin, rates),
                rates=rates,
                ingest_rate=ingest_rate,
                region=region,
            )
            found.append(
                Violation(
                    dashboard=title,
                    panel=str(panel.get("title") or "untitled panel"),
                    engine=classified.engine,
                    refresh_seconds=refresh,
                    window_seconds=window or 0,
                    monthly_cost=cost.cost_month,
                )
            )
            break
    return tuple(found)
