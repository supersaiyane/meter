"""Every collector the worker runs, built from the fakes for the local stack. TASK-P12-001.

P12 spec section 5.1 and ADR-0022. The same collectors `finops_ingest.composition` binds for a
deployed environment, each built here from the fake that plants its case, so the local stack runs
the dispatcher and the worker end to end with no AWS account. This lives with the fakes and is
reached only through the fakes' own entry points: nothing in a production package imports it, and
the runtime image does not carry it.

Each fake is built with its own planted estate and the clock it is handed: the fakes never read the
wall clock themselves, the rule `tests/providers/test_fake.py` holds them to, so the entry point
that runs them supplies it. A collector judged per account is handed the candidates of the unit's
own account, as the demo seed hands them.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal
from typing import Any, Final

from finops_fakes import estate_shape as shape
from finops_fakes.ai import (
    FAKE_ANTHROPIC,
    FAKE_OPENAI,
    FakeGpuMetrics,
    FakeInvocationLogs,
    FakeProviderReports,
)
from finops_fakes.budgets import FakeBudgets
from finops_fakes.catalog import (
    FakeInstanceCatalog,
    FakePriceCatalog,
    FakeSavingsPlansRates,
    FakeSpotPrices,
)
from finops_fakes.cloudwatch_estate import FakeCloudWatchEstate
from finops_fakes.commitment import FakeCommitmentReport
from finops_fakes.containers import FakeContainerSource
from finops_fakes.cur import FakeCostExport
from finops_fakes.estate_metrics import EstateMetrics, ec2_candidates, volume_candidates
from finops_fakes.evidence import FakeQueryEvidence
from finops_fakes.health import FakeRoleHealth
from finops_fakes.invoices import FakeInvoices
from finops_fakes.ownership import FakeResourceCreators, FakeServiceCatalogue
from finops_fakes.platform_cost import FakePlatformCost
from finops_fakes.provider import FakeProvider
from finops_fakes.quotas import FakeQuotaSource
from finops_fakes.recommendations import FakeRecommendationSource
from finops_fakes.surface import FakeQuerySurface
from finops_fakes.terraform_state import FakeTerraformState
from finops_fakes.topology import FakeTopologySource
from finops_ingest.collectors.account_health import AccountHealthCollector
from finops_ingest.collectors.ai_usage import BedrockInvocationsCollector
from finops_ingest.collectors.anthropic_usage import anthropic_collector
from finops_ingest.collectors.budgets import BudgetCollector
from finops_ingest.collectors.commitment import CommitmentCollector
from finops_ingest.collectors.commitment_actions import CommitmentActionsCollector
from finops_ingest.collectors.container_usage import ContainerUsageCollector
from finops_ingest.collectors.cost_anomaly import CostAnomalyCollector
from finops_ingest.collectors.cost_focus import CostFocusCollector
from finops_ingest.collectors.digests import DigestCollector
from finops_ingest.collectors.gpu_utilization import GpuUtilizationCollector
from finops_ingest.collectors.iac_state import IacStateCollector
from finops_ingest.collectors.instance_catalog import InstanceCatalogCollector
from finops_ingest.collectors.inventory import InventoryCollector
from finops_ingest.collectors.invoices import InvoiceCollector
from finops_ingest.collectors.openai_usage import openai_collector
from finops_ingest.collectors.org_tree import OrgTreeCollector
from finops_ingest.collectors.ownership import OwnershipCollector
from finops_ingest.collectors.platform_cost import PlatformCostCollector
from finops_ingest.collectors.price_catalog import PriceCatalogCollector
from finops_ingest.collectors.query_audit import (
    QueryAuditCollector,
    default_ingest_rate,
    rates_from,
)
from finops_ingest.collectors.quotas import QuotaCollector
from finops_ingest.collectors.realized_savings import RealizedSavingsCollector
from finops_ingest.collectors.recommendations import RecommendationCollector
from finops_ingest.collectors.savings_ledger import SavingsLedgerCollector
from finops_ingest.collectors.savings_plan_rates import SavingsPlanRatesCollector
from finops_ingest.collectors.score import ScoreCollector
from finops_ingest.collectors.spot_prices import SpotPricesCollector
from finops_ingest.collectors.waste_cloudwatch import WasteCloudWatchCollector
from finops_ingest.collectors.waste_compute import Candidate, WasteComputeCollector
from finops_ingest.collectors.waste_parking import Parkable, WasteParkingCollector
from finops_ingest.collectors.waste_volumes import VolumeCandidate
from finops_ingest.composition import Binding, compose, scope_of
from finops_ingest.registry import CollectorContext, CollectorRegistry, CollectorRunner
from finops_query.parser import GrafanaQueryParser

#: A month of hours, as the seed prices an instance's hour from its month.
HOURS: Final = Decimal("730")

Clock = Callable[[], datetime]


def _account_of(context: CollectorContext) -> str | None:
    account = context.unit.account
    return None if account is None else account.account_id


def _compute_candidates(clock: Clock) -> Callable[[CollectorContext], list[Candidate]]:
    def candidates(context: CollectorContext) -> list[Candidate]:
        here = _account_of(context)
        return [
            Candidate(
                resource_id=one.resource_id,
                account_id=one.account_id,
                region_id=one.region_id,
                observation_days=one.observation_days,
                monthly_cost=one.monthly_cost,
                credit_balance=one.credit_balance,
                instance_type=one.instance_type,
            )
            for one in ec2_candidates(at=clock())
            if one.account_id == here
        ]

    return candidates


def _volume_candidates(clock: Clock) -> Callable[[CollectorContext], list[VolumeCandidate]]:
    def candidates(context: CollectorContext) -> list[VolumeCandidate]:
        here = _account_of(context)
        return [
            VolumeCandidate(**asdict(one))
            for one in volume_candidates(at=clock())
            if one.account_id == here
        ]

    return candidates


def _parkable(clock: Clock) -> Callable[[CollectorContext], list[Parkable]]:
    def candidates(context: CollectorContext) -> list[Parkable]:
        here = _account_of(context)
        return [
            Parkable(
                account_id=one.account_id,
                region_id=one.region_id,
                resource_id=one.resource_id,
                hourly_rate=(one.monthly_cost / HOURS).quantize(Decimal("0.0001")),
                storage_monthly_cost=None,
            )
            for one in ec2_candidates(at=clock())
            if one.account_id == here
        ]

    return candidates


def _query_audit(context: CollectorContext) -> CollectorRunner:
    return QueryAuditCollector(
        FakeQuerySurface(),
        rates_from(context.settings),
        default_ingest_rate(context.settings),
        evidence=FakeQueryEvidence(GrafanaQueryParser()),
    )


def builders(clock: Clock) -> dict[str, Callable[[CollectorContext], Any]]:
    """Each collector, built from its fake for one unit, on the clock it is handed."""
    return {
        "account_health": lambda _c: AccountHealthCollector(
            FakeRoleHealth(at=clock()), clock=clock
        ),
        # The local stack's connected Anthropic organization, like the OpenAI one below.
        "anthropic_usage": lambda _c: anthropic_collector(
            lambda _context, _account: FakeProviderReports(at=clock()),
            accounts=lambda _connection, _tenant: (FAKE_ANTHROPIC,),
            clock=clock,
        ),
        "bedrock_invocations": lambda _c: BedrockInvocationsCollector(
            FakeInvocationLogs(at=clock()), clock=clock
        ),
        "budgets": lambda _c: BudgetCollector(FakeBudgets(), clock=clock),
        "commitment": lambda _c: CommitmentCollector(FakeCommitmentReport(at=clock()), clock=clock),
        "commitment_actions": lambda _c: CommitmentActionsCollector(clock=clock),
        "container_usage": lambda _c: ContainerUsageCollector(
            FakeContainerSource(at=clock()), clock=clock
        ),
        "cost_anomaly": lambda _c: CostAnomalyCollector(clock=clock),
        "cost_focus": lambda _c: CostFocusCollector(FakeCostExport(), clock=clock),
        "finops_score": lambda _c: ScoreCollector(clock=clock),
        "gpu_utilization": lambda _c: GpuUtilizationCollector(
            FakeGpuMetrics(at=clock()), clock=clock
        ),
        "iac_state": lambda _c: IacStateCollector(FakeTerraformState(), clock=clock),
        "instance_catalog": lambda _c: InstanceCatalogCollector(
            FakeInstanceCatalog(), hub_region=shape.REGIONS[0], clock=clock
        ),
        "inventory": lambda _c: InventoryCollector(FakeTopologySource(), clock=clock),
        "invoices": lambda _c: InvoiceCollector(FakeInvoices(), clock=clock),
        # The local stack's one connected organization, so it runs without a seeded row.
        "openai_usage": lambda _c: openai_collector(
            lambda _context, _account: FakeProviderReports(at=clock()),
            accounts=lambda _connection, _tenant: (FAKE_OPENAI,),
            clock=clock,
        ),
        "org_tree": lambda _c: OrgTreeCollector(FakeProvider(at=clock()), clock=clock),
        "ownership": lambda _c: OwnershipCollector(
            clock=clock, catalogue=FakeServiceCatalogue(), creators=FakeResourceCreators()
        ),
        "platform_cost": lambda _c: PlatformCostCollector(FakePlatformCost(), clock=clock),
        "price_catalog": lambda _c: PriceCatalogCollector(FakePriceCatalog(), clock=clock),
        "query_audit": _query_audit,
        "quotas": lambda _c: QuotaCollector(FakeQuotaSource(at=clock()), clock=clock),
        "realized_savings": lambda _c: RealizedSavingsCollector(clock=clock),
        "recommendations": lambda _c: RecommendationCollector(
            FakeRecommendationSource(at=clock()), clock=clock
        ),
        "savings_ledger": lambda _c: SavingsLedgerCollector(clock=clock),
        "savings_plan_rates": lambda _c: SavingsPlanRatesCollector(
            FakeSavingsPlansRates(), clock=clock
        ),
        "spot_prices": lambda _c: SpotPricesCollector(FakeSpotPrices(), clock=clock),
        "team_digests": lambda _c: DigestCollector(clock=clock),
        "waste_cloudwatch": lambda _c: WasteCloudWatchCollector(
            FakeCloudWatchEstate(at=clock()), clock=clock
        ),
        "waste_compute": lambda _c: WasteComputeCollector(
            EstateMetrics(at=clock()),
            _compute_candidates(clock),
            clock=clock,
            volumes=_volume_candidates(clock),
        ),
        "waste_parking": lambda _c: WasteParkingCollector(
            EstateMetrics(at=clock()), _parkable(clock), clock=clock
        ),
    }


def fake_bindings(clock: Clock) -> tuple[Binding, ...]:
    """Every collector the worker runs, each built from its fake."""
    built = builders(clock)
    return tuple(Binding(name, scope_of(name), built[name]) for name in sorted(built))


def fake_registry(clock: Clock) -> CollectorRegistry:
    """The registry the local stack's dispatcher and worker run, on the clock it is handed."""
    return compose(fake_bindings(clock))
