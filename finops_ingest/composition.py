"""Every collector the worker runs, built for each unit of work. FEAT-079, TASK-P12-001.

P12 spec section 5.1, OPEN-28 and ADR-0022. A collector takes its adapters when it is constructed,
and an AWS adapter is bound to one account's session, so each collector is registered with a
builder that constructs it for the unit in hand, from that unit's context. Before this module
nothing outside the tests assembled a registry, ISS-182.

**Production bindings only.** This module never reaches a fake: the fakes stay out of the runtime
image, ADR-0022, and the local stack composes the same collectors from them in
`finops_fakes.composition`, through entry points of its own. A collector that reads only what Meter
already holds is bound here for real, and one that reads AWS is built from its adapters,
`finops_ingest.aws_bindings`, TASK-P12-002. One that cannot be built for AWS yet fails each run
typed, as Misconfigured and naming why, so it shows on the freshness screen rather than nowhere,
and never runs on something invented.

A test holds the bindings equal to the collectors the schedule says run in the worker.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

from finops_core.errors import Misconfigured
from finops_ingest.ai_bindings import AI_PROVIDER_BUILDERS
from finops_ingest.aws_bindings import AWS_BUILDERS, UNBUILT
from finops_ingest.collectors.commitment_actions import CommitmentActionsCollector
from finops_ingest.collectors.cost_anomaly import CostAnomalyCollector
from finops_ingest.collectors.digests import DigestCollector
from finops_ingest.collectors.purchase_plan import PurchasePlanCollector
from finops_ingest.collectors.realized_savings import RealizedSavingsCollector
from finops_ingest.collectors.retention import RETENTION_COLLECTORS, register_retention
from finops_ingest.collectors.savings_ledger import SavingsLedgerCollector
from finops_ingest.collectors.score import ScoreCollector
from finops_ingest.registry import (
    DEFAULT_SCHEDULE,
    Collector,
    CollectorContext,
    CollectorOutcome,
    CollectorRegistry,
    CollectorRunner,
    CollectorScope,
)

#: Builds the collector for one unit, from that unit's context.
Build = Callable[[CollectorContext], CollectorRunner]

#: The collectors whose unit is one account in one Region, run on that account's session. Every
#: other is organization wide, run once, and reaches the accounts it needs itself.
PER_ACCOUNT: Final = frozenset(
    {
        "account_health",
        "bedrock_invocations",
        "commitment_inventory",
        "container_usage",
        "gpu_utilization",
        "quotas",
        "waste_cloudwatch",
        "waste_compute",
        "waste_parking",
    }
)


@dataclass(frozen=True)
class Binding:
    """One collector: its name, what one unit of it covers, and how it is built for a unit."""

    name: str
    scope: CollectorScope
    build: Build


def _now() -> datetime:
    return datetime.now(UTC)


def scope_of(name: str) -> CollectorScope:
    return CollectorScope.ACCOUNT if name in PER_ACCOUNT else CollectorScope.ORGANIZATION


def worker_collectors() -> frozenset[str]:
    """The collectors the schedule says run in the worker, retention among them."""
    return frozenset(entry.collector for entry in DEFAULT_SCHEDULE if entry.runs_in == "worker")


def per_unit(build: Build) -> CollectorRunner:
    """A runner that builds its collector for each unit, then runs it on that unit."""

    def run(context: CollectorContext) -> CollectorOutcome:
        return build(context)(context)

    return run


def compose(bindings: Iterable[Binding]) -> CollectorRegistry:
    """A registry of the bindings and the retention jobs, which need nothing to be built."""
    registry = CollectorRegistry()
    for binding in bindings:
        registry.register(Collector(binding.name, binding.scope, per_unit(binding.build)))
    register_retention(registry)
    return registry


def unbuilt(name: str, why: str) -> Build:
    """A collector that cannot be built for AWS yet: every run fails typed, naming why."""

    def build(context: CollectorContext) -> CollectorRunner:
        raise Misconfigured(
            scope_key=context.unit.scope_key,
            collector=name,
            detail=f"{name} cannot be built for AWS in this release: {why}",
        )

    return build


def _built(make: Callable[[], CollectorRunner]) -> Build:
    """A collector that reads only what Meter holds, the same for every unit."""
    return lambda _context: make()


#: The collectors that read only Meter's own tables, bound for real now.
_FROM_METER: Final[dict[str, Callable[[], CollectorRunner]]] = {
    "commitment_actions": CommitmentActionsCollector,
    "cost_anomaly": CostAnomalyCollector,
    "finops_score": ScoreCollector,
    "purchase_plan": PurchasePlanCollector,
    "realized_savings": RealizedSavingsCollector,
    "savings_ledger": SavingsLedgerCollector,
    "team_digests": lambda: DigestCollector(clock=_now),
}


def production_bindings() -> tuple[Binding, ...]:
    """Every collector the worker runs, bound for a deployed environment."""
    bindings = [Binding(name, scope_of(name), _built(make)) for name, make in _FROM_METER.items()]
    bindings.extend(Binding(name, scope_of(name), build) for name, build in AWS_BUILDERS.items())
    bindings.extend(
        Binding(name, scope_of(name), build) for name, build in AI_PROVIDER_BUILDERS.items()
    )
    bindings.extend(
        Binding(name, scope_of(name), unbuilt(name, why)) for name, why in UNBUILT.items()
    )
    return tuple(sorted(bindings, key=lambda one: one.name))


def production_registry() -> CollectorRegistry:
    """The registry a deployed dispatcher and worker run."""
    return compose(production_bindings())


#: The retention jobs `compose` adds, so a binding never repeats one.
RETENTION: Final = frozenset(collector.name for collector in RETENTION_COLLECTORS)
