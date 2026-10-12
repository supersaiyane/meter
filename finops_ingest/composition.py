"""Every collector the worker runs, built for each unit of work. FEAT-079, TASK-P12-001.

P12 spec section 5.1, OPEN-28 and ADR-0022. A collector takes its adapters when it is constructed,
and an AWS adapter is bound to one account's session, so each collector is registered with a
builder that constructs it for the unit in hand, from that unit's context. Before this module
nothing outside the tests assembled a registry, ISS-182.

**Production bindings only.** This module never reaches a fake: the fakes stay out of the runtime
image, ADR-0022, and the local stack composes the same collectors from them in
`finops_fakes.composition`, through entry points of its own. A collector that reads only what Meter
already holds is bound here for real. One that needs an AWS adapter fails each run typed, as
Misconfigured and naming what it lacks, until TASK-P12-002 gives it one, so it shows on the
freshness screen rather than nowhere, and never runs on something invented.

A test holds the bindings equal to the collectors the schedule says run in the worker.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

from finops_core.errors import Misconfigured
from finops_ingest.collectors.commitment_actions import CommitmentActionsCollector
from finops_ingest.collectors.cost_anomaly import CostAnomalyCollector
from finops_ingest.collectors.digests import DigestCollector
from finops_ingest.collectors.ownership import OwnershipCollector
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
        "container_usage",
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


def unbuilt(name: str, needs: str) -> Build:
    """A collector with no AWS adapter yet: every run fails typed, naming what it lacks."""

    def build(context: CollectorContext) -> CollectorRunner:
        raise Misconfigured(
            scope_key=context.unit.scope_key,
            collector=name,
            detail=f"{name} has no AWS adapter for {needs} in this release, TASK-P12-002",
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
    "realized_savings": RealizedSavingsCollector,
    "savings_ledger": SavingsLedgerCollector,
    "team_digests": lambda: DigestCollector(clock=_now),
}

#: The collectors that need an AWS adapter, and what it reads, until TASK-P12-002.
_NEEDS_AWS: Final[dict[str, str]] = {
    "account_health": "the collector role's health check",
    "budgets": "AWS Budgets",
    "commitment": "Savings Plans and Reserved Instance utilization",
    "container_usage": "EKS and Container Insights",
    "cost_focus": "the CUR 2.0 export",
    "iac_state": "Terraform state in S3",
    "instance_catalog": "EC2 instance types",
    "inventory": "AWS Config",
    "invoices": "the Invoicing API",
    "org_tree": "AWS Organizations",
    "platform_cost": "Cost Explorer for the hub",
    "price_catalog": "the Price List API",
    "query_audit": "Amazon Managed Grafana",
    "quotas": "Service Quotas",
    "recommendations": "Compute Optimizer, Cost Optimization Hub and Trusted Advisor",
    "savings_plan_rates": "the Savings Plans rates",
    "spot_prices": "the spot price history",
    "waste_cloudwatch": "CloudWatch alarms and log groups",
    "waste_compute": "CloudWatch metrics and the inventory's candidates",
    "waste_parking": "CloudWatch metrics and the inventory's candidates",
}


def production_bindings() -> tuple[Binding, ...]:
    """Every collector the worker runs, bound for a deployed environment."""
    bindings = [Binding(name, scope_of(name), _built(make)) for name, make in _FROM_METER.items()]
    # Tags alone until TASK-P12-002 gives it the catalogue and the creators.
    bindings.append(Binding("ownership", scope_of("ownership"), _built(OwnershipCollector)))
    bindings.extend(
        Binding(name, scope_of(name), unbuilt(name, needs)) for name, needs in _NEEDS_AWS.items()
    )
    return tuple(sorted(bindings, key=lambda one: one.name))


def production_registry() -> CollectorRegistry:
    """The registry a deployed dispatcher and worker run."""
    return compose(production_bindings())


#: The retention jobs `compose` adds, so a binding never repeats one.
RETENTION: Final = frozenset(collector.name for collector in RETENTION_COLLECTORS)
