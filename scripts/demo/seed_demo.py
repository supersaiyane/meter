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
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from sqlalchemy import create_engine, text

from finops_core.config import load_settings
from finops_core.domain.account import AccountKey
from finops_core.errors import CollectionError
from finops_fakes import fixtures
from finops_fakes.cloudwatch_estate import FakeCloudWatchEstate
from finops_fakes.commitment import FakeCommitmentReport
from finops_fakes.cur import FakeCostExport, estate
from finops_fakes.evidence import FakeQueryEvidence
from finops_fakes.health import FakeRoleHealth
from finops_fakes.platform_cost import FakePlatformCost
from finops_fakes.provider import FakeProvider
from finops_fakes.recommendations import FakeRecommendationSource
from finops_fakes.surface import FakeQuerySurface, queries_as_of
from finops_fakes.waste import FakeWasteMetrics, instances
from finops_ingest.collectors.account_health import AccountHealthCollector
from finops_ingest.collectors.commitment import CommitmentCollector
from finops_ingest.collectors.cost_anomaly import CostAnomalyCollector
from finops_ingest.collectors.cost_focus import CostFocusCollector
from finops_ingest.collectors.org_tree import OrgTreeCollector
from finops_ingest.collectors.partitions import ensure_partition, partition_maintenance
from finops_ingest.collectors.platform_cost import PlatformCostCollector
from finops_ingest.collectors.query_audit import (
    QueryAuditCollector,
    default_ingest_rate,
    rates_from,
)
from finops_ingest.collectors.realized_savings import (
    MATURITY_DAYS,
    SETTLE_DAYS,
    WINDOW_DAYS,
    RealizedSavingsCollector,
)
from finops_ingest.collectors.recommendations import RecommendationCollector
from finops_ingest.collectors.score import ScoreCollector
from finops_ingest.collectors.waste_cloudwatch import WasteCloudWatchCollector
from finops_ingest.collectors.waste_compute import Candidate, WasteComputeCollector
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
    "ingest_run",
    "platform_cost",
    "org_node",
    "cloud_account",
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
    "realized_saving",
    "recommendation_event",
    "recommendation",
    # P1, FEAT-023. Derived from the daily rows, so it goes before them.
    "cost_anomaly",
    # P1, FEAT-024. Neither references the other, and both reference only the
    # tenant, so their order between themselves does not matter.
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


#: The account and region the seeded verifications sit in. Named rather than
#: repeated, because three functions read them and a typo in one would produce a
#: recommendation whose resource never joins to a charge.
DEMO_ACCOUNT = "fake-platform-a"
DEMO_REGION = "eu-west-1"

#: A day of instance hours. The control that makes a cost fall claimable or not.
D24 = Decimal("24")

#: Three changes somebody finished, and the shape of the bill afterwards.
#:
#: One per verdict, because a demo estate where every verification succeeds cannot
#: show what this product is for. The numbers are chosen so the real collector
#: reaches each verdict from the billing rows rather than being told the answer:
#:
#: - `i-verified` cost fell and usage held, so the resource is cheaper per unit
#: - `i-regressed` cost did not move, so whatever was done did not land
#: - `i-shrank` cost fell forty percent and usage fell seventy five, so the fall is
#:   explained by a smaller workload and cannot be claimed
COMPLETED: tuple[tuple[str, str, Decimal, Decimal, Decimal | None, Decimal | None], ...] = (
    ("i-verified", "RIGHTSIZE_INSTANCE", Decimal("12.00"), Decimal("7.00"), D24, D24),
    ("i-regressed", "IDLE_INSTANCE", Decimal("9.00"), Decimal("9.00"), D24, D24),
    ("i-shrank", "GRAVITON_CANDIDATE", Decimal("10.00"), Decimal("6.00"), D24, Decimal("6")),
)


