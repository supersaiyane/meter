"""The weekly digests: one for each team the bill names, and one for the organization.

TASK-P7-012 and FEAT-041. Reads the daily cost rows the allocation screen reads, grouped by
the bill's `team` tag, composes each digest with `finops_query.digest`, and keeps it.

**Composed whether or not anybody can send it.** Nothing sends a digest until OPEN-11 picks
email or Slack, so every digest is written with `sent_at` null and the sentence saying so.
That is the half of the feature carrying the risk, composing the right rows with the right
provenance, and a sender is one adapter behind a port once somebody decides.

**One team failing does not fail the run.** A digest that cannot be composed is recorded as
a typed failure under a scope key of its own, the way the cost collector records its split
gap, so the worker's clear on success cannot delete it, and every other digest is still
written. A team that composes on a later run clears its own failure.

**A week with no billed spend has no digest.** Nothing collected is not a quiet week, and a
digest saying the organization spent nothing would be the zero this product exists not to
show.

Weekly, in the schedule with its reason and its cost, ADR-0012. It reads rows already in the
database and calls no provider.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import column, table, text

from finops_core.constants import TEAM_TAG
from finops_core.domain.insight import Answer
from finops_core.domain.platform import UNALLOCATED
from finops_ingest.registry import CollectorContext, CollectorOutcome
from finops_query.digest import Audience, WeekOfSpend, compose, last_complete_week

COLLECTOR = "team_digests"
SCOPE = "digests"

UNSENT = (
    "No sender is configured, so the digest was composed and kept here. Where a digest "
    "goes, email or Slack or both, is OPEN-11."
)

COMPOSE_FAILED_REMEDIATION = (
    "One digest could not be composed from its rows, and every other digest was. Read the "
    "detail, then fix the composition in finops_query/digest.py or the rows it names."
)

#: The tag value a team digest is grouped by, with untagged spend named as such.
_TEAM = f"coalesce(tags->>'{TEAM_TAG}', '{UNALLOCATED}')"

_WINDOW = "tenant_id = :t AND charge_period_start >= :start AND charge_period_start < :end"

WEEK_BY_TEAM = text(
    f"SELECT {_TEAM} AS team, sum(effective_cost) AS spend, min(as_of) AS as_of "
    f"FROM cost_focus_daily WHERE {_WINDOW} GROUP BY 1"
)

TOP_BY_TEAM = text(
    "SELECT team, service_name, spend, as_of FROM ("
    "  SELECT team, service_name, spend, as_of, row_number() OVER ("
    "    PARTITION BY team ORDER BY spend DESC, service_name) AS rank FROM ("
    f"    SELECT {_TEAM} AS team, service_name, sum(effective_cost) AS spend, "
    f"    min(as_of) AS as_of FROM cost_focus_daily WHERE {_WINDOW} GROUP BY 1, 2"
    "  ) AS per_service"
    ") AS ranked WHERE rank = 1"
)

WEEK_TOTAL = text(
    f"SELECT sum(effective_cost) AS spend, min(as_of) AS as_of FROM cost_focus_daily "
    f"WHERE {_WINDOW}"
)

TOP_OVERALL = text(
    "SELECT service_name, sum(effective_cost) AS spend, min(as_of) AS as_of "
    f"FROM cost_focus_daily WHERE {_WINDOW} GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT 1"
)

INSERT_DIGEST = text(
    "INSERT INTO team_digest (digest_id, tenant_id, ingest_run_id, audience, team, "
    "period_start, period_end, prose, citations, composed_at, sent_at, unsent_reason) "
    "VALUES (:id, :t, :run, :audience, :team, :start, :end, :prose, "
    "CAST(:citations AS JSONB), :at, NULL, :reason)"
)

COMPOSE_FAILED = text(
    "INSERT INTO sync_error (error_id, tenant_id, collector, scope_key, error_type, "
    "detail, remediation, first_seen_at, last_seen_at, occurrences) "
    "VALUES (:id, :t, :c, :s, 'SchemaDrift', :d, :r, :now, :now, 1) "
    "ON CONFLICT (tenant_id, collector, scope_key, error_type) DO UPDATE SET "
    "detail = EXCLUDED.detail, last_seen_at = EXCLUDED.last_seen_at, "
    "occurrences = sync_error.occurrences + 1"
)

#: Core constructs rather than literal SQL, so the values are bound parameters.
_DIGEST = table("team_digest", column("tenant_id"), column("period_start"), column("sent_at"))
_SYNC_ERROR = table("sync_error", column("tenant_id"), column("collector"), column("scope_key"))

Clock = Callable[[], datetime]
Composer = Callable[[WeekOfSpend], Answer]


class DigestCollector:
    """Composes the last complete week's digests for one tenant."""

    def __init__(self, clock: Clock, composer: Composer = compose) -> None:
        self._clock = clock
        self._compose = composer

    def __call__(self, context: CollectorContext) -> CollectorOutcome:
        if context.run_id is None:
            raise ValueError("a digest run needs the ledger's run id to record what wrote it")
        tenant: UUID = context.unit.tenant_id
        now = self._clock()
        start, end = last_complete_week(now)
        weeks = _weeks(context.connection, tenant, start, end)
        # A rerun of the same week replaces what it composed and never what was sent.
        context.connection.execute(
            _DIGEST.delete().where(
                _DIGEST.c.tenant_id == tenant,
                _DIGEST.c.period_start == start,
                _DIGEST.c.sent_at.is_(None),
            )
        )
        written = 0
        for week in weeks:
            scope_key = f"{SCOPE}:{week.audience.value}:{week.team or 'organization'}"
            try:
                answer = self._compose(week)
            except ValueError as failure:
                context.connection.execute(
                    COMPOSE_FAILED,
                    {
                        "id": uuid4(),
                        "t": tenant,
                        "c": COLLECTOR,
                        "s": scope_key,
                        "d": str(failure),
                        "r": COMPOSE_FAILED_REMEDIATION,
                        "now": now,
                    },
                )
                continue
            context.connection.execute(
                INSERT_DIGEST, _row(tenant, context.run_id, week, answer, now)
            )
            context.connection.execute(
                _SYNC_ERROR.delete().where(
                    _SYNC_ERROR.c.tenant_id == tenant,
                    _SYNC_ERROR.c.collector == COLLECTOR,
                    _SYNC_ERROR.c.scope_key == scope_key,
                )
            )
            written += 1
        return CollectorOutcome(items_written=written)


