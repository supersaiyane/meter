"""OpenAI's cost and usage for each organization a tenant connected. TASK-P13-004, FEAT-083.

The provider collector, `ai_providers.py`, named for OpenAI: what it reads is the adapter's, what
it writes and restates is the provider collector's, and this is where the schedule's name and the
source's word meet.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from finops_ingest.collectors.ai_providers import Accounts, AiProviderCollector, ReportsFor

COLLECTOR = "openai_usage"
#: The source, as `cost_focus_daily.ingest_source` and `ai_usage_daily.provider` name it.
SOURCE = "openai"


def _system_clock() -> datetime:
    return datetime.now(UTC)


def openai_collector(
    reports_for: ReportsFor,
    *,
    accounts: Accounts | None = None,
    clock: Callable[[], datetime] = _system_clock,
) -> AiProviderCollector:
    """The provider collector for OpenAI's organizations."""
    return AiProviderCollector(
        name=COLLECTOR, provider=SOURCE, reports_for=reports_for, accounts=accounts, clock=clock
    )
