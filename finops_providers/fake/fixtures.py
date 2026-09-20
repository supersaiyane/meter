"""A fixed organization, with fixed values, that never moves between runs.

Nothing here reads a clock or a random source. A fixture that does makes every
test downstream of it untrustworthy, and the bill arrives weeks later as a test
that fails one run in fifty and is then marked flaky rather than fixed.

The account identifiers are deliberately not twelve digit numbers. A twelve
digit literal in a repository is either a real account or a fixture that will
one day be mistaken for one, and `scripts/ci/check_hardcoded.py` refuses both.
The region is fictional for the same reason.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from types import MappingProxyType
from uuid import UUID

from finops_core.domain.account import AccountKey, AccountStatus, CloudAccount, Provider
from finops_core.domain.cost import CostRecord, source_fingerprint
from finops_core.domain.identity import Principal
from finops_core.domain.metrics import MetricPoint
from finops_core.domain.org import OrgNode, OrgNodeType
from finops_core.domain.quota import QuotaUsage
from finops_core.domain.resource import ResourceRef
from finops_core.errors import AccessDenied, CollectionError

AS_OF = datetime(2026, 8, 24, 6, 0, tzinfo=UTC)
COLLECTED_AT = datetime(2026, 8, 24, 6, 5, tzinfo=UTC)
SESSION_EXPIRES_AT = datetime(2026, 8, 24, 7, 0, tzinfo=UTC)

WINDOW_START = datetime(2026, 8, 23, 0, 0, tzinfo=UTC)
WINDOW_END = datetime(2026, 8, 24, 0, 0, tzinfo=UTC)
PERIOD_START = date(2026, 8, 1)
PERIOD_END = date(2026, 9, 1)

TENANT_ID = UUID("00000000-0000-4000-8000-000000000001")
INGEST_RUN_ID = UUID("00000000-0000-4000-8000-000000000002")

REGION = "fake-region-a"
NAMESPACE = "Fake/Logs"
METRIC_NAME = "FakeIncomingBytes"

#: The scope key used for calls that are about the organization, not an account.
ORGANIZATION_SCOPE = "organization"

ROOT_ID = "r-fake"
OU_PLATFORM_ID = "ou-platform"
OU_PRODUCT_ID = "ou-product"

ACCOUNT_IDS = (
    "fake-platform-a",
    "fake-platform-b",
    "fake-product-a",
    "fake-product-b",
    "fake-product-denied",
)
ACCOUNT_KEYS = tuple(AccountKey(provider=Provider.AWS, account_id=i) for i in ACCOUNT_IDS)

#: The one account that cannot be read. Every screen has to survive this.
DENIED_ACCOUNT_KEY = ACCOUNT_KEYS[4]

_PARENT_OF = {
    ACCOUNT_IDS[0]: OU_PLATFORM_ID,
    ACCOUNT_IDS[1]: OU_PLATFORM_ID,
    ACCOUNT_IDS[2]: OU_PRODUCT_ID,
    ACCOUNT_IDS[3]: OU_PRODUCT_ID,
    ACCOUNT_IDS[4]: OU_PRODUCT_ID,
}

ORG_NODES: tuple[OrgNode, ...] = (
    OrgNode(
        node_id=ROOT_ID,
        node_type=OrgNodeType.ROOT,
        name="Fake organization",
        parent_id=None,
        provider=Provider.AWS,
        as_of=AS_OF,
        collected_at=COLLECTED_AT,
    ),
    OrgNode(
        node_id=OU_PLATFORM_ID,
        node_type=OrgNodeType.OU,
        name="Platform",
        parent_id=ROOT_ID,
        provider=Provider.AWS,
        as_of=AS_OF,
        collected_at=COLLECTED_AT,
    ),
    OrgNode(
        node_id=OU_PRODUCT_ID,
        node_type=OrgNodeType.OU,
        name="Product",
        parent_id=ROOT_ID,
        provider=Provider.AWS,
        as_of=AS_OF,
        collected_at=COLLECTED_AT,
    ),
    *(
        OrgNode(
            node_id=account_id,
            node_type=OrgNodeType.ACCOUNT,
            name=account_id,
            parent_id=_PARENT_OF[account_id],
            provider=Provider.AWS,
            as_of=AS_OF,
            collected_at=COLLECTED_AT,
        )
        for account_id in ACCOUNT_IDS
    ),
)

ACCOUNTS: tuple[CloudAccount, ...] = tuple(
    CloudAccount(
        key=key,
        name=key.account_id,
        status=AccountStatus.ACTIVE,
        parent_node_id=_PARENT_OF[key.account_id],
        as_of=AS_OF,
        collected_at=COLLECTED_AT,
    )
    for key in ACCOUNT_KEYS
)

#: Passing `failures` to the provider replaces this entirely, so a test states
#: exactly what fails rather than inheriting a plan it cannot see.
DEFAULT_FAILURES: dict[str, type[CollectionError]] = {str(DENIED_ACCOUNT_KEY): AccessDenied}

COST_ROWS: tuple[CostRecord, ...] = tuple(
    CostRecord(
        tenant_id=TENANT_ID,
        ingest_run_id=INGEST_RUN_ID,
        # The real digest, not "fake:account". The contract asks every adapter
        # to compute a line item's identity the same way, and it caught this:
        # a fake with an identity the collector would never produce proves the
        # upsert against a shape that cannot occur.
        source_fingerprint=source_fingerprint(
            billing_account_id=ACCOUNT_IDS[0],
            sub_account_id=key.account_id,
            charge_period_start=WINDOW_START,
            charge_period_end=WINDOW_END,
            service_name="FakeLogs",
            resource_id=None,
            sku_id=None,
            charge_category="Usage",
            commitment_discount_id=None,
        ),
        as_of=AS_OF,
        collected_at=COLLECTED_AT,
        billing_account_id=ACCOUNT_IDS[0],
        sub_account_id=key.account_id,
        billing_period_start=PERIOD_START,
        billing_period_end=PERIOD_END,
        charge_period_start=WINDOW_START,
        charge_period_end=WINDOW_END,
        provider_name="Fake",
        publisher_name="Fake",
        invoice_issuer_name="Fake",
        service_name="FakeLogs",
        service_category="Management and Governance",
        resource_id=None,
        resource_name=None,
        region_id=REGION,
        availability_zone=None,
        charge_category="Usage",
        charge_description="Fixture charge",
        sku_id=None,
        pricing_quantity=Decimal("2"),
        consumed_quantity=Decimal("2"),
        consumed_unit="GB",
        billed_cost=Decimal("1.00"),
        effective_cost=Decimal("1.00"),
        list_cost=Decimal("1.20"),
        contracted_cost=None,
        commitment_discount_id=None,
        commitment_discount_type=None,
        commitment_discount_status=None,
        tags=MappingProxyType({"finops:module": "fixture"}),
    )
    for key in ACCOUNT_KEYS[:4]
)

METRIC_POINTS: tuple[MetricPoint, ...] = tuple(
    MetricPoint(
        account_key=ACCOUNT_KEYS[0],
        namespace=NAMESPACE,
        metric_name=METRIC_NAME,
        statistic="Sum",
        unit="Bytes",
        value=Decimal(value),
        at=at,
        as_of=AS_OF,
        collected_at=COLLECTED_AT,
    )
    for value, at in (("1024", WINDOW_START), ("2048", WINDOW_END))
)

RESOURCES: tuple[ResourceRef, ...] = tuple(
    ResourceRef(
        account_key=ACCOUNT_KEYS[0],
        resource_id=resource_id,
        resource_type="Fake::Compute::Instance",
        region_id=REGION,
        name=resource_id,
        tags=MappingProxyType({"finops:module": "fixture"}),
        as_of=AS_OF,
        collected_at=COLLECTED_AT,
    )
    for resource_id in ("fake-resource-a", "fake-resource-b")
)

QUOTAS: tuple[QuotaUsage, ...] = (
    QuotaUsage(
        account_key=ACCOUNT_KEYS[0],
        region_id=REGION,
        service_code="fake-logs",
        quota_code="FAKE-1",
        quota_name="Concurrent queries",
        quota_limit=Decimal("30"),
        used=Decimal("4"),
        as_of=AS_OF,
        collected_at=COLLECTED_AT,
    ),
    QuotaUsage(
        account_key=ACCOUNT_KEYS[0],
        region_id=REGION,
        service_code="fake-logs",
        quota_code="FAKE-2",
        quota_name="Retained log groups",
        quota_limit=Decimal("100"),
        # The provider publishes no usage for this one. None, never zero.
        used=None,
        as_of=AS_OF,
        collected_at=COLLECTED_AT,
    ),
)

VALID_TOKEN = "fake-token"

PRINCIPAL = Principal(
    principal_id="fake-principal",
    display_name="Fixture User",
    tenant_id=TENANT_ID,
    groups=frozenset({"finops-readers"}),
)

#: A principal the fixture has never heard of. Resolves to an empty scope.
STRANGER = Principal(
    principal_id="fake-stranger",
    display_name="Unknown",
    tenant_id=TENANT_ID,
    groups=frozenset(),
)
