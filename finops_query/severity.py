"""Severity from money, per ADR-0016, and the cause a finding is grouped by.

Two decisions live here and the second one matters more than the first.

**Severity is derived from monthly impact, never entered.** A person cannot
raise the severity of a finding by believing in it more strongly. The thresholds
are configurable per tenant, because 100 USD a month is material to one
organization and rounding error to another.

**Findings are grouped by cause before they are ranked.** Four hundred findings
at 15 USD each are `LOW` individually and 6,000 USD together, and the whole
point of a dollar threshold is defeated if a systemic problem can hide as four
hundred trivial rows. This is the failure mode ADR-0016 names, and it is the
reason `cause` exists at all: prose cannot be grouped on, so the model emits a
code beside the sentence.

The shape based `risk_level` in `cost_model` is not severity and is not replaced
by this. It ranks within a band, where its argument still holds: a fast refresh
over a wide window is a risk whatever today's modelled figure says, because that
figure rests on an ingestion assumption that may be an order of magnitude out.
Severity is the money. Confidence is the provenance flag. Shape is the tiebreak.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol


class SettingsLike(Protocol):
    """Only the three fields this reads.

    `finops_query` does not import `finops_core.config`, and a structural type
    keeps it that way while still type checking the read.
    """

    severity_critical_usd: Decimal
    severity_high_usd: Decimal
    severity_medium_usd: Decimal


CRITICAL = "CRITICAL"
HIGH = "HIGH"
MEDIUM = "MEDIUM"
LOW = "LOW"

#: Worst first. Used to order bands and to pick a group's severity.
ORDER: tuple[str, ...] = (CRITICAL, HIGH, MEDIUM, LOW)

#: A closed vocabulary. Prose cannot be grouped on, and a free text key would
#: split one systemic problem across every phrasing the model ever emitted.
ALERT_ALWAYS_ON = "ALERT_ALWAYS_ON"
VERY_FAST_REFRESH = "VERY_FAST_REFRESH"
FAST_REFRESH = "FAST_REFRESH"
VERY_WIDE_WINDOW = "VERY_WIDE_WINDOW"
WIDE_WINDOW = "WIDE_WINDOW"
METRIC_FANOUT = "METRIC_FANOUT"
NO_REFRESH = "NO_REFRESH"
ENGINE_SCAN = "ENGINE_SCAN"

#: Which cause a finding is filed under when several apply. Ordered by what a
#: reader would change first, not by cost: an alert running 24x7 is a different
#: conversation from a dashboard nobody has open, even at the same monthly
#: figure.
CAUSE_PRIORITY: tuple[str, ...] = (
    ALERT_ALWAYS_ON,
    VERY_FAST_REFRESH,
    VERY_WIDE_WINDOW,
    FAST_REFRESH,
    WIDE_WINDOW,
    METRIC_FANOUT,
    NO_REFRESH,
    ENGINE_SCAN,
)

CAUSE_LABEL: dict[str, str] = {
    ALERT_ALWAYS_ON: "Alert rules running 24x7",
    VERY_FAST_REFRESH: "Sub minute auto refresh",
    FAST_REFRESH: "Fast auto refresh",
    VERY_WIDE_WINDOW: "Very wide time window",
    WIDE_WINDOW: "Wide time window",
    METRIC_FANOUT: "Metric queries scanning many metrics",
    NO_REFRESH: "Manual loads only",
    ENGINE_SCAN: "Billed per volume scanned",
}


@dataclass(frozen=True)
class Thresholds:
    """The dollar bands, per tenant. ADR-0016 gives the defaults."""

    critical: Decimal
    high: Decimal
    medium: Decimal

    def __post_init__(self) -> None:
        if not self.critical >= self.high >= self.medium:
            # An unordered set of bands silently makes one of them unreachable,
            # and the finding that never reaches CRITICAL is the one that
            # mattered.
            raise ValueError(
                f"thresholds must descend: critical {self.critical} >= high "
                f"{self.high} >= medium {self.medium}"
            )


#: ADR-0016's own numbers, for a caller that has not been given settings. Not a
#: silent default in the settings object: the bands are configurable per tenant
#: and the configured ones win wherever they are available.
DEFAULT_THRESHOLDS = Thresholds(critical=Decimal("1000"), high=Decimal("100"), medium=Decimal("20"))


def thresholds_from(settings: SettingsLike) -> Thresholds:
    """The bands from settings.

    These are the existing `severity_*_usd` settings, not new query specific
    ones. ADR-0016 defines one dollar scale for every cost finding, and a second
    set of bands for query findings alone would let the same 500 USD read as
    HIGH on one screen and MEDIUM on another.
    """
    return Thresholds(
        critical=Decimal(str(settings.severity_critical_usd)),
        high=Decimal(str(settings.severity_high_usd)),
        medium=Decimal(str(settings.severity_medium_usd)),
    )


def severity_for(cost_month_usd: Decimal | float, thresholds: Thresholds) -> str:
    """The band a monthly figure falls in. Derived, never entered."""
    amount = Decimal(str(cost_month_usd))
    if amount >= thresholds.critical:
        return CRITICAL
    if amount >= thresholds.high:
        return HIGH
    if amount >= thresholds.medium:
        return MEDIUM
    return LOW


def primary_cause(causes: tuple[str, ...]) -> str:
    """The one a finding is filed under, when several apply.

    Falls back to the engine's own scan cost, which is true of every priced
    query and is therefore the honest answer when nothing sharper applies.
    """
    for candidate in CAUSE_PRIORITY:
        if candidate in causes:
            return candidate
    return ENGINE_SCAN
