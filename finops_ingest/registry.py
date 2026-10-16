"""What a collector is, and the register of the ones that exist.

A collector is a name, the scope it runs at, and something callable. Keeping
the register separate from the things registered is what lets the dispatcher
enumerate work without importing every collector, and what lets a test run the
dispatcher against two lines of fake instead of against AWS.

Cadence is deliberately not here. Constraint 9 in CLAUDE.md and ADR-0012 put it
in the `collector_schedule` table with its reason and its cost, because a
cadence in code is a number nobody can change without a deploy and nobody can
explain a year later.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import text


class CollectorScope(StrEnum):
    """What one unit of this collector's work covers."""

    #: One account in one region. Needs an assumed session.
    ACCOUNT = "account"
    #: The whole organization, once. Runs on the hub's own credentials.
    ORGANIZATION = "organization"


@dataclass(frozen=True)
class CollectorOutcome:
    """What a collector did, for the run ledger to record."""

    items_written: int = 0
    bytes_read: int = 0
    #: Rows the collector removed because the provider withdrew them. Separate
    #: from `items_written`, because a retraction is not a write, and counted at
    #: all because a destructive operation nobody can see is one nobody notices
    #: going wrong. P1, FEAT-020.
    items_removed: int = 0


@dataclass(frozen=True)
class CollectorContext:
    """Everything a collector is given, and nothing it is not.

    The connection is the worker's own transaction for this one unit. A
    collector writing through it inherits the guarantee that its work commits or
    rolls back with the run record, and a collector cannot open a second
    transaction and leave the two disagreeing.

    `unit` is typed loosely on purpose: `WorkUnit` lives in the dispatcher, and
    the dispatcher already imports this module.
    """

    unit: Any
    connection: Any
    #: The assumed session for account scoped work. None for organization scope,
    #: which runs on the hub's own credentials.
    session: Any = None
    #: Runtime configuration. On the context rather than on the unit, because a
    #: unit is a message that outlives the process that wrote it and settings
    #: are whatever the worker running it was started with.
    settings: Any = None
    #: The run this work belongs to, from the ledger's claim. Cost rows carry it
    #: in a NOT NULL column and P1's restatement delete keys on it, so a
    #: collector generating its own would be writing a number that names no run
    #: and deleting on a fiction. Defaulted so every existing collector and
    #: every existing test constructs a context exactly as it did before.
    run_id: Any = None


#: A collector receives one context and reports what it did.
CollectorRunner = Callable[[CollectorContext], CollectorOutcome]


@dataclass(frozen=True)
class Collector:
    name: str
    scope: CollectorScope
    run: CollectorRunner


@dataclass(frozen=True)
class ScheduleEntry:
    """One collector's cadence, with the reason it is that number.

    ADR-0012 and constraint 9: cadence is data, not code. `reason` is NOT NULL
    in the table because a cadence nobody can explain is a number nobody can
    safely change, and the first thing anyone does with an unexplained interval
    under cost pressure is double it.
    """

    collector: str
    cadence_seconds: int
    reason: str
    est_cost_per_run: str
    #: Which process runs it, 0029 and ADR-0033. The worker runs the collectors; the API runs
    #: the scheduled reports, because they render through its routes and nothing below it may
    #: import them.
    runs_in: str = "worker"


#: P8, FEAT-069. How often the API looks for scheduled reports that are due.
FIFTEEN_MINUTES = 900
#: P15, FEAT-092. How often the code host collector opens, follows and merges fixes.
TEN_MINUTES = 600
HOURLY = 3600
#: Six hours. The interval the P2 specification asks for, named rather than
#: written as a multiplication at the call site.
SIX_HOURLY = 21600
#: Eight hours, the interval the P9 specification's section 14.4 asks the catalog collectors for.
EIGHT_HOURLY = 28800
#: Twelve hours, the interval the P5 specification's section 7 asks for.
TWELVE_HOURLY = 43200
DAILY = 86400
#: Seven days, the interval a weekly digest is composed at, P7 spec section 7.
WEEKLY = 604800
#: Thirty days. The cost roll up is not calendar aware and does not need to be:
#: it aggregates everything past a cutoff, so running a day early or a day late
#: changes nothing except how many line items are left over until next time.
MONTHLY = 2592000

