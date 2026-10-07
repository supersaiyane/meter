"""The domain holds facts, and a fact that cannot say when it was true is not one.

Three constraints from CLAUDE.md meet in this module. Constraint 4, every fact
carries `as_of`. Constraint 10, two timestamps on every figure, because
conflating them makes a stale number look fresh. Constraint 2, the canonical
cost schema is FOCUS 1.1 and is not ours to improve.

The FOCUS test reads the column list out of `docs/07-DATA-MODEL.md` rather than
out of a list kept next to the entity. A list kept next to the entity would
agree with the entity by construction and prove nothing. Reading the schema
document means the entity and the table it is stored in cannot drift apart.
"""

from __future__ import annotations

import dataclasses
import importlib
import pkgutil
import re
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

import finops_core.domain as domain_package
from finops_core.domain.account import AccountKey, AccountStatus, CloudAccount, Provider
from finops_core.domain.cost import CostRecord
from finops_core.domain.fact import Fact
from finops_core.domain.identity import Entitlement, Principal
from finops_core.domain.ingest import CollectionFailure, IngestRun, RunStatus, Watermark
from finops_core.domain.metrics import MetricPoint
from finops_core.domain.org import OrgNode, OrgNodeType
from finops_core.domain.quota import QuotaUsage
from finops_core.domain.resource import ResourceRef
from finops_core.domain.tenant import Scope, Tenant

ROOT = Path(__file__).resolve().parent.parent.parent
DATA_MODEL = ROOT / "docs" / "07-DATA-MODEL.md"

NOW = datetime(2026, 8, 24, 9, 0, tzinfo=UTC)
TENANT = uuid4()
KEY = AccountKey(provider=Provider.AWS, account_id="111111111111")


def sample_cost_record(**overrides: object) -> CostRecord:
    base: dict[str, object] = {
        "tenant_id": TENANT,
        "ingest_run_id": uuid4(),
        "source_fingerprint": "sha256:abc",
        "as_of": NOW,
        "collected_at": NOW,
        "billing_account_id": "111111111111",
        "sub_account_id": "222222222222",
        "billing_period_start": date(2026, 8, 1),
        "billing_period_end": date(2026, 9, 1),
        "charge_period_start": NOW,
        "charge_period_end": NOW,
        "provider_name": "AWS",
        "publisher_name": "AWS",
        "invoice_issuer_name": "AWS",
        "service_name": "AmazonCloudWatch",
        "service_category": "Management and Governance",
        "resource_id": None,
        "resource_name": None,
        "region_id": "eu-west-1",
        "availability_zone": None,
        "charge_category": "Usage",
        "charge_description": "Logs scanned",
        "sku_id": None,
        "pricing_quantity": Decimal("1.5"),
        "consumed_quantity": Decimal("1.5"),
        "consumed_unit": "GB",
        "billed_cost": Decimal("0.75"),
        "effective_cost": Decimal("0.75"),
        "list_cost": None,
        "contracted_cost": None,
        "commitment_discount_id": None,
        "commitment_discount_type": None,
        "commitment_discount_status": None,
        "tags": {"finops:module": "ingest"},
    }
    base.update(overrides)
    return CostRecord(**base)  # type: ignore[arg-type]


def every_entity() -> list[object]:
    """One constructed instance of every entity in the domain."""
    return [
        Tenant(tenant_id=TENANT, name="acme"),
        Scope(tenant_id=TENANT, is_global=False, accounts=frozenset({KEY})),
        KEY,
        CloudAccount(
            key=KEY,
            name="production",
            status=AccountStatus.ACTIVE,
            parent_node_id="ou-1",
            as_of=NOW,
            collected_at=NOW,
        ),
        OrgNode(
            node_id="r-1",
            node_type=OrgNodeType.ROOT,
            name="root",
            parent_id=None,
            provider=Provider.AWS,
            as_of=NOW,
            collected_at=NOW,
        ),
        Principal(principal_id="p1", display_name="Ada", tenant_id=TENANT, groups=frozenset()),
        Entitlement(
            principal=Principal(
                principal_id="p1", display_name="Ada", tenant_id=TENANT, groups=frozenset()
            ),
            scope=Scope(tenant_id=TENANT, is_global=True, accounts=frozenset()),
            as_of=NOW,
            collected_at=NOW,
        ),
        IngestRun(
            run_id=uuid4(),
            tenant_id=TENANT,
            collector="org_tree",
            status=RunStatus.RUNNING,
            started_at=NOW,
            finished_at=None,
            accounts_total=3,
            accounts_succeeded=0,
            accounts_failed=0,
        ),
        CollectionFailure(
            scope_key="acct:111111111111",
            collector="org_tree",
            cause="AccessDenied",
            remediation="Check the StackSet deployment.",
            as_of=NOW,
            collected_at=NOW,
        ),
        Watermark(
            tenant_id=TENANT,
            collector="org_tree",
            account_key=KEY,
            watermark=NOW,
            as_of=NOW,
            collected_at=NOW,
        ),
        sample_cost_record(),
    ]


