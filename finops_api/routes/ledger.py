"""The savings ledger: teams by the savings they hold, and each team's credits. FEAT-078.

TASK-P11-008, P11 spec sections 5.6 and 8. Two reads of what the `savings_ledger` collector
stored, both exportable, every figure measured: a credit's held saving is the sum of the months the
bill showed it held, never a projection. The ledger ranks teams and never people, OPEN-27: a
person's name appears only as the owner or closer on a team's own credits. Each credit is read
through its account's scope, so a reader narrowed to one account sees only that account's credits,
and coverage counts accounts, as the recommendations do.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Connection

from finops_api.db.repositories import AccessContext
from finops_api.db.repositories.ledger import SavingsCreditRepository
from finops_api.deps import get_access_context, get_connection, get_scope
from finops_api.exports import ExportSpec, exportable, rows_in
from finops_api.routes import API_PREFIX, build_meta
from finops_api.schemas import (
    Envelope,
    LedgerCreditOut,
    LedgerCreditsOut,
    LedgerMonthOut,
    LedgerOut,
    LedgerTeamOut,
)
from finops_core.domain.tenant import Scope

router = APIRouter(prefix=API_PREFIX, tags=["savings"])

HELD, REGRESSED = "HELD", "REGRESSED"


def _decimal(value: Any) -> Decimal | None:
    return None if value is None else Decimal(value)


def credit_out(row: Any) -> LedgerCreditOut:
    """One credit on the wire, its held saving summed from the months the bill showed."""
    months = [
        LedgerMonthOut(
            month=one["month"],
            state=one["state"],
            cost=_decimal(one["cost"]),
            saving=_decimal(one["saving"]),
            as_of=one["as_of"],
            collected_at=one["collected_at"],
        )
        for one in row.months or ()
    ]
    held = [one.saving for one in months if one.state == HELD and one.saving is not None]
    return LedgerCreditOut(
        credit_id=row.credit_id,
        recommendation_id=row.recommendation_id,
        account_id=row.sub_account_id,
        resource_id=row.resource_id,
        team=row.team,
        owner=row.owner,
        closed_by=row.closed_by,
        verified_monthly_saving=Decimal(row.verified_monthly_saving),
        verified_on=row.verified_on,
        saving_held=sum(held, Decimal(0)),
        months_held=len(held),
        regressed=any(one.state == REGRESSED for one in months),
        months=months,
        as_of=row.as_of,
        collected_at=row.collected_at,
    )


def teams_of(credited: Sequence[LedgerCreditOut]) -> list[LedgerTeamOut]:
    """Each team's credits summed, the most held saving first; the unnamed team last on a tie."""
    grouped: dict[str | None, list[LedgerCreditOut]] = {}
    for one in credited:
        grouped.setdefault(one.team, []).append(one)
    teams = [
        LedgerTeamOut(
            team=team,
            credits=len(held),
            saving_held=sum((one.saving_held for one in held), Decimal(0)),
            months_held=sum(one.months_held for one in held),
            regressed=sum(1 for one in held if one.regressed),
            latest_month=max((month.month for one in held for month in one.months), default=None),
            # The stalest credit's, so a team's figure is never fresher than its parts.
            as_of=min(one.as_of for one in held),
            collected_at=min(one.collected_at for one in held),
        )
        for team, held in grouped.items()
    ]
    return sorted(teams, key=lambda one: (-one.saving_held, one.team is None, one.team or ""))


def _accounts(rows: Sequence[Any]) -> int:
    return len({row.sub_account_id for row in rows})


@router.get("/savings/ledger", response_model=Envelope[LedgerOut])
@exportable(
    ExportSpec(
        title="Savings ledger", row_model=LedgerTeamOut, rows=rows_in("teams"), metric="Saving held"
    )
)
def ledger(
    connection: Connection = Depends(get_connection),
    scope: Scope = Depends(get_scope),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[LedgerOut]:
    """Teams by the savings they hold, most first. Teams, never people, OPEN-27."""
    rows = SavingsCreditRepository(connection, context).every(scope)
    teams = teams_of([credit_out(row) for row in rows])
    meta = build_meta(connection, scope, context, visible=_accounts(rows), rows=rows)
    return Envelope(data=LedgerOut(teams=teams), meta=meta)


@router.get("/savings/ledger/credits", response_model=Envelope[LedgerCreditsOut])
@exportable(
    ExportSpec(
        title="Savings ledger credits",
        row_model=LedgerCreditOut,
        rows=rows_in("credits"),
        metric="Saving held",
    )
)
def ledger_credits(
    team: str | None = Query(default=None, max_length=256),
    connection: Connection = Depends(get_connection),
    scope: Scope = Depends(get_scope),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[LedgerCreditsOut]:
    """One team's credits with their months, the most held saving first.

    `team` names the team; an empty `team` asks for the credits no source named a team for; no
    `team` at all asks for every credit the reader can see, which is what an export of the whole
    ledger wants.
    """
    rows = SavingsCreditRepository(connection, context).every(scope)
    chosen = [row for row in rows if team is None or (row.team or "") == team]
    listed = sorted(
        (credit_out(row) for row in chosen), key=lambda one: (-one.saving_held, one.verified_on)
    )
    found = LedgerCreditsOut(team=team or None, every_team=team is None, credits=listed)
    meta = build_meta(connection, scope, context, visible=_accounts(chosen), rows=chosen)
    return Envelope(data=found, meta=meta)
