"""Computing the posture score and storing it with its parts.

The arithmetic is in `finops_query.score` and has no database. This is the part that
gathers a `Posture` per account, asks for a `Score`, and writes the total and every
component in one transaction.

**One score per account, per run.** The components go in beside it rather than being
recomputed later, because the components of last week's score cannot be derived once
the findings have changed. That is what makes a difference between two runs a list of
findings that opened or closed rather than two numbers a reader takes on trust.

**Coverage is counted in accounts, and the collector says so.** Which individual
resources a waste collector managed to observe is not recorded anywhere, so the
honest denominator available today is whether the waste collectors reached the
account at all. The unit travels with the figure, because a coverage number whose
unit is implied has been the defect four times in this product. ISS-192 is the finer
signal.

**An account nobody could judge gets no score.** Not zero. `score()` returns None
where no component is computable, and this writes nothing for that account, so the
screen says the account was not assessed rather than showing it as the worst in the
estate.

**No team scores yet.** FEAT-043 asks for them and they need the P2 tag allocation
join, and a team score computed from a partial allocation is the same misleading
figure as a team score computed from the accounts one reader happens to see. Stated
here rather than left for somebody to notice the rows are missing. ISS-193.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text

from finops_core.domain.waste import Lifecycle
from finops_ingest.registry import CollectorContext, CollectorOutcome
from finops_query.realized import Verdict
from finops_query.score import Finding, Posture, Verification, score

COLLECTOR = "finops_score"
SCOPE = "billing"

#: The window the spend figure covers. Thirty days rather than a calendar month
#: because a score recomputed every six hours would otherwise jump on the first of
#: the month, when the denominator resets and every ratio doubles.
SPEND_DAYS = 30

#: How recently a waste collector must have succeeded for an account to count as
#: judged. Two days rather than one, so a single failed run does not read as an
#: unobserved account and blank the score.
JUDGED_WITHIN_DAYS = 2

#: The collectors whose success means an account was actually looked at. The AWS
#: native source is not among them: it returns findings without our having measured
#: anything, so an account where only it ran has been reported on rather than judged.
JUDGING_COLLECTORS = ("waste_compute", "waste_cloudwatch")

Clock = Callable[[], datetime]


def _system_clock() -> datetime:
    return datetime.now(UTC)


#: The accounts to score. `cloud_account.account_id` rather than `sub_account_id`:
#: that is the column name on the account table, and the recommendation and cost
#: tables call the same value `sub_account_id` because there it is the member account
#: under a payer. The join is on the value, not on the name.
ACCOUNTS = text(
    "SELECT account_id FROM cloud_account WHERE tenant_id = :tenant ORDER BY account_id"
)

SPEND = text(
    "SELECT COALESCE(SUM(effective_cost), 0) FROM cost_focus_daily "
    "WHERE tenant_id = :tenant AND sub_account_id = :account "
    "AND date(charge_period_start) >= :since"
)

#: Open findings only. A dismissed or verified recommendation is neither money on
#: the bill nor work waiting, and including it would make a score that never
#: improves no matter what anybody does.
FINDINGS = text(
    "SELECT recommendation_id, estimated_monthly_saving, lifecycle, owner "
    "FROM recommendation "
    "WHERE tenant_id = :tenant AND sub_account_id = :account "
    "AND lifecycle IN ('OPEN', 'ACCEPTED', 'IN_PROGRESS', 'DONE')"
)

VERIFICATIONS = text(
    "SELECT s.recommendation_id, s.verdict FROM realized_saving s "
    "JOIN recommendation r ON r.recommendation_id = s.recommendation_id "
    "WHERE s.tenant_id = :tenant AND r.sub_account_id = :account"
)

#: Whether a waste collector got through this account recently. The scope key format
#: is `provider:account:region`, documented in `docs/07-DATA-MODEL.md`, so the second
#: field is the account.
WAS_JUDGED = text(
    "SELECT COUNT(*) FROM ingest_run "
    "WHERE tenant_id = :tenant AND collector = ANY(:collectors) "
    "AND status IN ('SUCCEEDED', 'PARTIAL') "
    "AND split_part(scope_key, ':', 2) = :account "
    "AND finished_at >= :since"
)

WRITE_SCORE = text(
    "INSERT INTO finops_score (score_id, tenant_id, sub_account_id, team, total, "
    "available_weight, why, as_of, collected_at) "
    "VALUES (:id, :tenant, :account, NULL, :total, :weight, :why, :at, :now)"
)

WRITE_COMPONENT = text(
    "INSERT INTO finops_score_component (component_id, score_id, tenant_id, name, "
    "points, weight, why, finding_ids, as_of, collected_at) "
    "VALUES (:id, :score, :tenant, :name, :points, :weight, :why, :findings, :at, :now)"
)

#: A second run at the same instant would collide on the unique index. Replacing
#: rather than failing, because a run repeated by a retry is not an error and the
#: verdict is the same either way.
REPLACE = text(
    "DELETE FROM finops_score WHERE tenant_id = :tenant AND sub_account_id = :account "
    "AND as_of = :at"
)

#: Accounts that produced no score at all. Recorded so the absence is a named gap
#: rather than a shorter list nobody counts.
UNSCORED_ERROR = text(
    "INSERT INTO sync_error (error_id, tenant_id, collector, scope_key, error_type, "
    "detail, remediation, first_seen_at, last_seen_at, occurrences) "
    "VALUES (:id, :t, :c, :s, 'NoData', :d, :r, :now, :now, 1) "
    "ON CONFLICT (tenant_id, collector, scope_key, error_type) DO UPDATE SET "
    "detail = EXCLUDED.detail, last_seen_at = EXCLUDED.last_seen_at, "
    "occurrences = sync_error.occurrences + 1"
)


def _findings(rows: Any, at: datetime) -> tuple[Finding, ...]:
    return tuple(
        Finding(
            recommendation_id=str(row[0]),
            monthly_saving=Decimal(row[1]),
            lifecycle=Lifecycle(row[2]),
            owner=row[3],
            # The score does not use the date, and it is on the entity because a
            # later component about ageing will. Passing the run time keeps the
            # collector from inventing one.
            opened_on=at.date(),
        )
        for row in rows
    )


class ScoreCollector:
    """One score per account, with its components, every run."""

    def __init__(self, clock: Clock = _system_clock) -> None:
        self._clock = clock

    def __call__(self, context: CollectorContext) -> CollectorOutcome:
        at = self._clock()
        tenant = context.unit.tenant_id
        accounts = [row[0] for row in context.connection.execute(ACCOUNTS, {"tenant": tenant})]

        written = 0
        unscored: list[str] = []
        for account in accounts:
            posture = self._posture(context, account, at)
            found = score(posture)
            if found is None:
                # Nothing about this account could be computed, so there is no
                # number. Writing a zero would put the account at the bottom of a
                # league table for a collection failure.
                unscored.append(account)
                continue
            self._write(context, account, found, at)
            written += 1

        if unscored:
            self._record_gap(context, unscored, len(accounts), at)

        return CollectorOutcome(items_written=written)

    def _posture(self, context: CollectorContext, account: str, at: datetime) -> Posture:
        tenant = context.unit.tenant_id
        spend = context.connection.execute(
            SPEND,
            {
                "tenant": tenant,
                "account": account,
                "since": at.date() - timedelta(days=SPEND_DAYS),
            },
        ).scalar_one()
        findings = context.connection.execute(
            FINDINGS, {"tenant": tenant, "account": account}
        ).all()
        verifications = context.connection.execute(
            VERIFICATIONS, {"tenant": tenant, "account": account}
        ).all()
        judged = context.connection.execute(
            WAS_JUDGED,
            {
                "tenant": tenant,
                "account": account,
                "collectors": list(JUDGING_COLLECTORS),
                "since": at - timedelta(days=JUDGED_WITHIN_DAYS),
            },
        ).scalar_one()
        return Posture(
            monthly_spend=Decimal(spend),
            findings=_findings(findings, at),
            verifications=tuple(
                Verification(recommendation_id=str(row[0]), verdict=Verdict(row[1]))
                for row in verifications
            ),
            # One account at a time, so the coverage question is whether this account
            # was reachable at all. Binary by construction, and that is the honest
            # shape of the signal that exists.
            subjects_judged=1 if judged else 0,
            subjects_in_scope=1,
            subject_unit="accounts",
        )

    def _write(self, context: CollectorContext, account: str, found: Any, at: datetime) -> None:
        tenant = context.unit.tenant_id
        score_id = uuid4()
        context.connection.execute(REPLACE, {"tenant": tenant, "account": account, "at": at})
        context.connection.execute(
            WRITE_SCORE,
            {
                "id": score_id,
                "tenant": tenant,
                "account": account,
                "total": found.total,
                "weight": found.available_weight,
                "why": found.why,
                "at": at,
                "now": at,
            },
        )
        for part in found.components:
            context.connection.execute(
                WRITE_COMPONENT,
                {
                    "id": uuid4(),
                    "score": score_id,
                    "tenant": tenant,
                    "name": part.name,
                    # None stays None. A component that could not be computed is
                    # excluded from the denominator, and a zero here would put it
                    # back in as the worst possible value.
                    "points": part.points,
                    "weight": part.weight,
                    "why": part.why,
                    "findings": [UUID(identifier) for identifier in part.findings],
                    "at": at,
                    "now": at,
                },
            )

    def _record_gap(
        self, context: CollectorContext, unscored: list[str], total: int, at: datetime
    ) -> None:
        context.connection.execute(
            UNSCORED_ERROR,
            {
                "id": uuid4(),
                "t": context.unit.tenant_id,
                "c": COLLECTOR,
                "s": SCOPE,
                "d": (
                    f"{len(unscored)} of {total} accounts could not be scored because no "
                    f"waste collector reached them, so no component was computable. "
                    f"First: {unscored[0]}"
                ),
                "r": (
                    "Check the waste collectors for these accounts. An account with no "
                    "score is an account nobody has assessed, which is different from an "
                    "account with a bad score and must not be shown as one."
                ),
                "now": at,
            },
        )