#: What a new tenant starts with. Installed at onboarding rather than in a
#: migration, because the table is keyed by tenant and a migration knows none.
DEFAULT_SCHEDULE: tuple[ScheduleEntry, ...] = (
    ScheduleEntry(
        collector="org_tree",
        cadence_seconds=HOURLY,
        reason=(
            "A new account has to appear within one hour with no human step, which is "
            "the P0 definition of done for onboarding. Faster buys nothing, because "
            "accounts are created by people and not by autoscaling."
        ),
        est_cost_per_run="0",
    ),
    ScheduleEntry(
        collector="account_health",
        cadence_seconds=HOURLY,
        reason=(
            "A broken collector role is invisible until something tries to read the "
            "account, so the check runs as often as the tree it belongs to. The calls "
            "are free, and the alternative is finding out from a missing number."
        ),
        est_cost_per_run="0",
    ),
    ScheduleEntry(
        collector="query_audit",
        cadence_seconds=SIX_HOURLY,
        reason=(
            "A dashboard is edited by a person, so the population changes on a human "
            "timescale rather than a machine one. Six hours catches a bad panel within "
            "one working day, which is fast enough to matter and slow enough that the "
            "survey itself is not the thing being audited: every run reads every "
            "dashboard in every workspace, and the Grafana API is the cost."
        ),
        est_cost_per_run="0",
    ),
    ScheduleEntry(
        collector="platform_cost",
        cadence_seconds=DAILY,
        reason=(
            "Cost Explorer charges per request, so the cadence is itself a cost "
            "decision. Daily is the granularity the data has, and running hourly "
            "would pay twenty four times over for a figure that changes once."
        ),
        # The published per request price at the time of writing. Modelled, not
        # measured: the real figure arrives in the next day's own report, which
        # is the point of metering ourselves.
        est_cost_per_run="0.01",
    ),
    ScheduleEntry(
        collector="retention_principal",
        cadence_seconds=DAILY,
        reason=(
            "The retention window is stated in days, so checking it more than once "
            "a day cannot make the promise more true. Daily is also what makes a "
            "stopped retention job visible on the freshness screen within a day."
        ),
        est_cost_per_run="0",
    ),
    ScheduleEntry(
        collector="retention_operational",
        cadence_seconds=DAILY,
        reason=(
            "Run history is the largest table by row count and the least valuable "
            "row for row. Daily keeps the deletion small enough to stay inside one "
            "transaction, which a weekly cadence would not."
        ),
        est_cost_per_run="0",
    ),
    ScheduleEntry(
        collector="retention_assistant",
        cadence_seconds=DAILY,
        reason=(
            "A person's questions to the assistant are kept 90 days, OPEN-14. Daily, so a "
            "question leaves within a day of its window rather than within a week."
        ),
        est_cost_per_run="0",
    ),
    ScheduleEntry(
        collector="retention_ai_usage",
        cadence_seconds=DAILY,
        reason=(
            "Tokens and requests per caller are kept 13 months, P13 spec section 6, because a "
            "caller can name a person. Daily, so a day's usage leaves within a day of its window."
        ),
        est_cost_per_run="0",
    ),
    # TASK-P16-007. Migration 0067 installs the same row for every tenant before it.
    ScheduleEntry(
        collector="retention_plans",
        cadence_seconds=DAILY,
        reason=(
            "Plans, their estimates, comments and comparisons are kept 400 days, P16 spec section "
            "6: the comparison needs sixty days after a merge, and a year of accuracy is what is "
            "published. Daily, so a plan leaves within a day of its window."
        ),
        est_cost_per_run="0",
    ),
    ScheduleEntry(
        collector="retention_audit",
        cadence_seconds=DAILY,
        reason=(
            "Thirteen months is a regulatory floor rather than a preference, so the "
            "job runs on the same daily cadence as the rest and is never the thing "
            "that made the window drift."
        ),
        est_cost_per_run="0",
    ),
    ScheduleEntry(
        collector="retention_cost",
        cadence_seconds=MONTHLY,
        reason=(
            "Aggregating three year old line items is expensive and the answer does "
            "not change between runs, because nothing new becomes three years old "
            "inside a day. Monthly is the cheapest cadence that still bounds the "
            "table's growth."
        ),
        est_cost_per_run="0",
    ),
    ScheduleEntry(
        collector="cost_focus",
        cadence_seconds=SIX_HOURLY,
        reason=(
            "The open billing period changes continuously, so a figure on the cost "
            "screen is out of date the moment it is written and the only question is "
            "by how much. Four times a day bounds that at six hours, which is inside "
            "the window anybody reconciling against an invoice cares about. Faster "
            "costs real money: each run is one Athena query per period, charged on "
            "bytes scanned, and the tool that reports on cost paying to watch itself "
            "more closely is the wrong trade."
        ),
        est_cost_per_run="0.02",
    ),
    ScheduleEntry(
        collector="partition_maintenance",
        cadence_seconds=DAILY,
        reason=(
            "Partitions are created months ahead, so this could run weekly and still "
            "be correct. It runs daily because a stopped job is then visible within a "
            "day on the freshness screen, and the failure it prevents is every cost "
            "insert failing at midnight on the first of a month."
        ),
        est_cost_per_run="0",
    ),
    ScheduleEntry(
        collector="retention_scope_cache",
        cadence_seconds=HOURLY,
        reason=(
            "An expired entitlement row is already ignored by the reader, so this is "
            "housekeeping and not enforcement. Hourly keeps the table small without "
            "anyone having to think about it."
        ),
        est_cost_per_run="0",
    ),
    # P1. Both of these were written without an entry here, which meant
    # `due_collectors` never returned them and neither ever ran on cadence. Their
    # tests call them directly, so nothing noticed. ISS-190, and the test in
    # `tests/ingest/test_registry.py` derives this list from the source so a sixth
    # cannot happen.
    ScheduleEntry(
        collector="cost_anomaly",
        cadence_seconds=DAILY,
        reason=(
            "It judges the most recent day that has data, and a day gets its data "
            "once. Running more often re reaches the same verdict about the same day "
            "and risks rewriting one somebody has already acted on. It reads rows "
            "already in the database, so the cadence costs nothing and the only thing "
            "a slower one buys is a later warning."
        ),
        est_cost_per_run="0",
    ),
    ScheduleEntry(
        collector="commitment",
        cadence_seconds=DAILY,
        reason=(
            "AWS reports utilization and coverage per day, so an hourly read would "
            "return the same figures and pay Cost Explorer for each one. Daily is the "
            "grain the source actually has. Each run makes eight Cost Explorer requests "
            "at a cent each: four over the month, and four for the last month of days "
            "at the daily grain, TASK-P8-013."
        ),
        est_cost_per_run="0.08",
    ),
    # P3.
    ScheduleEntry(
        collector="recommendations",
        cadence_seconds=DAILY,
        reason=(
            "Compute Optimizer and Cost Optimization Hub refresh at most daily, and "
            "Trusted Advisor less often than that. A faster cadence re reads an "
            "unchanged answer, and the withdrawal pass means each read can retract "
            "findings, so running it more often than the source changes would churn a "
            "list people are working from."
        ),
        est_cost_per_run="0",
    ),
    ScheduleEntry(
        collector="waste_compute",
        cadence_seconds=SIX_HOURLY,
        reason=(
            "Six hours because the P3 specification section 7 says so for the bespoke "
            "collectors. It is the most expensive cadence in this schedule and the "
            "trade is worth stating: GetMetricData is charged per metric requested, the "
            "batched read asks for four metrics per instance over fourteen days, and "
            "the sizing rules barely move between mornings, so four runs a day pay four "
            "times to restate the same percentile. Daily would be the cheaper number "
            "and ADR-0012 is why it is a row rather than a constant. ISS-194."
        ),
        est_cost_per_run="0.05",
    ),
    ScheduleEntry(
        collector="waste_cloudwatch",
        cadence_seconds=SIX_HOURLY,
        reason=(
            "Six hours, with the other bespoke collector, per P3 specification section "
            "7. Retention settings and alarm definitions are configuration rather than "
            "measurements, and the describe calls are free, so nothing here is paying "
            "for the interval."
        ),
        est_cost_per_run="0",
    ),
    ScheduleEntry(
        collector="budgets",
        cadence_seconds=DAILY,
        reason=(
            "Daily, because a budget is a decision somebody made and decisions are not made "
            "hourly. The status a screen shows moves every day on its own, since it is spend "
            "against where the calendar has got to, and that recomputes per request from the "
            "stored limit: reading the provider more often would not move it. The call is one "
            "DescribeBudgets at the payer and costs nothing. ADR-0012 and constraint 9."
        ),
        est_cost_per_run="0",
    ),
    ScheduleEntry(
        collector="invoices",
        cadence_seconds=DAILY,
        reason=(
            "Daily, because AWS issues an invoice once a month and a credit memo rarely, so a "
            "daily read finds each within a day of its issue. A run is one ListInvoiceSummaries "
            "per billing period at the payer, modelled at no cost until a real bill shows "
            "otherwise. ADR-0012, constraint 9 and FEAT-076."
        ),
        est_cost_per_run="0",
    ),
    # FEAT-071, TASK-P9-004. Migration 0034 installs the same row for every tenant before it.
    ScheduleEntry(
        collector="price_catalog",
        cadence_seconds=EIGHT_HOURLY,
        reason=(
            "Every 8 hours, P9 specification section 14.4. A run asks each of five services for "
            "its current price list version in every Region and loads only a version it does not "
            "hold, so a run that finds nothing new is five ListPriceLists calls and writes "
            "nothing, and a faster cadence would only repeat them. A version AWS publishes is "
            "loaded within 8 hours, so a saving is never quoted from superseded prices for longer "
            "than that. The Price List API makes no charge; a load costs the hub's endpoint "
            "processing its pages at 0.01 USD a GB, AWS's published rate, and a full load of all "
            "five services in every Region is modelled at under one GB, so the figure below "
            "bounds a full load and a quiet run costs nothing. ADR-0012, ADR-0035, constraint 9 "
            "and FEAT-071."
        ),
        est_cost_per_run="0.01",
    ),
    # FEAT-072, TASK-P9-005. Migration 0035 installs the same row for every tenant before it.
    ScheduleEntry(
        collector="instance_catalog",
        cadence_seconds=EIGHT_HOURLY,
        reason=(
            "Every 8 hours, P9 specification section 14.4, beside the price catalog whose "
            "Regions it places EC2's types in. A run is one DescribeInstanceTypes in the hub's "
            "Region, one in the Region it is compared with, and GetProducts only for a managed "
            "service whose price list changed since its classes were read, so a faster cadence "
            "would read the same descriptions again. A type AWS starts selling is described "
            "within 8 hours of being priced. Neither API makes a charge; the cost is the hub's "
            "endpoints processing the pages, modelled at a tenth of a cent a run. ADR-0012, "
            "ADR-0035, constraint 9 and FEAT-072."
        ),
        est_cost_per_run="0.001",
    ),
    # FEAT-071, TASK-P9-012. Migration 0036 installs the same row for every tenant before it.
    ScheduleEntry(
        collector="savings_plan_rates",
        cadence_seconds=EIGHT_HOURLY,
        reason=(
            "Every 8 hours, with the other catalog collectors, P9 specification section 14.4. "
            "Savings Plans rates carry no published version, so every Region is read each run "
            "and a Region whose rates have not moved is stored as nothing. A run is six relay "
            "calls a Region, one per plan type and payment option, so no answer outgrows the "
            "relay; about 180 calls a run across 30 Regions (modelled), inside the Lambda free "
            "allowance, and an S3 write each at 0.005 USD a thousand, AWS's published rate. "
            "ADR-0012, ADR-0035, constraint 9, FEAT-071 and OPEN-19."
        ),
        est_cost_per_run="0.001",
    ),
    # FEAT-071, TASK-P9-013. Migration 0037 installs the same row for every tenant before it.
    ScheduleEntry(
        collector="spot_prices",
        cadence_seconds=EIGHT_HOURLY,
        reason=(
            "Every 8 hours, with the other catalog collectors, P9 specification section 14.4. "
            "Each run reads every Region's window since its last read, one relay call a Region "
            "because DescribeSpotPriceHistory pages with botocore's own paginator: about 2,700 "
            "calls a month across 30 Regions (modelled), the figure spec section 14.5 gave, "
            "inside the Lambda free allowance and an S3 write each at 0.005 USD a thousand, "
            "AWS's published rate. Spot moves within hours, so a slower cadence would miss the "
            "daily low and high OPEN-18 keeps, and a faster one would only repeat the same "
            "prices. ADR-0012, ADR-0035, constraint 9, FEAT-071 and OPEN-18."
        ),
        est_cost_per_run="0.0002",
    ),
    ScheduleEntry(
        collector="iac_state",
        cadence_seconds=DAILY,
        reason=(
            "Daily, and the number is about how often the thing being read changes rather than "
            "about cost. State changes when somebody applies, which is many times a day in an "
            "active estate and never in a quiet one, and neither pattern is worth reading "
            "hourly: the address of a resource that has not moved is the same address. The read "
            "itself is a handful of S3 GETs, so this is nearly free, which is exactly why a "
            "faster cadence would be tempting and still pointless. Nothing is locked, because a "
            "Terraform state lock blocks whoever is mid apply and a tool that can stall a "
            "deployment is not read only in the sense the person on call cares about. ADR-0012 "
            "and constraint 9."
        ),
        est_cost_per_run="0",
    ),
    ScheduleEntry(
        collector="commitment_actions",
        cadence_seconds=DAILY,
        reason=(
            "Daily, following the commitment collector it reads rather than choosing an "
            "interval of its own. It makes no provider call at all: everything it needs is "
            "in commitment_coverage, which FEAT-019 writes from the bill, so this is the one "
            "collector in the schedule whose cost per run is genuinely zero rather than "
            "rounded to it. A faster cadence would restate the same coverage window, because "
            "the window only moves when the bill does. ADR-0012 and constraint 9."
        ),
        est_cost_per_run="0",
    ),
    ScheduleEntry(
        collector="waste_parking",
        cadence_seconds=DAILY,
        reason=(
            "Daily, not six hourly with the other two bespoke collectors, and the reason is "
            "the shape of the thing being measured. A parking window is a property of a "
            "fortnight folded into a week, so four runs a day would fold almost exactly the "
            "same fortnight four times and restate the same window. The read is also the "
            "most expensive in the schedule per run: one metric per resource at hourly "
            "resolution over fourteen days is 336 data points each, and GetMetricData is "
            "charged per metric requested. Daily is the cadence at which the answer can "
            "actually change, because it takes a new day of readings to move a window. "
            "ADR-0012 and constraint 9 are why this is a row with a reason rather than a "
            "constant somebody would later have to guess at."
        ),
        est_cost_per_run="0.02",
    ),
    ScheduleEntry(
        collector="inventory",
        cadence_seconds=DAILY,
        reason=(
            "The graph and its coverage, from the Config aggregator plus the four APIs "
            "Config does not cover. Daily, and it is the floor rather than a comfortable "
            "choice. FEAT-044 asks about a change somebody made this morning, so a day "
            "old graph answers about yesterday's estate, which argues for six hourly. "
            "Against that: five calls per slice, so three hundred accounts across eleven "
            "regions is about sixteen thousand calls a run, and four runs a day is where "
            "the throttle rather than the price becomes the constraint. The calls "
            "themselves are free, which is why the estimate below is nought: the money in "
            "FEAT-030 is the Config recorder, which charges per configuration item "
            "recorded and runs continuously whatever this cadence says. ADR-0012 makes "
            "this a row so the argument can be settled with a number from a real estate "
            "rather than from this paragraph."
        ),
        est_cost_per_run="0",
    ),
    ScheduleEntry(
        collector="finops_score",
        cadence_seconds=SIX_HOURLY,
        reason=(
            "The interval FEAT-043 asks for, and it reads rows already in the database, "
            "so it costs nothing. Six hours is short enough that a team sees its own "
            "score move on the day it closes something, which is the only reason a "
            "posture number changes anybody's behaviour."
        ),
        est_cost_per_run="0",
    ),
    ScheduleEntry(
        collector="realized_savings",
        cadence_seconds=DAILY,
        reason=(
            "A verdict is only reachable sixty days after the change was done, so "
            "nothing here is urgent. Daily means a recommendation is judged on the "
            "first day its after window is complete rather than up to a week later, "
            "and it reads rows already in the database, so that costs nothing."
        ),
        est_cost_per_run="0",
    ),
    ScheduleEntry(
        collector="anthropic_usage",
        cadence_seconds=DAILY,
        reason=(
            "Anthropic's cost and usage for each connected organization, P13 spec section 5.5. "
            "Daily, rereading the billing period to date: the cost report is in daily buckets "
            "and recent ones are revised, so reading more often adds nothing and reading less "
            "often leaves the month's figure behind the bill. The Admin API's reports are not "
            "billed, so a run costs the NAT gateway's per GB charge on a few kilobytes. ADR-0012 "
            "and constraint 9."
        ),
        est_cost_per_run="0",
    ),
    ScheduleEntry(
        collector="openai_usage",
        cadence_seconds=DAILY,
        reason=(
            "OpenAI's cost and usage for each connected organization, P13 spec section 5.5. "
            "Daily, rereading the billing period to date: the reports are in daily buckets and "
            "OpenAI revises recent ones, so reading more often adds nothing and reading less "
            "often leaves the month's figure behind the bill. The reports are not billed, so a "
            "run costs the NAT gateway's per GB charge on a few kilobytes. ADR-0012 and "
            "constraint 9."
        ),
        est_cost_per_run="0",
    ),
    ScheduleEntry(
        collector="gpu_utilization",
        cadence_seconds=DAILY,
        reason=(
            "How busy each GPU instance's accelerators were, P13 spec section 5.6. Daily, for the "
            "day before: the table holds a day's average and peak, so reading more often reads "
            "the same day again. The cost is GetMetricData's, USD 0.01 per 1,000 metrics at the "
            "list price, three a day for each accelerator of each GPU instance the bill names: "
            "modelled at 0.001 USD a run for one instance of eight accelerators, and not measured "
            "until an account is read, ISS-002. ADR-0012 and constraint 9."
        ),
        est_cost_per_run="0.001",
    ),
    ScheduleEntry(
        collector="commitment_inventory",
        cadence_seconds=DAILY,
        reason=(
            "What each member account holds, P14 spec section 5.3. Daily: a commitment's term, "
            "end and state change at most once a day, and the calendar counts months. Savings "
            "Plans and RDS reservations come through the relay, ADR-0037, EC2 reservations "
            "through its endpoint, as each account's collector role: modelled at about 0.00001 "
            "USD a run in Lambda and S3 requests, and not measured until an account is read, "
            "ISS-002. ADR-0012 and constraint 9."
        ),
        est_cost_per_run="0.00001",
    ),
    ScheduleEntry(
        collector="purchase_recommendation",
        cadence_seconds=DAILY,
        reason=(
            "AWS's purchase recommendations, P14 spec section 5.1. Daily: Cost Explorer refreshes "
            "them at least once a day, and a plan is drafted against them daily. Eight requests a "
            "run, two Savings Plans types and six reserved services, at USD 0.01 each at AWS's "
            "published price: modelled at 0.08 USD a run, and not measured until a payer is read, "
            "ISS-002. ADR-0012 and constraint 9."
        ),
        est_cost_per_run="0.08",
    ),
    ScheduleEntry(
        collector="purchase_plan",
        cadence_seconds=DAILY,
        reason=(
            "Meter's own purchase plan, P14 spec section 5.6. Daily, after the bill, the "
            "inventory and P9's rates it reads: it drafts this month's plan, redrafts a plan "
            "nobody has approved yet, and lapses a draft from an earlier month. It reads only "
            "Meter's own tables, so its cost per run is zero. ADR-0012 and constraint 9."
        ),
        est_cost_per_run="0",
    ),
    ScheduleEntry(
        collector="bedrock_invocations",
        cadence_seconds=DAILY,
        reason=(
            "Who called which Bedrock model, from the invocation logs, P13 spec section 5.4. "
            "Daily, for the day before: the logs are complete for a day once it has ended, a "
            "cost per caller is modelled from the bill, which is itself daily, and reading more "
            "often would scan the same log events again. The cost is the bytes Logs Insights "
            "scans in the member account, USD 0.005 per GB at the list price, and the logs hold "
            "every prompt and response, so a busy account's day can be gigabytes: modelled at two "
            "GB a run, 0.01 USD, and not measured until an account is read, ISS-002. ADR-0012 "
            "and constraint 9."
        ),
        est_cost_per_run="0.01",
    ),
    ScheduleEntry(
        collector="container_usage",
        cadence_seconds=TWELVE_HOURLY,
        reason=(
            "A request is a number somebody sets in a manifest, so it changes when "
            "somebody deploys rather than continuously. Use moves all day, but the "
            "figures this reads are a 99th percentile and a peak over a fortnight, "
            "and neither moves much between one reading and the next. Twice a day "
            "keeps the comparison current without paying for precision nobody can "
            "act on: below fourteen days of history there is no recommendation at "
            "all, so reading faster cannot produce one sooner. The cost is call "
            "count rather than dollars, GetMetricData being charged per metric "
            "requested, and a cluster of four hundred pods is four hundred metrics "
            "a run even batched at five hundred a call. ADR-0012 and constraint 9."
        ),
        est_cost_per_run="0.01",
    ),
    ScheduleEntry(
        collector="quotas",
        cadence_seconds=TWELVE_HOURLY,
        reason=(
            "Twelve hours, per P5 specification section 7. A quota moves when somebody "
            "raises it, which is rare, and usage against it is read as a peak over the "
            "preceding day, so a faster cadence would re read the same window and report "
            "the same number. The reason to go no slower is the opposite of cost: this is "
            "the one signal in the product that is not about money but about the wall an "
            "estate hits at three in the morning, and a day old reading of a quota filling "
            "up is a fortnight of warning turned into an afternoon of it. The call count is "
            "the real constraint: one ListServices, then one ListServiceQuotas per service, "
            "per account, per region, and Service Quotas is rate limited per account, so an "
            "hourly cadence across a large organization would spend the account's whole "
            "allowance reading quotas. All of it is free of charge, so the cost below is a "
            "true zero rather than a rounding. ADR-0012 and constraint 9."
        ),
        est_cost_per_run="0",
    ),
    ScheduleEntry(
        collector="team_digests",
        cadence_seconds=WEEKLY,
        reason=(
            "A digest summarises one complete week, so composing it more often than "
            "weekly would write the same week again and change nothing a reader sees. "
            "It reads cost rows already in the database and calls no provider and no "
            "model, so a run costs a query and the figure below is a true zero. FEAT-041, "
            "P7 spec section 7, ADR-0012 and constraint 9."
        ),
        est_cost_per_run="0",
    ),
    # P8, FEAT-069 and ADR-0033. Run by the API, not the worker: due_collectors leaves it out.
    # Migration 0029 installs the same row for every tenant that existed before it.
    ScheduleEntry(
        collector="report_schedules",
        cadence_seconds=FIFTEEN_MINUTES,
        reason=(
            "A schedule falls due at a fixed hour at most once a day, so looking every fifteen "
            "minutes renders each within a quarter of an hour of its time. A look reads the due "
            "schedules and renders through the API in process, calling no provider and no "
            "model, so its cost is a query, and an S3 request for each file written. ADR-0012, "
            "ADR-0033 and FEAT-069."
        ),
        est_cost_per_run="0.000005",
        runs_in="api",
    ),
    # FEAT-077, TASK-P11-002. Migration 0041 installs the same row for every tenant before it.
    ScheduleEntry(
        collector="ownership",
        cadence_seconds=DAILY,
        reason=(
            "Daily, P11 specification section 7. Tags are read from the inventory Meter already "
            "holds, with no AWS call; the service catalogue, AWS AppRegistry, is read once per "
            "account and Region; CloudTrail's event history is asked once for each resource that "
            "has no creator yet, and never again. Owners change when teams reorganise, not by the "
            "hour, so a daily read keeps a suggestion at most a day behind. ADR-0012, constraint 9 "
            "and FEAT-077."
        ),
        est_cost_per_run="0.0005",
    ),
    # FEAT-078, TASK-P11-006. Migration 0043 installs the same row for every tenant before it.
    ScheduleEntry(
        collector="savings_ledger",
        cadence_seconds=DAILY,
        reason=(
            "Daily, P11 specification section 7. Reads only what Meter already holds, FEAT-029's "
            "verdicts, the recommendations' owners and the bill's daily cost, with no AWS call. A "
            "verdict is reached at most once a day, so a daily read credits a verified saving at "
            "most a day after it verifies. ADR-0012, constraint 9 and FEAT-078."
        ),
        est_cost_per_run="0",
    ),
    # FEAT-092, TASK-P15-004. Migration 0060 installs the same row for every tenant before it.
    ScheduleEntry(
        collector="fix_pull_requests",
        cadence_seconds=TEN_MINUTES,
        reason=(
            "Opens each fix a person asked for, follows each open pull request and, under the "
            "tenant's merge policy, merges, P15 spec section 7. Every ten minutes, so a person who "
            "asks sees the pull request within ten minutes and each later step within the next "
            "run. GitHub's API is free within its rate limit and the worker's NAT carries "
            "kilobytes: modelled at 0.00 USD a run. ADR-0012 and constraint 9."
        ),
        est_cost_per_run="0.00",
    ),
    # FEAT-095, TASK-P16-005. Migration 0065 installs the same row for every tenant before it.
    ScheduleEntry(
        collector="plan_estimates",
        cadence_seconds=TEN_MINUTES,
        reason=(
            "Prices each Terraform plan received from the catalog Meter already holds and writes "
            "its estimate, P16 spec section 7. Every ten minutes, so an estimate is written within "
            "ten minutes of its plan arriving. It reads only Meter's own tables: modelled at 0.00 "
            "USD a run. ADR-0012 and constraint 9."
        ),
        est_cost_per_run="0.00",
    ),
    # FEAT-096, TASK-P16-006. Migration 0066 installs the same row for every tenant before it.
    ScheduleEntry(
        collector="plan_comments",
        cadence_seconds=TEN_MINUTES,
        reason=(
            "Writes or edits each estimate's one comment on its pull request and follows the pull "
            "request until it merges or closes, P16 spec section 7. Every ten minutes, so the "
            "comment follows its estimate within the next run. GitHub's API is free within its "
            "rate limit: modelled at 0.00 USD a run. ADR-0012 and constraint 9."
        ),
        est_cost_per_run="0.00",
    ),
    # FEAT-097, TASK-P16-007. Migration 0067 installs the same row for every tenant before it.
    ScheduleEntry(
        collector="estimate_comparison",
        cadence_seconds=DAILY,
        reason=(
            "Sets each resource a merged plan created against thirty billed days once the bill "
            "reaches them, and restates the verdict as the bill is restated, P16 spec section 7. "
            "Daily, as the bill is read. It reads only Meter's own tables: modelled at 0.00 USD a "
            "run. ADR-0012 and constraint 9."
        ),
        est_cost_per_run="0.00",
    ),
)