# --- immutability ------------------------------------------------------------


def test_entities_are_immutable() -> None:
    for entity in every_entity():
        field = dataclasses.fields(entity)[0].name  # type: ignore[arg-type]
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(entity, field, None)


def test_every_domain_class_is_a_frozen_dataclass() -> None:
    """A single mutable entity is enough to reintroduce hidden side effects."""
    for module in pkgutil.iter_modules(domain_package.__path__):
        loaded = importlib.import_module(f"{domain_package.__name__}.{module.name}")
        for attribute in vars(loaded).values():
            if dataclasses.is_dataclass(attribute) and isinstance(attribute, type):
                # __dataclass_params__ is set by the decorator and is not on
                # the protocol the type checker uses for a dataclass type.
                params = attribute.__dataclass_params__  # type: ignore[attr-defined]
                assert params.frozen, attribute.__name__


def test_updates_return_a_new_instance() -> None:
    run = IngestRun(
        run_id=uuid4(),
        tenant_id=TENANT,
        collector="org_tree",
        status=RunStatus.RUNNING,
        started_at=NOW,
        finished_at=None,
        accounts_total=3,
        accounts_succeeded=0,
        accounts_failed=0,
    )
    finished = dataclasses.replace(run, status=RunStatus.SUCCEEDED, accounts_succeeded=3)
    assert run.status is RunStatus.RUNNING
    assert finished.status is RunStatus.SUCCEEDED
    assert finished.run_id == run.run_id


def test_tags_cannot_be_mutated_through_the_mapping() -> None:
    record = sample_cost_record()
    with pytest.raises(TypeError):
        record.tags["finops:module"] = "something else"  # type: ignore[index]


# --- freshness ---------------------------------------------------------------


def test_as_of_is_required() -> None:
    for fact_type in Fact.__subclasses__():
        fields = {f.name: f for f in dataclasses.fields(fact_type)}
        assert "as_of" in fields
        assert fields["as_of"].default is dataclasses.MISSING
        assert fields["as_of"].default_factory is dataclasses.MISSING


def test_every_fact_carries_both_timestamps() -> None:
    """Constraint 10. as_of is when it was true, collected_at is when we fetched it."""
    for fact_type in Fact.__subclasses__():
        names = {f.name for f in dataclasses.fields(fact_type)}
        assert {"as_of", "collected_at"} <= names, fact_type.__name__


def test_constructing_a_fact_without_as_of_raises() -> None:
    with pytest.raises(TypeError):
        CloudAccount(  # type: ignore[call-arg]
            key=KEY,
            name="production",
            status=AccountStatus.ACTIVE,
            parent_node_id=None,
            collected_at=NOW,
        )


# --- provider neutrality -----------------------------------------------------


def test_cloud_account_carries_provider() -> None:
    account = CloudAccount(
        key=AccountKey(provider=Provider.GCP, account_id="proj-1"),
        name="analytics",
        status=AccountStatus.ACTIVE,
        parent_node_id=None,
        as_of=NOW,
        collected_at=NOW,
    )
    assert account.provider is Provider.GCP


def test_an_account_key_renders_with_its_provider() -> None:
    """The rendered form reaches logs and scope keys, so it must not read as a bare id."""
    assert str(KEY) == "aws:111111111111"
    assert str(AccountKey(provider=Provider.GCP, account_id="proj-1")) == "gcp:proj-1"


def test_no_entity_exposes_a_bare_account_id() -> None:
    """A bare AWS identifier in the domain is how multi cloud becomes a rewrite."""
    for entity in every_entity():
        if isinstance(entity, AccountKey | CostRecord):
            continue
        names = {f.name for f in dataclasses.fields(entity)}  # type: ignore[arg-type]
        assert "account_id" not in names, type(entity).__name__


