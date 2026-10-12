"""Anthropic's cost and usage for each organization a tenant connected. TASK-P13-005, FEAT-083.

The provider collector, `ai_providers.py`, named for Anthropic: what it reads is the adapter's,
what it writes and restates is the provider collector's, and this is where the schedule's name and
the source's word meet.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from finops_ingest.collectors.ai_providers import Accounts, AiProviderCollector, ReportsFor

COLLECTOR = "anthropic_usage"
#: The source, as `cost_focus_daily.ingest_source` and `ai_usage_daily.provider` name it.
SOURCE = "anthropic"


def _system_clock() -> datetime:
    return datetime.now(UTC)


def anthropic_collector(
    reports_for: ReportsFor,
    *,
    accounts: Accounts | None = None,
    clock: Callable[[], datetime] = _system_clock,
) -> AiProviderCollector:
    """The provider collector for Anthropic's organizations."""
    return AiProviderCollector(
        name=COLLECTOR, provider=SOURCE, reports_for=reports_for, accounts=accounts, clock=clock
    )