def _row(
    tenant: UUID, run: Any, week: WeekOfSpend, answer: Answer, now: datetime
) -> dict[str, Any]:
    return {
        "id": uuid4(),
        "t": tenant,
        "run": run,
        "audience": week.audience.value,
        "team": week.team,
        "start": week.week_start,
        "end": week.week_end,
        "prose": answer.prose,
        "citations": json.dumps([citation.as_record() for citation in answer.citations]),
        "at": now,
        "reason": UNSENT,
    }


def _weeks(connection: Any, tenant: UUID, start: date, end: date) -> list[WeekOfSpend]:
    """Every audience with billed spend in the week, the organization last."""
    week_start = datetime.combine(start, time.min, tzinfo=UTC)
    this_week = {"t": tenant, "start": week_start, "end": week_start + timedelta(days=7)}
    week_before = {"t": tenant, "start": week_start - timedelta(days=7), "end": week_start}

    spend = {row.team: row for row in connection.execute(WEEK_BY_TEAM, this_week)}
    before = {row.team: row for row in connection.execute(WEEK_BY_TEAM, week_before)}
    tops = {row.team: row for row in connection.execute(TOP_BY_TEAM, this_week)}
    weeks = [
        WeekOfSpend(
            audience=Audience.TEAM,
            team=team,
            week_start=start,
            week_end=end,
            spend=row.spend,
            spend_as_of=row.as_of,
            previous=before[team].spend if team in before else None,
            previous_as_of=before[team].as_of if team in before else None,
            top_service=tops[team].service_name if team in tops else None,
            top_service_spend=tops[team].spend if team in tops else None,
            top_as_of=tops[team].as_of if team in tops else None,
        )
        for team, row in sorted(spend.items())
    ]

    total = connection.execute(WEEK_TOTAL, this_week).one()
    if total.spend is None:
        return weeks
    previous = connection.execute(WEEK_TOTAL, week_before).one()
    top = connection.execute(TOP_OVERALL, this_week).first()
    weeks.append(
        WeekOfSpend(
            audience=Audience.EXECUTIVE,
            team=None,
            week_start=start,
            week_end=end,
            spend=total.spend,
            spend_as_of=total.as_of,
            previous=previous.spend,
            previous_as_of=previous.as_of,
            top_service=top.service_name if top else None,
            top_service_spend=top.spend if top else None,
            top_as_of=top.as_of if top else None,
        )
    )
    return weeks