# --- organization ------------------------------------------------------------


def test_org_node_type_is_a_closed_set() -> None:
    assert {member.name for member in OrgNodeType} == {"ROOT", "OU", "ACCOUNT"}


def test_a_root_cannot_have_a_parent() -> None:
    with pytest.raises(ValueError, match="ROOT"):
        OrgNode(
            node_id="r-1",
            node_type=OrgNodeType.ROOT,
            name="root",
            parent_id="ou-1",
            provider=Provider.AWS,
            as_of=NOW,
            collected_at=NOW,
        )


def test_a_non_root_must_have_a_parent() -> None:
    with pytest.raises(ValueError, match="parent"):
        OrgNode(
            node_id="ou-1",
            node_type=OrgNodeType.OU,
            name="platform",
            parent_id=None,
            provider=Provider.AWS,
            as_of=NOW,
            collected_at=NOW,
        )


# --- scope -------------------------------------------------------------------


def test_scope_is_global_or_an_explicit_set_never_a_wildcard() -> None:
    explicit = Scope(tenant_id=TENANT, is_global=False, accounts=frozenset({KEY}))
    assert explicit.is_global is False
    assert explicit.accounts == frozenset({KEY})
    assert all(not isinstance(a, str) for a in explicit.accounts)


def test_a_global_scope_may_not_also_enumerate_accounts() -> None:
    with pytest.raises(ValueError, match="global"):
        Scope(tenant_id=TENANT, is_global=True, accounts=frozenset({KEY}))


def test_scope_permits_only_what_it_names() -> None:
    scope = Scope(tenant_id=TENANT, is_global=False, accounts=frozenset({KEY}))
    other = AccountKey(provider=Provider.AWS, account_id="999999999999")
    assert scope.permits(KEY) is True
    assert scope.permits(other) is False


def test_a_global_scope_permits_everything() -> None:
    scope = Scope(tenant_id=TENANT, is_global=True, accounts=frozenset())
    assert scope.permits(KEY) is True


def test_an_empty_scope_permits_nothing() -> None:
    """A principal with no grants must fail closed rather than read everything."""
    scope = Scope(tenant_id=TENANT, is_global=False, accounts=frozenset())
    assert scope.permits(KEY) is False


def test_a_global_scope_narrowed_to_one_account_reads_that_account_alone() -> None:
    """FEAT-075. The account chosen in the address, applied where scope already is."""
    narrowed = Scope(
        tenant_id=TENANT, is_global=True, accounts=frozenset(), principal_id="p1"
    ).narrowed_to(KEY)

    assert narrowed.is_global is False
    assert narrowed.accounts == frozenset({KEY})
    assert narrowed.chosen == KEY
    assert (narrowed.tenant_id, narrowed.principal_id) == (TENANT, "p1")
    assert narrowed.permits(AccountKey(provider=Provider.AWS, account_id="999999999999")) is False


def test_narrowing_never_widens_a_scope() -> None:
    """A link naming an account the session cannot see must read nothing, not that account."""
    outside = AccountKey(provider=Provider.AWS, account_id="999999999999")
    scope = Scope(tenant_id=TENANT, is_global=False, accounts=frozenset({KEY}))

    with pytest.raises(ValueError, match="never widens"):
        scope.narrowed_to(outside)


@pytest.mark.parametrize(
    ("is_global", "accounts"),
    [
        (False, frozenset({KEY, AccountKey(provider=Provider.AWS, account_id="999999999999")})),
        (True, frozenset()),
        (False, frozenset()),
    ],
)
def test_a_chosen_account_is_the_whole_of_its_scope(
    is_global: bool, accounts: frozenset[AccountKey]
) -> None:
    with pytest.raises(ValueError, match="chosen"):
        Scope(tenant_id=TENANT, is_global=is_global, accounts=accounts, chosen=KEY)


# --- FOCUS -------------------------------------------------------------------


def checked_in_columns() -> tuple[set[str], set[str]]:
    """The Meter columns and the FOCUS columns, read out of the schema document."""
    text = DATA_MODEL.read_text(encoding="utf-8")
    start = text.index("CREATE TABLE cost_focus_daily (")
    block = text[start : text.index("PRIMARY KEY", start)]
    meter_half, _, focus_half = block.partition("-- FOCUS 1.1")
    column = re.compile(r"^\s{4}([a-z_]+)\s{2,}", re.MULTILINE)
    return set(column.findall(meter_half)), set(column.findall(focus_half))