#: The flag that stops every retention job at once. Declared in
#: `docs/feature-flags.yaml` as a permanent operational control: retention
#: removes data, so a suspected bug in one has to be stoppable now rather than
#: after a deploy.
RETENTION_FLAG = "retention_jobs"

#: Which collectors that flag governs. Derived from the name rather than listed,
#: because a list here and the collectors in `retention.py` is two places to add
#: a job and one place to forget.
RETENTION_PREFIXES = ("retention_", "partition_")


def governed_by_retention_flag(collector: str) -> bool:
    return collector.startswith(RETENTION_PREFIXES)


def due_collectors(
    connection: Any,
    tenant_id: Any,
    is_enabled: Callable[[str], bool],
    now: datetime,
) -> tuple[str, ...]:
    """Which of a tenant's collectors are due, honouring the kill switch.

    `is_enabled` is passed in rather than imported. The flag resolver lives in
    `finops_api` and this package sits below it, so taking the predicate is what
    keeps the layering intact. It has no default: a default of "everything is
    on" would turn a missing wire up into a silently ignored kill switch, which
    is the one failure an operational control must not have.

    A collector the flag turns off produces no unit and therefore no
    `ingest_run`, so it reads as stale on the freshness screen rather than as a
    successful run that removed nothing. That is the honest rendering: retention
    is not running, and the flag's own reason calls that a deliberate,
    temporary and auditable act.
    """
    rows = connection.execute(
        text(
            "SELECT s.collector, s.cadence_seconds, latest.finished_at "
            "FROM collector_schedule s LEFT JOIN LATERAL ("
            "  SELECT MAX(r.finished_at) AS finished_at FROM ingest_run r "
            "  WHERE r.tenant_id = s.tenant_id AND r.collector = s.collector "
            "  AND r.status IN ('SUCCEEDED', 'PARTIAL')"
            ") latest ON true WHERE s.tenant_id = :tenant AND s.is_enabled "
            "AND s.runs_in = 'worker' ORDER BY s.collector"
        ),
        {"tenant": tenant_id},
    ).mappings()

    retention_on = is_enabled(RETENTION_FLAG)
    due = []
    for row in rows:
        name = str(row["collector"])
        if governed_by_retention_flag(name) and not retention_on:
            continue
        last = row["finished_at"]
        # Never run is due. An absent last run is the case the first dispatch
        # after onboarding depends on.
        if last is None or (now - last).total_seconds() >= int(row["cadence_seconds"]):
            due.append(name)
    return tuple(due)


