"""Each collector built from its AWS adapters for one unit of work. FEAT-079, TASK-P12-002.

P12 spec section 5.1. `finops_ingest.composition` registers these for a deployed environment. A
builder runs once per unit, before the collector does, and constructs the collector from that
unit's context: the tenant, the run, the settings the worker was started with and, for an
account scoped unit, the session the worker assumed in that account. Clients are made on first
use, `finops_providers.aws.reach`, so building touches no network.

**What a builder cannot build fails typed.** A setting a read depends on that is not set fails
the unit as Misconfigured naming the setting, and a port with no AWS adapter fails it as
Misconfigured naming the issue that says why, `UNBUILT`. Either way the freshness screen shows
the reason, and nothing runs on something invented.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import partial
from typing import Any, Final

from finops_core.domain.account import AccountKey
from finops_core.domain.commitments import EC2, ELASTICACHE, MEMORYDB, OPENSEARCH, RDS, REDSHIFT
from finops_core.errors import Misconfigured, SchemaDrift
from finops_ingest.accounts import active_accounts
from finops_ingest.collectors.account_health import AccountHealthCollector
from finops_ingest.collectors.ai_usage import BedrockInvocationsCollector
from finops_ingest.collectors.budgets import BudgetCollector
from finops_ingest.collectors.commitment import CommitmentCollector
from finops_ingest.collectors.commitment_inventory import CommitmentInventoryCollector
from finops_ingest.collectors.container_usage import ContainerUsageCollector
from finops_ingest.collectors.cost_focus import CostFocusCollector
from finops_ingest.collectors.gpu_utilization import GpuUtilizationCollector
from finops_ingest.collectors.iac_state import IacStateCollector
from finops_ingest.collectors.instance_catalog import InstanceCatalogCollector
from finops_ingest.collectors.inventory import InventoryCollector
from finops_ingest.collectors.invoices import InvoiceCollector
from finops_ingest.collectors.org_tree import OrgTreeCollector
from finops_ingest.collectors.ownership import OwnershipCollector
from finops_ingest.collectors.platform_cost import PlatformCostCollector
from finops_ingest.collectors.price_catalog import PriceCatalogCollector
from finops_ingest.collectors.purchase_recommendation import PurchaseRecommendationCollector
from finops_ingest.collectors.quotas import QuotaCollector
from finops_ingest.collectors.recommendations import RecommendationCollector
from finops_ingest.collectors.savings_plan_rates import SavingsPlanRatesCollector
from finops_ingest.collectors.spot_prices import SpotPricesCollector
from finops_ingest.collectors.topology import CompositeTopologySource
from finops_ingest.registry import CollectorContext, CollectorRunner
from finops_providers.aws.accounts import AwsAccountDiscovery
from finops_providers.aws.bedrock_invocations import BedrockInvocationLogs
from finops_providers.aws.budgets import AwsBudgets
from finops_providers.aws.cloudtrail_creators import AwsResourceCreators
from finops_providers.aws.commitment import COST_EXPLORER_REGION, CostExplorerCommitmentReport
from finops_providers.aws.commitment_inventory import AwsCommitmentHoldings
from finops_providers.aws.commitment_recommendations import CostExplorerRecommendations
from finops_providers.aws.config_inventory import ConfigAggregatorInventory
from finops_providers.aws.container_insights import ContainerInsightsSource
from finops_providers.aws.credentials import AwsCredentialBroker
from finops_providers.aws.cur import AthenaCostExport
from finops_providers.aws.gpu_metrics import CloudWatchGpuMetrics
from finops_providers.aws.health import AccountHealthCheck
from finops_providers.aws.instance_types import AwsInstanceCatalog
from finops_providers.aws.invoices import AwsInvoices
from finops_providers.aws.platform_cost import AwsPlatformCostSource
from finops_providers.aws.price_list import AwsPriceCatalog
from finops_providers.aws.quotas import AwsQuotas
from finops_providers.aws.reach import (
    GLOBAL_REGION,
    PerAccountCatalogue,
    hub_client,
    member_clients,
    payer_client,
    payer_of,
    relay,
    session_clients,
)
from finops_providers.aws.recommendations import CostRecommendationSource
from finops_providers.aws.relay_client import RelayClient
from finops_providers.aws.savings_plans import AwsSavingsPlansRates
from finops_providers.aws.spot import AwsSpotPrices
from finops_providers.aws.terraform_state import S3TerraformState
from finops_providers.aws.topology import AwsEdgeSupplement
from finops_query.parser import GrafanaQueryParser
from finops_query.severity import severity_for, thresholds_from

Build = Callable[[CollectorContext], CollectorRunner]

#: The collectors that cannot be built for AWS in this release, and why.
UNBUILT: Final[dict[str, str]] = {
    "query_audit": "no setting names the Amazon Managed Grafana workspaces to search, ISS-272",
    "waste_cloudwatch": "CloudWatchEstate has a fake and no AWS adapter, ISS-240",
    "waste_compute": "CloudWatchWasteMetrics does not satisfy MetricSource, ISS-240",
    "waste_parking": "CloudWatchWasteMetrics does not satisfy MetricSource, ISS-240",
}


def _not_set(context: CollectorContext, collector: str, setting: str, reads: str) -> Misconfigured:
    return Misconfigured(
        scope_key=context.unit.scope_key,
        collector=collector,
        detail=f"{collector} reads {reads}, and {setting} is not set",
    )


def _relayed(
    context: CollectorContext, collector: str, *, service: str, region: str, account: str | None
) -> RelayClient:
    settings = context.settings
    if not settings.relay_function_name:
        raise _not_set(context, collector, "METER_RELAY_FUNCTION_NAME", "through the relay")
    if not settings.s3_bucket:
        raise _not_set(context, collector, "METER_S3_BUCKET", "the relay's answers from S3")
    return relay(settings, service=service, region=region, account_id=account)


def _payer(context: CollectorContext, collector: str) -> str:
    payer = payer_of(context.settings)
    if payer is None:
        raise Misconfigured(
            scope_key=context.unit.scope_key,
            collector=collector,
            detail=f"{collector} reads at the payer, the account in METER_ORG_READER_ROLE_ARN, "
            "and that setting is not an IAM role ARN",
        )
    return payer


def _assumed(context: CollectorContext, collector: str) -> Any:
    """The boto3 session the worker assumed for this account scoped unit."""
    if context.session is None:
        raise SchemaDrift(
            scope_key=context.unit.scope_key,
            collector=collector,
            detail="an account scoped unit arrived with no assumed session",
        )
    return context.session.session


def enrolled(context: CollectorContext) -> tuple[tuple[AccountKey, str | None], ...]:
    """The tenant's active accounts, each in every configured Region and globally."""
    regions: tuple[str | None, ...] = (*context.settings.region_list, None)
    return tuple(
        (account, region)
        for account in active_accounts(context.connection, context.unit.tenant_id)
        for region in regions
    )