def _completed_work(connection: Any, now: datetime) -> None:
    """Three finished recommendations and the bill that followed them.

    Written directly rather than driven through the routes, because the point of
    the fixture is the state of the bill sixty days later and walking four
    transitions per recommendation would make this a test of the lifecycle. The
    verdicts themselves are not written: `RealizedSavingsCollector` reads these
    rows and reaches them, which is what makes the demo screen show a real result
    rather than a staged one.
    """
    done_on = now.date() - timedelta(days=MATURITY_DAYS)
    done_at = datetime(done_on.year, done_on.month, done_on.day, 12, tzinfo=UTC)

    for resource, waste_class, before, after, usage_before, usage_after in COMPLETED:
        recommendation_id = uuid4()
        # Idempotent like every collector around it. `make seed` is run once per
        # day of history, and a second insert of the same finished work would
        # either fail on the unique constraint or double the verdicts.
        created = connection.execute(
            text(
                "INSERT INTO recommendation (recommendation_id, tenant_id, sub_account_id, "
                "source, source_reference, waste_class, resource_id, region_id, "
                "estimated_monthly_saving, confidence, severity, observation_days, "
                "lifecycle, owner, rationale, as_of, collected_at) "
                "VALUES (:id, :t, :a, 'METER', :ref, :class, :res, :region, :saving, 'HIGH', "
                "'MEDIUM', 30, 'DONE', 'platform@example.local', :why, :at, :at) "
                "ON CONFLICT (tenant_id, source, source_reference) DO NOTHING "
                "RETURNING recommendation_id"
            ),
            {
                "id": recommendation_id,
                "t": DEMO_TENANT,
                "a": DEMO_ACCOUNT,
                "ref": f"seed:{resource}",
                "class": waste_class,
                "res": resource,
                "region": DEMO_REGION,
                # Modelled, and deliberately larger than any of these actually
                # realized. The gap between this and the savings screen is what
                # the runbook stops on.
                "saving": (before - after) * Decimal("30") + Decimal("40"),
                "why": f"{resource} was judged over 30 days and the work was completed",
                "at": now,
            },
        ).first()
        if created is None:
            # Already seeded on an earlier day. The events and the charges went in
            # with it, so there is nothing to add.
            continue

        for target, occurred, previous in (
            ("OPEN", done_at - timedelta(days=7), None),
            ("ACCEPTED", done_at - timedelta(days=6), "OPEN"),
            ("IN_PROGRESS", done_at - timedelta(days=5), "ACCEPTED"),
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

        for offset in range(WINDOW_DAYS):
            _charge(
                connection,
                resource,
                done_on - timedelta(days=offset + 1),
                before,
                usage_before,
                now,
            )
            _charge(
                connection,
                resource,
                done_on + timedelta(days=SETTLE_DAYS + offset),
                after,
                usage_after,
                now,
            )


def _charge(
    connection: Any,
    resource: str,
    day: date,
    cost: Decimal,
    quantity: Decimal | None,
    now: datetime,
) -> None:
    """One day of charge for one resource, in its own partition.

    `quantity` of None leaves `consumed_quantity` null, which a real export does
    for the services that publish no usage figure. None of the three seeded
    changes uses it, so the demo's inconclusive verdict comes from usage falling
    faster than cost rather than from a missing control: both paths exist and the
    more interesting one is the one that had a control and still could not claim.
    """
    period = date(day.year, day.month, 1)
    ensure_partition(connection, "cost_focus_daily", period)
    start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    connection.execute(
        text(
            "INSERT INTO cost_focus_daily (tenant_id, ingest_run_id, source_fingerprint, "
            "as_of, collected_at, billing_account_id, sub_account_id, billing_period_start, "
            "billing_period_end, charge_period_start, charge_period_end, provider_name, "
            "service_name, resource_id, charge_category, billed_cost, effective_cost, "
            "consumed_quantity, tags) "
            "VALUES (:t, :run, :fp, :at, :at, 'fake-payer', :a, :period, :period_end, "
            ":start, :end, 'Fake', 'AmazonEC2', :res, 'Usage', :cost, :cost, :q, '{}'::jsonb) "
            "ON CONFLICT DO NOTHING"
        ),
        {
            "t": DEMO_TENANT,
            "run": uuid4(),
            "fp": f"seed:{resource}:{day}",
            "at": now,
            "a": DEMO_ACCOUNT,
            "period": period,
            "period_end": date(period.year + (period.month // 12), (period.month % 12) + 1, 1),
            "start": start,
            "end": start + timedelta(days=1),
            "res": resource,
            "cost": cost,
            "q": quantity,
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
        bill = estate(at=now)
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
                CostFocusCollector(FakeCostExport(rows=month), clock=lambda: now),
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
        # Our own findings, from the metrics the fake estate publishes. These two
        # runs are also what makes an account count as judged for the score: an
        # account no waste collector reached has no score rather than a bad one,
        # and an estate where nothing ran would show that state for everything.
        written += _through_the_ledger(
            ledger,
            WasteComputeCollector(
                FakeWasteMetrics(),
                lambda _context: [
                    Candidate(
                        resource_id=shape.instance_id,
                        account_id=DEMO_ACCOUNT,
                        region_id=DEMO_REGION,
                        observation_days=shape.days,
                        monthly_cost=shape.monthly_cost,
                        credit_balance=shape.credit_balance,
                    )
                    for shape in instances()
                ],
                clock=lambda: now,
            ),
            connection,
            unit(scope_key=f"aws:{DEMO_ACCOUNT}:{DEMO_REGION}"),
            "waste_compute",
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