def install_default_schedule(connection: Any, tenant_id: Any, updated_by: str) -> int:
    """Give a tenant the P0 cadences. Idempotent, and never overwrites a change.

    An operator who has deliberately slowed a collector down should not have that
    undone by a redeploy, so an existing row is left alone.
    """
    written = 0
    for entry in DEFAULT_SCHEDULE:
        result = connection.execute(
            text(
                "INSERT INTO collector_schedule (tenant_id, collector, cadence_seconds, "
                "reason, est_cost_per_run, updated_by, runs_in) VALUES (:tenant, :collector, "
                ":cadence, :reason, :cost, :who, :runs_in) "
                "ON CONFLICT (tenant_id, collector) DO NOTHING"
            ),
            {
                "tenant": tenant_id,
                "collector": entry.collector,
                "cadence": entry.cadence_seconds,
                "reason": entry.reason,
                "cost": entry.est_cost_per_run,
                "who": updated_by,
                "runs_in": entry.runs_in,
            },
        )
        written += result.rowcount or 0
    return written


class CollectorRegistry:
    """The collectors this process knows how to run."""

    def __init__(self) -> None:
        self._collectors: dict[str, Collector] = {}

    def register(self, collector: Collector) -> None:
        if collector.name in self._collectors:
            raise ValueError(
                f"{collector.name} is already registered. Two collectors under one name "
                f"means the dispatcher and the worker disagree about what ran."
            )
        self._collectors[collector.name] = collector

    def get(self, name: str) -> Collector:
        try:
            return self._collectors[name]
        except KeyError as missing:
            raise KeyError(
                f"No collector named {name!r}. A unit of work naming a collector that "
                f"does not exist is a dispatch bug, not something to skip quietly."
            ) from missing

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._collectors))

    def __contains__(self, name: object) -> bool:
        return name in self._collectors