def _account_health(context: CollectorContext) -> CollectorRunner:
    return AccountHealthCollector(AccountHealthCheck(AwsCredentialBroker(context.settings)))


def _bedrock_invocations(context: CollectorContext) -> CollectorRunner:
    session = _assumed(context, "bedrock_invocations")
    logs = BedrockInvocationLogs(context.settings, context.unit.tenant_id, session=session)
    return BedrockInvocationsCollector(logs)


def _budgets(context: CollectorContext) -> CollectorRunner:
    payer = _payer(context, "budgets")
    client = _relayed(context, "budgets", service="budgets", region=GLOBAL_REGION, account=payer)
    return BudgetCollector(AwsBudgets(client=client, account_id=payer))


def _commitment(context: CollectorContext) -> CollectorRunner:
    # As the payer: Cost Explorer reports the organization's commitments only there, ISS-294.
    settings = context.settings
    return CommitmentCollector(
        CostExplorerCommitmentReport(
            settings,
            context.unit.tenant_id,
            client_factory=lambda: payer_client(settings, "ce", COST_EXPLORER_REGION),
        )
    )


def _purchase_recommendation(context: CollectorContext) -> CollectorRunner:
    # As the payer, for the reason `_commitment` is: AWS recommends for the organization there.
    settings = context.settings
    return PurchaseRecommendationCollector(
        CostExplorerRecommendations(
            context.unit.tenant_id,
            client_factory=lambda: payer_client(settings, "ce", COST_EXPLORER_REGION),
        ),
        services=settings.recommendation_services,
    )


