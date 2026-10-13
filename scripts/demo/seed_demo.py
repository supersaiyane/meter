"""Fill a local database with a demo estate, so the product can be developed
against something before any of it can talk to AWS.

The data is produced by running the **real collectors** against the **existing
fake adapters**, not by writing rows, and through the **real run ledger**. That
matters twice over. A second hand written estate would drift from what the
collectors actually write, and the first time the real ones ran the screens
would change shape. And going through the ledger means the ingest and freshness
screens fill from the same act of seeding rather than needing a second fixture
that agrees with the first by hand.

Four collectors, in dependency order: the organization tree, then role health
per account, then the platform's own cost, then the query audit. Every row here
is a row the pipeline would have written.

Three safeguards, because a seeding script is exactly the kind of tool that ends
up pointed somewhere it should not be.

**It refuses any database that is not local.** Not a warning, a refusal. This is
the only one of the three that matters if the others are forgotten.

**Everything lives under one tenant with a fixed identifier.** Removal is then
exact rather than a search, and scope enforcement means the demo estate cannot
appear inside a real tenant's view even while it exists.

**`--remove` is part of this script rather than a note in a document.** The
request was to seed now and clear it later, and later is when nobody remembers
which tables were touched.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from sqlalchemy import create_engine, text

from finops_core.config import load_settings
from finops_core.domain.account import AccountKey, Provider
from finops_core.errors import CollectionError
from finops_fakes import containers as container_estate
from finops_fakes import cur, fixtures, prices, utilization
from finops_fakes import estate_shape as shape
from finops_fakes import quotas as quota_estate
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
from finops_fakes.cur import FakeCostExport, estate
from finops_fakes.estate_metrics import EstateMetrics, ec2_candidates, volume_candidates
from finops_fakes.evidence import FakeQueryEvidence
from finops_fakes.health import FakeRoleHealth
from finops_fakes.invoices import FakeInvoices
from finops_fakes.ownership import FakeResourceCreators, FakeServiceCatalogue
from finops_fakes.platform_cost import FakePlatformCost
from finops_fakes.provider import FakeProvider
from finops_fakes.recommendations import FakeRecommendationSource
from finops_fakes.surface import FakeQuerySurface, queries_as_of
from finops_fakes.terraform_state import LOCATIONS as FAKE_STATE_LOCATIONS
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
from finops_ingest.collectors.gpu_utilization import GpuUtilizationCollector
from finops_ingest.collectors.iac_state import IacStateCollector
from finops_ingest.collectors.instance_catalog import InstanceCatalogCollector
from finops_ingest.collectors.inventory import InventoryCollector
from finops_ingest.collectors.invoices import InvoiceCollector
from finops_ingest.collectors.openai_usage import openai_collector
from finops_ingest.collectors.org_tree import OrgTreeCollector
from finops_ingest.collectors.ownership import OwnershipCollector
from finops_ingest.collectors.partitions import ensure_partition, partition_maintenance
from finops_ingest.collectors.platform_cost import PlatformCostCollector
from finops_ingest.collectors.price_catalog import PriceCatalogCollector
from finops_ingest.collectors.query_audit import (
    QueryAuditCollector,
    default_ingest_rate,
    rates_from,
)
from finops_ingest.collectors.quotas import QuotaCollector
from finops_ingest.collectors.realized_savings import (
    RealizedSavingsCollector,
)
from finops_ingest.collectors.recommendations import RecommendationCollector
from finops_ingest.collectors.savings_ledger import SavingsLedgerCollector
from finops_ingest.collectors.savings_plan_rates import SavingsPlanRatesCollector
from finops_ingest.collectors.score import ScoreCollector
from finops_ingest.collectors.spot_prices import SpotPricesCollector
from finops_ingest.collectors.waste_cloudwatch import WasteCloudWatchCollector
from finops_ingest.collectors.waste_compute import Candidate, WasteComputeCollector
from finops_ingest.collectors.waste_parking import Parkable, WasteParkingCollector
from finops_ingest.collectors.waste_volumes import VolumeCandidate
from finops_ingest.ledger import RunLedger
from finops_ingest.registry import CollectorContext, install_default_schedule
from finops_query.parser import GrafanaQueryParser

#: Fixed, and readable as "seeded" in the first block, so a row found in a
#: database months from now identifies itself without a lookup.
DEMO_TENANT = UUID("5eeded00-0000-4000-8000-000000000001")
DEMO_NAME = "demo estate, seeded, safe to remove"

#: How far back the seeded window reaches. Thirty, because the platform cost
#: screen draws a thirty day sparkline and a seven day window left it empty.
DEMO_WINDOW_DAYS = 30

#: The account whose health check fails outright, as opposed to the one that
#: answers `access denied`. The two are different facts and the screens render
#: them differently: one is an account whose role is misconfigured, the other is
#: an account Meter could not ask about at all. An estate with neither leaves
#: the failure rendering on three screens permanently unexercised.
UNREADABLE_ACCOUNT = str(fixtures.ACCOUNT_KEYS[1])

#: Hosts a seed may write to. The compose service name counts as local because
#: it only resolves inside the local stack.
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "postgres", ""})

#: Reverse dependency order. A removal that orphaned a foreign key would leave
#: the database refusing it and the operator guessing why.
DEMO_TABLES = (
    "collector_schedule",
    "audit_event",
    "sync_error",
    "ingest_watermark",
    # P4, FEAT-030 and FEAT-031, and they go here rather than further down because all
    # three reference `ingest_run`. The first draft put them after it, and
    # `test_seed_then_remove_leaves_nothing_behind` failed on the foreign key, which is
    # exactly what happened to `query_adhoc` and is why that comment is still below.
    # Within the three: the edges reference the nodes, so the edges go first.
    "topology_edge",
    "topology_node",
    # P11, FEAT-077. Owners read from the nodes above; no foreign key, so anywhere above
    # the tenant would do, and beside the nodes is where a reader looks for it.
    "resource_owner",
    # TASK-P11-004. Which resources CloudTrail was asked about; no foreign key either.
    "creator_lookup",
    # P13, FEAT-082. Tokens per caller; it references the tenant only.
    "ai_usage_daily",
    # P13, FEAT-083. The AI provider organizations a tenant connected; the tenant only.
    "ai_provider_account",
    # P13, FEAT-084. How busy each GPU instance was; the tenant only.
    "gpu_utilization_daily",
    # P14, FEAT-086. What each account holds; the tenant only.
    "commitment_inventory",
    "graph_coverage",
    # P6, FEAT-035 and FEAT-036. Above `ingest_run` like the P4 and P5 tables,
    # because both carry the run that wrote them. Neither references the other, so
    # the order between the two is only convention.
    "container_usage",
    "container_cluster",
    # P5, FEAT-033 and FEAT-034, above `ingest_run` for the same reason the three P4
    # tables are: both quota tables carry the run that wrote them. The history table has
    # no run of its own and is ordered beside the requests it belongs to.
    "quota_request_history",
    "quota_request",
    "quota_usage",
    # P7, FEAT-041. Above `ingest_run` like the P4 to P6 tables, because each digest
    # carries the run that composed it.
    "team_digest",
    "ingest_run",
    "platform_cost",
    "org_node",
    "cloud_account",
    # P7, FEAT-038, FEAT-042 and FEAT-046. The seed writes neither, and a person asking a
    # question on the demo writes both, so unseed removes them. The event references its
    # exchange and has no cascade, so the event goes first.
    "redaction_event",
    "assistant_exchange",
    # P8, FEAT-067. The seed writes none, and every export made on the demo writes one,
    # so unseed removes them. It references the tenant and nothing else.
    "report_run",
    # P8, FEAT-069. The seed writes none, and every schedule made on the demo writes one. It
    # references the views below and is referenced by the runs above, so it goes between them.
    "report_schedule",
    # P8, FEAT-068. The seed writes none, and every view saved on the demo writes one, so
    # unseed removes them. It references the tenant and nothing else.
    "saved_view",
    # FEAT-051. Added with the table in TASK-P2-026 and missed here, so unseed
    # failed on the foreign key rather than removing the estate. A table that
    # references the tenant and is not in this list makes the teardown a lie.
    "query_adhoc",
    "remediation_change",
    "enforcement_action",
    "folder_team_map",
    "query_finding",
    "query_definition",
    "grafana_instance",
    # P3, FEAT-043. The components reference the score, so they go first.
    "finops_score_component",
    "finops_score",
    # P3, FEAT-025 and FEAT-029. Both of these reference `recommendation`, so
    # both go before it: the measured verdict and the lifecycle log first, the
    # finding they are about second.
    # P11, FEAT-078. A month references its credit, and a credit the verification and the
    # recommendation, so these go first.
    "savings_credit_month",
    "savings_credit",
    "realized_saving",
    "recommendation_event",
    # Before the recommendations it hangs off and the prices it quotes. TASK-P9-006.
    "recommendation_option",
    "recommendation",
    # P1, FEAT-023. Derived from the daily rows, so it goes before them.
    "cost_anomaly",
    # P1, FEAT-055. Derived from commitment_coverage, so it goes before it, even though it
    # holds no foreign key to it: reverse dependency order is the rule this list follows and
    # an exception justified by the absence of a key is one somebody will later add.
    # P4, FEAT-057. References only the tenant, so its place here is reverse dependency
    # order for its own sake rather than for a key.
    "resource_management",
    "sizing_refusal",
    # P1, FEAT-060. References only the tenant.
    "budget",
    # P10, FEAT-076. Both reference only the tenant.
    "invoice_detail",
    "billing_period",
    # P9, migration 0033. After `recommendation`, whose target references a price, and each
    # price before the version it belongs to. The rest reference only the tenant.
    "price",
    "price_list_version",
    "instance_type_spec",
    "volume_type_spec",
    "spot_price_daily",
    "spot_price",
    "commitment_action",
    # P1, FEAT-024. Neither references the other, and both reference only the
    # tenant, so their order between themselves does not matter. The daily rows, TASK-P8-013,
    # are the same commitments at another grain and reference only the tenant too.
    "commitment_day",
    "commitment_coverage",
    "commitment_use",
    # P1. The monthly aggregate goes before the daily rows it is derived from,
    # for the same reason as everything else in this list: reverse dependency
    # order, so a removal never orphans a foreign key.
    "cost_focus_monthly",
    "cost_focus_daily",
    "cost_provider_extra",
)


class NotLocalError(RuntimeError):
    """The database is not one this script is allowed to write to."""


def require_local(database_url: str) -> None:
    """Refuse anything that is not a local database.

    The whole risk of a seeding tool is that it runs somewhere real. Everything
    else in this file is tidiness; this is the part that matters.
    """
    host = (urlsplit(database_url).hostname or "").lower()
    if host not in LOCAL_HOSTS:
        raise NotLocalError(
            f"refusing to seed {host!r}. This writes a fake estate and is only "
            f"ever for a local database, one of {sorted(LOCAL_HOSTS - {''})}."
        )


@dataclass(frozen=True)
class Unit:
    """What a collector reads off a work unit, and nothing else.

    The dispatcher's own `WorkUnit` is not used here because it carries
    scheduling state this script has no business setting. `CollectorContext`
    types its unit loosely for exactly this reason.
    """

    tenant_id: UUID
    scope_key: str = "organization"
    account: AccountKey | None = None
    region: str | None = None
    window_start: datetime | None = None
    window_end: datetime | None = None


@dataclass(frozen=True)
class Seeded:
    """What one seeding run produced, for the operator to read back."""

    rows: int
    instances: int
    accounts: int
    runs: int


def _through_the_ledger(
    ledger: RunLedger,
    collector: Any,
    connection: Any,
    unit: Unit,
    name: str,
    settings: Any = None,
) -> int:
    """Run one collector as the worker would, recording the run either way.

    The failure branch is not defensive tidiness. The fake estate contains an
    account that refuses, because the screens exist to report exactly that, and
    a seeding script that let one refusal abort the whole run would produce a
    demo estate with no failures in it, which is the estate least worth
    developing against.
    """
    if unit.window_start is None or unit.window_end is None:
        # Every unit this script builds carries a window. A missing one is a bug
        # here rather than a case to paper over with a default that would put a
        # run in the ledger claiming a window nobody chose.
        raise ValueError(f"the {name} unit was built without a window")
    claim = ledger.claim(name, unit.scope_key, unit.window_start, unit.window_end)
    if claim is None:
        return 0
    ledger.running(claim)
    try:
        outcome = collector(
            # The claim's run id, as the worker passes it. The cost collector
            # writes it into a NOT NULL column and removes on it, so a context
            # without one is a run it refuses rather than a run that invents a
            # number naming nothing.
            CollectorContext(
                unit=unit,
                connection=connection,
                run_id=claim.run_id,
                # Only the collectors that need it get it. `cost_anomaly` refuses to
                # run without settings, because its severity boundaries and its
                # sensitivity are configuration and a default would put an invented
                # severity on a screen.
                settings=settings,
            )
        )
    except CollectionError as failure:
        ledger.fail(claim, failure)
        ledger.record_sync_error(name, unit.scope_key, failure)
        return 0
    ledger.complete(claim, items_written=outcome.items_written, bytes_read=0)
    return int(outcome.items_written)


#: The fake providers the demo connects, as `scripts/ops/connect_ai_provider.py` connects one.
DEMO_AI_PROVIDERS = (FAKE_OPENAI, FAKE_ANTHROPIC)

CONNECT_PROVIDER = text(
    "INSERT INTO ai_provider_account (provider, organization_id, tenant_id, name, "
    "key_secret_name, enrolled_at) VALUES (:provider, :organization, :tenant, :name, :key, :at) "
    "ON CONFLICT (provider, organization_id) DO NOTHING"
)


def _seed_ai(ledger: RunLedger, connection: Any, unit: Callable[..., Unit], now: datetime) -> int:
    """AI spend from every source, P13: both providers, the invocation logs and the GPU agent.

    After the bill, whose Bedrock and GPU lines these are read beside. The providers are connected
    first, so their collectors find them the way a deployment's do, through the table rather than a
    fixed list. One account with Bedrock features sends its logs to S3 only and reads NotOptedIn,
    and one GPU instance publishes nothing, so the screen has both absences to say.
    """
    for account in DEMO_AI_PROVIDERS:
        connection.execute(
            CONNECT_PROVIDER,
            {
                "provider": account.provider,
                "organization": account.organization_id,
                "tenant": DEMO_TENANT,
                "name": account.name,
                "key": account.key_secret_name,
                "at": now,
            },
        )
    written = 0
    for name, build in (
        ("openai_usage", openai_collector),
        ("anthropic_usage", anthropic_collector),
    ):
        provider = build(lambda _context, _account: FakeProviderReports(at=now), clock=lambda: now)
        written += _through_the_ledger(ledger, provider, connection, unit(scope_key=name), name)
    per_account = (
        ("bedrock_invocations", {feature.account for feature in cur.BEDROCK_FEATURES}),
        ("gpu_utilization", {gpu.account for gpu in cur.GPU_INSTANCES}),
    )
    for name, accounts in per_account:
        for account_id in sorted(accounts):
            key = AccountKey(provider=Provider.AWS, account_id=account_id)
            collector: Any = (
                BedrockInvocationsCollector(FakeInvocationLogs(at=now), clock=lambda: now)
                if name == "bedrock_invocations"
                else GpuUtilizationCollector(FakeGpuMetrics(at=now), clock=lambda: now)
            )
            written += _through_the_ledger(
                ledger,
                collector,
                connection,
                unit(scope_key=f"{key}:{fixtures.REGION}", account=key, region=fixtures.REGION),
                name,
            )
    return written


#: The account and region the seeded verifications sit in. Named rather than
#: repeated, because three functions read them and a typo in one would produce a
#: recommendation whose resource never joins to a charge.
DEMO_ACCOUNT = "fake-platform-a"
DEMO_REGION = "eu-west-1"

#: The one slice the seeded inventory run deliberately does not read, so its
#: `graph_coverage` row stays UNREAD.
#:
#: The same pair `finops_fakes.topology.coverage_state` already calls unread, so the seeded
#: estate and a live read of the fake agree about which slice it is. Named here because
#: `docs/runbooks/demo.md` has to name it and a demo whose deliberately broken part is
#: undocumented reads as a bug.
UNREAD_ACCOUNT = "fake-product-b"
UNREAD_REGION = shape.REGION_B

#: The clock the utilization estate is generated against. Two years of hourly
#: behaviour end here, so a collector run on a later clock would read a window half
#: of which the estate does not cover and would refuse most of it for too little
#: history. The bill uses the real `now`, because a demo wants this month's periods.
ESTATE_AT = fixtures.AS_OF

#: How many billing periods the seeded bill covers. See the comment where it is
#: used: ninety days of history has to fit, with margin.
BILL_PERIODS = 5


def _always[Chosen](chosen: list[Chosen]) -> Callable[[CollectorContext], list[Chosen]]:
    """The candidate list this run was built with, whatever context it is handed.

    A named factory rather than a lambda closing over the loop variable. The lambda
    form needs a default argument to capture the current list, which mypy cannot infer
    and which reads like the closure bug it exists to avoid.

    Generic since FEAT-054, because two collectors now take a candidate list and they take
    different records. Written for `Candidate` alone first, which made the second caller a
    type error rather than a copy of this function.
    """

    def candidates(_context: CollectorContext) -> list[Chosen]:
        return chosen

    return candidates


def _completed_work(connection: Any, now: datetime) -> None:
    """The recommendations behind the changes the bill already records.

    Every charge these are judged against is written by the cost collector from
    `cur.estate`, which since 2026-09-21 names every resource the utilization estate
    runs and moves the cost and the usage of the three in `cur.LANDED`. So this
    function writes recommendations and events and no charges at all.

    It used to write three resources of its own with hand written daily charges,
    because the bill named two resources per account and neither was one the estate
    modelled. `DATA_DICTIONARY.md` decision 6 is that gap, and the consequence was
    that the one screen proving this product works read a fixture written for it. The
    verdicts now come from the same rows a cost screen shows.

    The lifecycle is written directly rather than driven through four route calls,
    because the point of the fixture is the state of the bill sixty days later and
    walking the transitions would make this a test of the routes.
    """
    done_on = cur.landed_on(now)
    done_at = datetime(done_on.year, done_on.month, done_on.day, 12, tzinfo=UTC)

    for change in cur.LANDED:
        spec = utilization.spec(change.resource_id)
        recommendation_id = uuid4()
        # Idempotent like every collector around it. `make seed` runs once per day of
        # history, and a second insert of the same finished work would either fail on
        # the unique constraint or double the verdicts.
        created = connection.execute(
            text(
                "INSERT INTO recommendation (recommendation_id, tenant_id, sub_account_id, "
                "source, source_reference, waste_class, resource_id, region_id, "
                "estimated_monthly_saving, confidence, severity, observation_days, "
                "lifecycle, owner, rationale, as_of, collected_at) "
                "VALUES (:id, :t, :a, 'METER', :ref, :class, :res, :region, :saving, 'HIGH', "
                "'MEDIUM', 45, 'DONE', 'platform@example.local', :why, :at, :at) "
                "ON CONFLICT (tenant_id, source, source_reference) DO NOTHING "
                "RETURNING recommendation_id"
            ),
            {
                "id": recommendation_id,
                "t": DEMO_TENANT,
                "a": spec.account_id,
                "ref": f"seed:{change.resource_id}",
                "class": change.waste_class,
                "res": change.resource_id,
                "region": spec.region_id,
                # Modelled, and the whole monthly price: these are all findings whose
                # action is that the resource should not exist. The gap between this
                # and what the savings screen measured is what the runbook stops on.
                "saving": prices.monthly_usd(spec),
                "why": change.why,
                "at": now,
            },
        ).first()
        if created is None:
            # Already seeded on an earlier day, with its events.
            continue

        for target, occurred, previous in (
            ("OPEN", done_at - timedelta(days=21), None),
            ("ACCEPTED", done_at - timedelta(days=14), "OPEN"),
            ("IN_PROGRESS", done_at - timedelta(days=7), "ACCEPTED"),
            ("DONE", done_at, "IN_PROGRESS"),
        ):
            connection.execute(
                text(
                    "INSERT INTO recommendation_event (event_id, recommendation_id, tenant_id, "
                    "from_lifecycle, to_lifecycle, actor, reason, occurred_at, as_of, "
                    "collected_at) VALUES (:e, :id, :t, :from, :to, 'demo-seed', NULL, :at, "
                    ":at, :at)"
                ),
                {
                    "e": uuid4(),
                    "id": recommendation_id,
                    "t": DEMO_TENANT,
                    "from": previous,
                    "to": target,
                    "at": occurred,
                },
            )


def seed(engine: Any, settings: Any, now: datetime, latest: datetime | None = None) -> Seeded:
    """Create the tenant and run all four collectors into it.

    `latest` is the newest day of the history being laid down, and it is what
    tells this run how far in the past it is. Left out, `now` is the newest day
    and the estate is reported at full size, which is what a single day seed and
    every test that calls this already expect.
    """
    # Derived rather than passed, so the day being seeded and the distance back
    # to the present cannot disagree with each other.
    days_ago = (latest.date() - now.date()).days if latest else 0
    parser = GrafanaQueryParser()
    provider = FakeProvider(at=now)
    window_start = now - timedelta(days=DEMO_WINDOW_DAYS)
    written = 0

    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO tenant (tenant_id, name) VALUES (:id, :name) "
                "ON CONFLICT (tenant_id) DO NOTHING"
            ),
            {"id": DEMO_TENANT, "name": DEMO_NAME},
        )
        # Cadence is data, per ADR-0012, and an estate without it cannot judge
        # its own freshness: every collector read `not scheduled` and therefore
        # `stale`, one minute after it ran.
        install_default_schedule(connection, DEMO_TENANT, updated_by="seed_demo")

        ledger = RunLedger(
            connection,
            DEMO_TENANT,
            settings.run_claim_timeout_minutes,
            clock=lambda: now,
        )

        def unit(**extra: Any) -> Unit:
            return Unit(
                tenant_id=DEMO_TENANT,
                window_start=window_start,
                window_end=now,
                **extra,
            )

        # The tree first. Role health writes onto accounts the tree creates, and
        # doing it the other way round leaves health rows for accounts that do
        # not exist yet.
        written += _through_the_ledger(
            ledger, OrgTreeCollector(provider, clock=lambda: now), connection, unit(), "org_tree"
        )
        for account in fixtures.ACCOUNT_KEYS:
            written += _through_the_ledger(
                ledger,
                AccountHealthCollector(
                    FakeRoleHealth(refuse=UNREADABLE_ACCOUNT, at=now), clock=lambda: now
                ),
                connection,
                unit(
                    scope_key=f"{account}:{fixtures.REGION}",
                    account=account,
                    region=fixtures.REGION,
                ),
                "account_health",
            )
        written += _through_the_ledger(
            ledger,
            PlatformCostCollector(FakePlatformCost(), clock=lambda: now),
            connection,
            unit(),
            "platform_cost",
        )
        # Partitions before the cost rows, because `cost_focus_daily` is
        # partitioned by billing period and the database refuses a row with
        # nowhere to go. `partition_maintenance` does this in a running system
        # and the seed has to do it too, or the first cost run fails for a
        # reason that looks nothing like a seeding problem.
        written += _through_the_ledger(
            ledger,
            lambda context: partition_maintenance(context, clock=lambda: now),
            connection,
            unit(),
            "partition_maintenance",
        )
        # One run per billing period, because the collector reads whichever
        # period its export says is latest and that is all it reads. ISS-183.
        # Which periods to ingest is policy and policy lives above the port, so
        # the seed makes the choice by handing the collector one period at a
        # time. Without this the demo has a single month, and the comparison on
        # the summary is permanently absent, which is the one figure a person
        # looks at first.
        #
        # The estate is built at this day's clock, so its newest period is the
        # one still running. A fixture pinned to a fixed month stops being open
        # the day that month ends, and then the open period label has nothing
        # to label.
        # Five periods rather than three. The realized savings collector compares
        # the thirty days before a change to the thirty days ending sixty days
        # after it, which is ninety days of history and does not fit in three
        # calendar months with any margin at all.
        bill = estate(at=now, periods=BILL_PERIODS)
        # P13, FEAT-081 and FEAT-084: the bill's Bedrock lines and its GPU instances, in the one
        # bill the cost rows and the invoices are both built from, so the invoices still match.
        bill = cur.with_ai(bill)
        # `partition_maintenance` creates the current month and the ones ahead,
        # which is right for a running system and wrong for a seed: this estate
        # reaches two months back, and those partitions will never be created by
        # looking forward. The collector refuses a row with nowhere to go rather
        # than misfiling it, per constraint 11, so the seed says explicitly
        # which months it is about to write.
        for period in sorted({row.billing_period_start for row in bill}):
            ensure_partition(connection, "cost_focus_daily", period)
            ensure_partition(connection, "cost_provider_extra", period)

        for period in sorted({row.billing_period_start for row in bill}):
            month = tuple(row for row in bill if row.billing_period_start == period)
            written += _through_the_ledger(
                ledger,
                CostFocusCollector(FakeCostExport(rows=month, split=True), clock=lambda: now),
                connection,
                unit(scope_key=f"billing:{period:%Y-%m}"),
                "cost_focus",
            )
        # After the cost rows and not before, because the detector reads
        # `cost_focus_daily` and has nothing to judge until they are there. It judges
        # the most recent day with data, which is the day the estate put wrong, so a
        # single run is enough to give the anomalies screen its finding. TASK-P1-019.
        written += _through_the_ledger(
            ledger,
            CostAnomalyCollector(clock=lambda: now),
            connection,
            unit(),
            "cost_anomaly",
            settings=settings,
        )
        # Commitments come from a different API on a different cadence, so they are
        # their own collector and their own ledger entry. The fake sizes them against
        # the estate above, which is why they are seeded after it rather than beside
        # it: a coverage percentage here and a service total on the spend screen are
        # two views of one number.
        written += _through_the_ledger(
            ledger,
            CommitmentCollector(FakeCommitmentReport(at=now), clock=lambda: now),
            connection,
            unit(scope_key="billing:commitments"),
            "commitment",
        )
        # FEAT-060. Four budgets, two of which this product cannot join, because the first
        # thing a finance reader asks is how many of their budgets can actually be tracked and
        # a seed where everything joined would leave that answer rendered by nothing.
        written += _through_the_ledger(
            ledger,
            BudgetCollector(FakeBudgets(), clock=lambda: now),
            connection,
            unit(scope_key="billing:budgets"),
            "budgets",
        )
        # FEAT-076. Built from the same bill the cost rows were, so the invoices match those rows
        # by construction except where the fake says otherwise: one period matches, one is
        # 2.50 over with a Marketplace invoice beside it, and the running month is open.
        written += _through_the_ledger(
            ledger,
            InvoiceCollector(FakeInvoices(rows=bill), clock=lambda: now),
            connection,
            unit(scope_key="billing:invoices"),
            "invoices",
        )
        # FEAT-071. EC2's prices in the estate's Regions, from the fake whose on demand rates are
        # the estate's own monthly figures, so a rightsizing saving quoted from them is the
        # difference in the bill the estate generates. The fake holds no other service, so the
        # other four are read as having no versions rather than as failing.
        written += _through_the_ledger(
            ledger,
            PriceCatalogCollector(FakePriceCatalog(), clock=lambda: now),
            connection,
            unit(scope_key="catalog:prices"),
            "price_catalog",
        )
        # FEAT-072, after the prices it places EC2's types by: every type the estate prices,
        # described in the first Region and stored in each Region the fake sells it in.
        written += _through_the_ledger(
            ledger,
            InstanceCatalogCollector(
                FakeInstanceCatalog(), hub_region=shape.REGIONS[0], clock=lambda: now
            ),
            connection,
            unit(scope_key="catalog:instances"),
            "instance_catalog",
        )
        # FEAT-071, TASK-P9-012. The Savings Plans rates for every Region the prices are held for.
        written += _through_the_ledger(
            ledger,
            SavingsPlanRatesCollector(FakeSavingsPlansRates(), clock=lambda: now),
            connection,
            unit(scope_key="catalog:savings-plans"),
            "savings_plan_rates",
        )
        # FEAT-071, TASK-P9-013. Spot prices for the same Regions: the latest and today's range.
        written += _through_the_ledger(
            ledger,
            SpotPricesCollector(FakeSpotPrices(), clock=lambda: now),
            connection,
            unit(scope_key="catalog:spot"),
            "spot_prices",
        )
        # FEAT-055, immediately after the coverage it reads. Turning the gaps into findings in
        # the same seed run is what makes the commitments screen show the actions rather than
        # only the chart, and ordering matters: seeded before the coverage it would read an
        # empty table and write nothing while reporting success.
        written += _through_the_ledger(
            ledger,
            CommitmentActionsCollector(clock=lambda: now),
            connection,
            unit(scope_key="billing:commitments"),
            "commitment_actions",
            settings=settings,
        )
        written += _through_the_ledger(
            ledger,
            QueryAuditCollector(
                # The dashboards as they stood on the day being seeded. A
                # modelled cost is computed from the definition, so this is the
                # only thing that can move one.
                FakeQuerySurface(queries=queries_as_of(days_ago)),
                rates_from(settings),
                default_ingest_rate(settings),
                clock=lambda: now,
                # With evidence, so the demo estate shows a measured finding
                # beside a modelled one. Telling those apart is what the screens
                # are for, and an estate where every figure is modelled cannot
                # demonstrate it.
                evidence=FakeQueryEvidence(parser, days_ago=days_ago),
            ),
            connection,
            unit(),
            "query_audit",
        )

        # P3. The recommendations first, then the finished work and the bill it
        # left behind, then the collector that judges it. In that order because
        # each step reads what the one before it wrote, and a verification run
        # before the charges exist would find nothing and say so correctly.
        written += _through_the_ledger(
            ledger,
            RecommendationCollector(FakeRecommendationSource(), clock=lambda: now),
            connection,
            unit(),
            "recommendations",
        )
        # Our own findings, from the utilization estate rather than from seven flat
        # shapes, so a demo shows a percentile over two years of hourly behaviour and
        # the false positives the estate plants are refused for the reasons it gives.
        #
        # Once per account, and that matters twice over. The score counts an account
        # as judged by finding a successful waste run whose scope key names it, so a
        # single global run would leave every account unscored but one. And a run per
        # account is what the dispatcher actually does, so seeding it any other way
        # would be a demo of an arrangement that does not exist.
        instances = ec2_candidates(at=ESTATE_AT)
        volumes = volume_candidates(at=ESTATE_AT)
        # Every account with something to judge, instances or attached volumes. An account
        # holding only volumes, as fake-platform-b does, was skipped until TASK-P9-011 found its
        # planted gp2 volume never priced in the demo.
        for judged in sorted({c.account_id for c in instances} | {v.account_id for v in volumes}):
            attached = [VolumeCandidate(**asdict(v)) for v in volumes if v.account_id == judged]
            chosen = [
                Candidate(
                    resource_id=c.resource_id,
                    account_id=c.account_id,
                    region_id=c.region_id,
                    observation_days=c.observation_days,
                    monthly_cost=c.monthly_cost,
                    credit_balance=c.credit_balance,
                    instance_type=c.instance_type,
                )
                for c in instances
                if c.account_id == judged
            ]
            region = chosen[0].region_id if chosen else attached[0].region_id
            written += _through_the_ledger(
                ledger,
                WasteComputeCollector(
                    EstateMetrics(at=ESTATE_AT),
                    _always(chosen),
                    clock=lambda: ESTATE_AT,
                    # The account's attached volumes, so the planted gp2 one is priced as gp3
                    # in the same run as its instances, TASK-P9-009.
                    volumes=_always(attached),
                ),
                connection,
                unit(scope_key=f"aws:{judged}:{region}"),
                "waste_compute",
                settings=settings,
            )
        # FEAT-054. The development box in the fake estate is busy in business hours and
        # idles at about two percent outside them, so a parking window is there to be found.
        # Seeded from the same estate and the same clock as the rightsizing findings, because
        # two collectors disagreeing about what a fortnight looked like would be worse than
        # either of them being absent.
        #
        # `storage_monthly_cost` is None on purpose. The candidate record does not carry the
        # volume cost, and inventing one would put a number in a rationale that nobody could
        # reconcile against the bill. The finding says it is not known, which is true.
        # Once per account, for the same two reasons the rightsizing loop above gives: the
        # score counts an account as judged by finding a run whose scope key names it, and a
        # run per account is what the dispatcher actually does. The first draft filtered to
        # DEMO_ACCOUNT, which holds no EC2 candidates at all, so the collector was handed an
        # empty list and the guard below skipped it in silence.
        for parked in sorted({c.account_id for c in ec2_candidates(at=ESTATE_AT)}):
            parkable = [
                Parkable(
                    account_id=c.account_id,
                    region_id=c.region_id,
                    resource_id=c.resource_id,
                    # Compute only, from the monthly figure over the hours in a month. The
                    # storage share is excluded here and named as not known in the finding,
                    # because the candidate record does not carry the volume cost and a
                    # number invented for a rationale is one nobody can reconcile.
                    hourly_rate=(c.monthly_cost / Decimal("730")).quantize(Decimal("0.0001")),
                    storage_monthly_cost=None,
                )
                for c in ec2_candidates(at=ESTATE_AT)
                if c.account_id == parked
            ]
            written += _through_the_ledger(
                ledger,
                WasteParkingCollector(
                    EstateMetrics(at=ESTATE_AT),
                    _always(parkable),
                    clock=lambda: ESTATE_AT,
                ),
                connection,
                unit(scope_key=f"aws:{parked}:{parkable[0].region_id}"),
                "waste_parking",
                settings=settings,
            )
        written += _through_the_ledger(
            ledger,
            WasteCloudWatchCollector(FakeCloudWatchEstate(), clock=lambda: now),
            connection,
            unit(scope_key=f"aws:{DEMO_ACCOUNT}:{DEMO_REGION}"),
            "waste_cloudwatch",
            settings=settings,
        )
        _completed_work(connection, now)
        written += _through_the_ledger(
            ledger,
            RealizedSavingsCollector(clock=lambda: now),
            connection,
            unit(),
            "realized_savings",
        )
        # The score last, because it reads every one of the above. An account
        # counts as judged only where a waste collector reached it, so the seeded
        # estate deliberately scores some accounts and leaves the rest with no
        # number rather than a bad one, which is the distinction the screen shows.
        written += _through_the_ledger(
            ledger,
            ScoreCollector(clock=lambda: now),
            connection,
            unit(),
            "finops_score",
        )

        # P4. The graph, and one slice deliberately left unread.
        #
        # `covers` is nineteen of the twenty slices the source enrols, so the twentieth
        # keeps its UNREAD row. That is not a trick to make the screen interesting: it is
        # the state a dispatcher fanning out per account produces whenever one unit has not
        # run yet, and it is the one state a demo estate cannot show if every slice is
        # read. `docs/runbooks/demo.md` names which slice and why.
        source = FakeTopologySource()
        unread = (
            AccountKey(provider=Provider.AWS, account_id=UNREAD_ACCOUNT),
            UNREAD_REGION,
        )
        written += _through_the_ledger(
            ledger,
            InventoryCollector(
                source,
                clock=lambda: now,
                covers=tuple(one for one in source.enrolled_slices if one != unread),
            ),
            connection,
            unit(),
            "inventory",
        )

        # P11, FEAT-077. Owners from the nodes' tags, after the inventory because it reads them.
        # The demo names `owner` as a second key so the planted volume that carries only that
        # tag, in the account with no team tags, shows the case; a deployment names its own.
        written += _through_the_ledger(
            ledger,
            # And the fake AppRegistry, whose applications mark resources by tag, TASK-P11-003,
            # and the fake event history, which saw two of the unnamed resources made, P11-004.
            OwnershipCollector(
                clock=lambda: now,
                catalogue=FakeServiceCatalogue(),
                creators=FakeResourceCreators(),
            ),
            connection,
            unit(scope_key="ownership"),
            "ownership",
            settings=settings.model_copy(update={"owner_tag_keys": "team,owner"}),
        )
        # FEAT-078, TASK-P11-006. After the owners, because a credit names the team they
        # suggest, and after the verdicts above, because it credits only a VERIFIED one.
        written += _through_the_ledger(
            ledger,
            SavingsLedgerCollector(clock=lambda: now),
            connection,
            unit(scope_key="savings_ledger"),
            "savings_ledger",
        )

        # FEAT-057. Seeded after the inventory on purpose, because it joins to it: the
        # account on a resource_management row comes from the node the identifier matched,
        # so a run before the nodes exist places nothing and writes nothing while reporting
        # success. That is exactly what the first draft did, and the assertion in
        # tests/scripts/test_seed_demo.py is what caught it.
        #
        # The fake state owns three of the estate's resources and one of its three
        # backends refuses, so a local reader sees a managed resource, a not determined one, and
        # the sync_error row that says why Meter will not call any account unmanaged.
        #
        # The locations come from the fake rather than from settings, because the demo has no
        # real backend to name and a seed that read the configured locations would read nothing
        # and leave the whole feature invisible locally.
        written += _through_the_ledger(
            ledger,
            IacStateCollector(FakeTerraformState(), clock=lambda: now),
            connection,
            unit(scope_key="iac"),
            "iac_state",
            settings=settings.model_copy(
                update={"iac_state_locations": ",".join(FAKE_STATE_LOCATIONS)}
            ),
        )

        # FEAT-033 and FEAT-034, per slice because a quota is per account per region. The
        # estate carries 130 quotas of which roughly half can be measured, and that ratio is
        # the feature: a seed where every quota had a usage figure would leave the second
        # list, the one the whole sub project exists for, rendered by nothing anybody runs.
        # `fake-product-a` and `fake-product-b` carry no Business support, so the same quota
        # is measurable in one account and not in another, which is OPEN-03 as data.
        for account_id, region_id in quota_estate.SLICES:
            account_key = AccountKey(provider=Provider.AWS, account_id=account_id)
            written += _through_the_ledger(
                ledger,
                QuotaCollector(quota_estate.FakeQuotaSource(at=now), clock=lambda: now),
                connection,
                unit(
                    scope_key=f"{account_key}:{region_id}",
                    account=account_key,
                    region=region_id,
                ),
                "quotas",
            )

        # FEAT-035, FEAT-036 and FEAT-037, per account because a cluster lives in one.
        # After the bill and not before: the collector sizes each EC2 workload against
        # its measured split cost, and a workload with no cost yet is refused rather than
        # recommended. The estate is shaped to be unflattering. `batch-eks` publishes no
        # requests, so it is listed with its use, its cost and its reason and every one of
        # its workloads reads UNOBSERVED; `platform-eks` carries a workload that has been
        # killed for running out of memory and a namespace requesting five times its use;
        # `product-ecs` is Fargate, sized against the orderable matrix.
        for account_id in sorted({cluster.account_id for cluster in container_estate.CLUSTERS}):
            account_key = AccountKey(provider=Provider.AWS, account_id=account_id)
            written += _through_the_ledger(
                ledger,
                ContainerUsageCollector(
                    container_estate.FakeContainerSource(at=now), clock=lambda: now
                ),
                connection,
                unit(
                    scope_key=f"{account_key}:{fixtures.REGION}",
                    account=account_key,
                    region=fixtures.REGION,
                ),
                "container_usage",
            )

        written += _seed_ai(ledger, connection, unit, now)

        counts = {
            name: connection.execute(
                text(f"SELECT count(*) FROM {name} WHERE tenant_id = :t"), {"t": DEMO_TENANT}
            ).scalar_one()
            for name in ("grafana_instance", "cloud_account", "ingest_run")
        }

    return Seeded(
        rows=written,
        instances=int(counts["grafana_instance"]),
        accounts=int(counts["cloud_account"]),
        runs=int(counts["ingest_run"]),
    )


def remove(engine: Any) -> dict[str, int]:
    """Clear every demo row, in an order the foreign keys accept."""
    cleared: dict[str, int] = {}
    with engine.begin() as connection:
        for table_name in DEMO_TABLES:
            result = connection.execute(
                text(f"DELETE FROM {table_name} WHERE tenant_id = :t"),
                {"t": DEMO_TENANT},
            )
            cleared[table_name] = result.rowcount or 0
        result = connection.execute(
            text("DELETE FROM tenant WHERE tenant_id = :t"), {"t": DEMO_TENANT}
        )
        cleared["tenant"] = result.rowcount or 0
    return cleared


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed or clear the local demo estate.")
    parser.add_argument(
        "--remove",
        action="store_true",
        help="clear the demo estate instead of creating it",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=1,
        help=(
            "how many consecutive days to seed, ending today. One is the estate as it "
            "is now. More gives the audit a history, which is what a trend is drawn "
            "from: the collectors are run once per day at that day's clock, so the rows "
            "are the ones those runs would have written rather than invented ones"
        ),
    )
    args = parser.parse_args(argv)
    if args.days < 1:
        print("FAIL: --days must be at least 1", file=sys.stderr)
        return 2

    settings = load_settings()
    try:
        require_local(settings.database_url)
    except NotLocalError as refused:
        print(f"FAIL: {refused}", file=sys.stderr)
        return 2

    engine = create_engine(settings.database_url)
    try:
        if args.remove:
            for table_name, count in remove(engine).items():
                print(f"  cleared {count:>4} from {table_name}")
            print(f"Demo tenant {DEMO_TENANT} is gone.")
            return 0

        # Oldest first, so the newest run is the one that lands last and the
        # watermarks end where a reader expects them. Each pass writes that
        # day's rows through the same collectors, and the audit's upsert is
        # keyed on the day, so re running any of them changes nothing.
        today = datetime.now(UTC)
        for offset in range(args.days - 1, -1, -1):
            seeded = seed(engine, settings, today - timedelta(days=offset), latest=today)
        print(f"Seeded tenant {DEMO_TENANT}, {DEMO_NAME}.")
        print(f"  {seeded.accounts} accounts, {seeded.instances} workspaces")
        if args.days > 1:
            print(f"  {args.days} days of history, so a trend has something to draw")
        print(f"  {seeded.rows} rows across {seeded.runs} runs, written by the real collectors")
        print("  four role health states, one failed run, one unreadable workspace")
        print("")
        print("To see it, point the local identity at this tenant:")
        print(f"  METER_LOCAL_TENANT_ID={DEMO_TENANT}")
        print("Clear it with: make unseed")
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