def test_cost_record_matches_focus_columns() -> None:
    meter, focus = checked_in_columns()
    assert focus, "the FOCUS section of the schema document was not found"
    fields = {f.name for f in dataclasses.fields(CostRecord)}
    assert fields == meter | focus


#: The shorter, friendlier names an author reaches for when renaming a FOCUS
#: column. None of them may appear, because each one is a mapping somebody then
#: maintains forever, and an ambiguous one at that: which cost, whose account.
FRIENDLY_RENAMES = frozenset(
    {"cost", "amount", "total", "account", "service", "region", "period", "quantity", "unit"}
)


def test_focus_columns_are_not_renamed_to_something_more_readable() -> None:
    """ADR-0002. The standard's value is that it is not ours to improve."""
    _, focus = checked_in_columns()
    fields = {f.name for f in dataclasses.fields(CostRecord)}
    assert focus <= fields
    assert not fields & FRIENDLY_RENAMES


def test_money_is_never_a_float() -> None:
    record = sample_cost_record()
    for name in ("billed_cost", "effective_cost", "pricing_quantity", "consumed_quantity"):
        value = getattr(record, name)
        assert value is None or isinstance(value, Decimal)


# --- the three port contract types -------------------------------------------


def test_a_metric_point_separates_the_instant_from_the_freshness() -> None:
    """`at` is what the value describes. `as_of` is when the source was true."""
    point = MetricPoint(
        account_key=KEY,
        namespace="AWS/Logs",
        metric_name="IncomingBytes",
        statistic="Sum",
        unit="Bytes",
        value=Decimal("1024"),
        at=NOW,
        as_of=NOW,
        collected_at=NOW,
    )
    assert point.value == Decimal("1024")
    assert point.at == point.as_of


def test_a_resource_reference_holds_immutable_tags() -> None:
    ref = ResourceRef(
        account_key=KEY,
        resource_id="i-0123456789abcdef0",
        resource_type="AWS::EC2::Instance",
        region_id="eu-west-1",
        name="worker",
        tags={"finops:module": "ingest"},
        as_of=NOW,
        collected_at=NOW,
    )
    assert ref.tags["finops:module"] == "ingest"
    with pytest.raises(TypeError):
        ref.tags["finops:module"] = "other"  # type: ignore[index]


def test_unpublished_quota_usage_is_none_and_never_zero() -> None:
    """Zero would read as plenty of headroom on a quota that is about to be hit."""
    quota = QuotaUsage(
        account_key=KEY,
        region_id="eu-west-1",
        service_code="logs",
        quota_code="L-12345",
        quota_name="Concurrent queries",
        quota_limit=Decimal("30"),
        used=None,
        # P5 added the pair this has to satisfy: a quota nothing measures says why, and
        # `tests/core/test_quota.py` is where that rule is exercised properly.
        unmeasurable_reason="CloudWatch publishes no usage metric for this quota",
        as_of=NOW,
        collected_at=NOW,
    )
    assert quota.used is None


def test_the_service_and_host_providers_follow_provider_name_until_a_source_names_them() -> None:
    """P10 spec section 5.2: FOCUS replaced ProviderName with ServiceProviderName, and the host
    equals the service provider unless one is exposed. One rule, in the record, for every source."""
    derived = sample_cost_record()
    assert (derived.service_provider_name, derived.host_provider_name) == ("AWS", "AWS")
    named = sample_cost_record(service_provider_name="Seller", host_provider_name="AWS")
    assert (named.service_provider_name, named.host_provider_name) == ("Seller", "AWS")
    hosted_by_seller = sample_cost_record(service_provider_name="Seller")
    assert hosted_by_seller.host_provider_name == "Seller"


def test_an_invoice_detail_is_its_invoice_until_a_source_says_otherwise() -> None:
    assert sample_cost_record().invoice_detail_id is None
    assert sample_cost_record(invoice_id="INV-1").invoice_detail_id == "INV-1"
    assert (
        sample_cost_record(invoice_id="INV-1", invoice_detail_id="D-7").invoice_detail_id == "D-7"
    )