#: Each reserved service read through the relay, ADR-0037, and the name the relay knows it by.
RELAYED_RESERVATIONS: Final = {
    RDS: "rds",
    ELASTICACHE: "elasticache",
    OPENSEARCH: "opensearch",
    REDSHIFT: "redshift",
    MEMORYDB: "memorydb",
}


def _relayed_reservations(
    relayed: Callable[[str, str, str], Any], service: str, account: str, region: str
) -> Any:
    return relayed(service, region, account)


def _commitment_inventory(context: CollectorContext) -> CollectorRunner:
    # Each account's own commitments, as its collector role: Savings Plans and RDS reservations
    # through the relay, ADR-0037, EC2 reservations through the EC2 endpoint, FEAT-086.
    settings = context.settings
    session = _assumed(context, "commitment_inventory")
    ec2 = session_clients(settings, session)

    def relayed(service: str, region: str, account: str) -> Any:
        return _relayed(
            context, "commitment_inventory", service=service, region=region, account=account
        )

    holdings = AwsCommitmentHoldings(
        context.unit.tenant_id,
        savings_plans_for=lambda account: relayed("savingsplans", GLOBAL_REGION, account),
        reservations_for={
            EC2: lambda _account, region: ec2("ec2", region),
            **{
                program: partial(_relayed_reservations, relayed, service)
                for program, service in RELAYED_RESERVATIONS.items()
            },
        },
    )
    return CommitmentInventoryCollector(holdings, first_region=settings.region_list[0])


def _container_usage(context: CollectorContext) -> CollectorRunner:
    session = _assumed(context, "container_usage")
    return ContainerUsageCollector(ContainerInsightsSource(context.settings, session=session))


def _cost_focus(context: CollectorContext) -> CollectorRunner:
    export = AthenaCostExport(context.settings, context.unit.tenant_id, context.run_id)
    return CostFocusCollector(export)


def _gpu_utilization(context: CollectorContext) -> CollectorRunner:
    session = _assumed(context, "gpu_utilization")
    metrics = CloudWatchGpuMetrics(context.settings, context.unit.tenant_id, session=session)
    return GpuUtilizationCollector(metrics)


def _iac_state(context: CollectorContext) -> CollectorRunner:
    settings = context.settings
    state = S3TerraformState(client=hub_client(settings, "s3"), locations=settings.iac_locations)
    return IacStateCollector(state)


def _instance_catalog(context: CollectorContext) -> CollectorRunner:
    settings = context.settings
    ec2 = AwsInstanceCatalog(client_for=lambda region: hub_client(settings, "ec2", region))
    return InstanceCatalogCollector(ec2, hub_region=settings.region_list[0])


def _inventory(context: CollectorContext) -> CollectorRunner:
    settings = context.settings
    if not settings.config_aggregator:
        raise _not_set(context, "inventory", "METER_CONFIG_AGGREGATOR", "the AWS Config aggregator")
    tenant = context.unit.tenant_id
    slices = enrolled(context)
    source = CompositeTopologySource(
        ConfigAggregatorInventory(
            settings,
            client=hub_client(settings, "config"),
            aggregator_name=settings.config_aggregator,
            tenant_id=tenant,
            enrolled=slices,
        ),
        AwsEdgeSupplement(
            settings, client_factory=member_clients(settings), tenant_id=tenant, enrolled=slices
        ),
    )
    return InventoryCollector(source)


def _invoices(context: CollectorContext) -> CollectorRunner:
    payer = _payer(context, "invoices")
    client = _relayed(context, "invoices", service="invoicing", region=GLOBAL_REGION, account=payer)
    return InvoiceCollector(AwsInvoices(client=client, account_id=payer))


def _org_tree(context: CollectorContext) -> CollectorRunner:
    # As the payer: Organizations lists the accounts only to the management account, ISS-296.
    settings = context.settings
    return OrgTreeCollector(
        AwsAccountDiscovery(
            settings, client_factory=lambda: payer_client(settings, "organizations", GLOBAL_REGION)
        )
    )


def _ownership(context: CollectorContext) -> CollectorRunner:
    settings = context.settings
    member = member_clients(settings)
    return OwnershipCollector(
        catalogue=PerAccountCatalogue(member=member, owner_key=settings.catalogue_owner_key),
        creators=AwsResourceCreators(
            client_factory=member, principal_of=GrafanaQueryParser().principal_from
        ),
    )


def _platform_cost(context: CollectorContext) -> CollectorRunner:
    return PlatformCostCollector(AwsPlatformCostSource(context.settings))


def _price_catalog(context: CollectorContext) -> CollectorRunner:
    pricing = hub_client(context.settings, "pricing", GLOBAL_REGION)
    return PriceCatalogCollector(AwsPriceCatalog(client=pricing))


def _quotas(context: CollectorContext) -> CollectorRunner:
    clients = session_clients(context.settings, _assumed(context, "quotas"))
    return QuotaCollector(AwsQuotas(client_factory=clients))


def _recommendations(context: CollectorContext) -> CollectorRunner:
    thresholds = thresholds_from(context.settings)
    source = CostRecommendationSource(
        context.settings,
        context.unit.tenant_id,
        severity_of=lambda amount: severity_for(amount, thresholds),
    )
    return RecommendationCollector(source)


def _savings_plan_rates(context: CollectorContext) -> CollectorRunner:
    client = _relayed(
        context, "savings_plan_rates", service="savingsplans", region=GLOBAL_REGION, account=None
    )
    return SavingsPlanRatesCollector(AwsSavingsPlansRates(client=client))


def _spot_prices(context: CollectorContext) -> CollectorRunner:
    # Checked once here, so a missing setting fails the unit before any Region is asked.
    _relayed(context, "spot_prices", service="ec2", region=GLOBAL_REGION, account=None)
    settings = context.settings
    return SpotPricesCollector(
        AwsSpotPrices(
            client_for=lambda region: relay(settings, service="ec2", region=region, account_id=None)
        )
    )


#: Each collector the worker runs that has an AWS composition, built from its adapters.
AWS_BUILDERS: Final[dict[str, Build]] = {
    "account_health": _account_health,
    "bedrock_invocations": _bedrock_invocations,
    "budgets": _budgets,
    "commitment": _commitment,
    "commitment_inventory": _commitment_inventory,
    "container_usage": _container_usage,
    "cost_focus": _cost_focus,
    "gpu_utilization": _gpu_utilization,
    "iac_state": _iac_state,
    "instance_catalog": _instance_catalog,
    "inventory": _inventory,
    "invoices": _invoices,
    "org_tree": _org_tree,
    "ownership": _ownership,
    "platform_cost": _platform_cost,
    "price_catalog": _price_catalog,
    "purchase_recommendation": _purchase_recommendation,
    "quotas": _quotas,
    "recommendations": _recommendations,
    "savings_plan_rates": _savings_plan_rates,
    "spot_prices": _spot_prices,
}
