"""What an estate is allowed to run, how close it is, and what was asked for.

Three routes, P5 spec section 8. FEAT-033 and FEAT-034.

**Nothing in this module writes.** There is no POST, no PUT, no PATCH and no DELETE, and
that absence is constraint 6 and spec section 6 rather than an oversight:
`RequestServiceQuotaIncrease` is a write into a member account, so Meter drafts the request
and hands it to a person. The IAM policy does not grant the call, and a test asserts the
name appears nowhere.

**The list route returns two lists and states both counts.** A quota nothing measured has no
headroom to sort by, and that is not zero headroom. One list would have to put those rows
somewhere, and wherever they sort is a claim: at the top they read as urgent and at the
bottom as safe, and neither is known. The counts travel because both lists are truncated, so
a reader given eight of forty cannot work the ratio out, and the ratio is the honest summary
of how much of this problem AWS lets anybody solve.

**Coverage counts quotas, not accounts.** Accounts would be the wrong denominator here in
the way that reads as reassuring: a reader whose whole organization is visible would be told
coverage is complete while nine tenths of their quotas had no usage figure at all.
TASK-P5-005, and the plan notes this would have been the fourth time a wrong count reached
that slot.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Connection

from finops_api.db.repositories import AccessContext
from finops_api.db.repositories.quotas import (
    QuotaRepository,
    QuotaRequestHistoryRepository,
    QuotaRequestRepository,
)
from finops_api.deps import get_access_context, get_connection, get_scope
from finops_api.routes import API_PREFIX, build_meta
from finops_api.schemas import (
    DraftRefusalOut,
    Envelope,
    QuotaDetailOut,
    QuotaDraftOut,
    QuotaOut,
    QuotaRequestOut,
    QuotaRequestsOut,
    QuotasOut,
    RequestTransitionOut,
    UnmeasurableQuotaOut,
)
from finops_core.domain.tenant import Scope
from finops_query.quota import DraftRefused, draft_for

router = APIRouter(prefix=API_PREFIX, tags=["quotas"])

#: What a caller gets when the quota exists in nothing they can read. A 404 rather than an
#: empty detail, because an empty page says the quota has no limits and no requests, which is
#: a claim about a quota nobody has collected.
NO_SUCH_QUOTA = "No quota by that service and code has been collected in this scope."

#: The statuses that mean something is still going to happen. The same test `RequestStatus.
#: is_open` makes, and the repository has to make it a third time in SQL, so
#: `tests/api/test_quota_routes.py` holds the three equal rather than trusting them.
OPEN_STATUSES = ("PENDING", "CASE_OPENED")


def _figure(value: Any) -> Decimal | None:
    """A number the provider published, or None. Never a zero standing in for an absence."""
    return None if value is None else Decimal(str(value))


def _measured(row: Any) -> QuotaOut:
    return QuotaOut(
        account_id=row.sub_account_id,
        region_id=row.region_id,
        service_code=row.service_code,
        quota_code=row.quota_code,
        quota_name=row.quota_name,
        limit=_figure(row.limit_value),
        # Not `_figure`: a row in this list has a usage by construction, because the
        # repository filtered on the source and the database holds the two equal. A None here
        # would be a broken invariant rather than an absence, and the model refusing it is how
        # that arrives as a loud error rather than as a blank cell.
        used=Decimal(str(row.used_value)),
        source=row.usage_source,
        headroom=_figure(row.headroom),
        is_adjustable=row.is_adjustable,
    )


def _unmeasured(row: Any) -> UnmeasurableQuotaOut:
    return UnmeasurableQuotaOut(
        account_id=row.sub_account_id,
        region_id=row.region_id,
        service_code=row.service_code,
        quota_code=row.quota_code,
        quota_name=row.quota_name,
        limit=_figure(row.limit_value),
        reason=row.unmeasurable_reason,
        is_adjustable=row.is_adjustable,
    )


def _draft(row: Any) -> QuotaDraftOut | DraftRefusalOut:
    """The increase Meter would ask for on this slice, or the reason it would not.

    Per slice, because each region carries its own limit and its own observed peak. A single
    draft for a quota code would be sized from whichever row the query returned first, which
    is a number about a region nobody named.
    """
    outcome = draft_for(
        service_code=row.service_code,
        quota_code=row.quota_code,
        region_id=row.region_id,
        current_limit=_figure(row.limit_value),
        observed_usage=_figure(row.used_value),
        is_adjustable=row.is_adjustable,
    )
    if isinstance(outcome, DraftRefused):
        return DraftRefusalOut(
            account_id=row.sub_account_id,
            region_id=row.region_id,
            reason=outcome.reason,
        )
    return QuotaDraftOut(
        account_id=row.sub_account_id,
        region_id=row.region_id,
        current_limit=outcome.current_limit,
        observed_usage=outcome.observed_usage,
        suggested_value=outcome.suggested_value,
        working=outcome.working,
        console_url=outcome.console_url,
        cli_command=outcome.cli_command,
    )


def _request(row: Any) -> QuotaRequestOut:
    return QuotaRequestOut(
        request_id=row.request_id,
        account_id=row.sub_account_id,
        region_id=row.region_id,
        service_code=row.service_code,
        quota_code=row.quota_code,
        quota_name=row.quota_name,
        desired_value=Decimal(str(row.desired_value)),
        status=row.status,
        is_open=row.status in OPEN_STATUSES,
        requested_at=row.requested_at,
        last_updated_at=row.last_updated_at,
        submitted_by_meter=row.submitted_by_meter,
    )


@router.get("/governance/quotas", response_model=Envelope[QuotasOut])
def quotas(
    connection: Connection = Depends(get_connection),
    scope: Scope = Depends(get_scope),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[QuotasOut]:
    """Every quota this reader can see, in two lists. FEAT-033.

    The measured ones are ordered by headroom, least first, which is the only list in this
    product ordered by something other than money. The unmeasured ones are ordered by name,
    because a limit on its own ranks nothing: a quota of 5 nobody is near and a quota of 5000
    that is nearly full sort identically and neither position means anything.

    The second list is expected to be the longer one. That is not a defect to hide, it is the
    state of what AWS publishes, and the counts beside it are what let a reader tell this
    product's limits from the provider's.
    """
    repository = QuotaRepository(connection, context)
    measurable = repository.measurable(scope)
    unmeasurable = repository.unmeasurable(scope)
    measured_count, found_count = repository.coverage(scope)

    found = QuotasOut(
        measurable=tuple(_measured(row) for row in measurable),
        unmeasurable=tuple(_unmeasured(row) for row in unmeasurable),
        measured_count=measured_count,
        found_count=found_count,
    )
    meta = build_meta(
        connection,
        scope,
        context,
        visible=measured_count,
        rows=[*measurable, *unmeasurable],
        coverage=(measured_count, found_count),
        coverage_unit="quotas",
    )
    return Envelope(data=found, meta=meta)


@router.get("/governance/quotas/requests", response_model=Envelope[QuotaRequestsOut])
def requests(
    connection: Connection = Depends(get_connection),
    scope: Scope = Depends(get_scope),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[QuotaRequestsOut]:
    """Increase requests and what became of them. FEAT-034.

    This is the half of FEAT-034 actually missing from the tools people have. Nobody loses a
    quota increase because they could not find the button; they lose it because nobody
    checked whether it was ever approved.

    Every request Meter has read is here, refusals included. Coverage is in accounts rather
    than quotas, and deliberately: a request list is not a sample of quotas, it is everything
    somebody asked for in the accounts this reader can see.
    """
    repository = QuotaRequestRepository(connection, context)
    rows = repository.all_requests(scope)
    found = QuotaRequestsOut(
        requests=tuple(_request(row) for row in rows),
        open_count=sum(1 for row in rows if row.status in OPEN_STATUSES),
    )
    meta = build_meta(
        connection,
        scope,
        context,
        visible=len({row.sub_account_id for row in rows}),
        rows=rows,
    )
    return Envelope(data=found, meta=meta)


@router.get(
    "/governance/quotas/{service_code}/{quota_code}",
    response_model=Envelope[QuotaDetailOut],
)
def quota_detail(
    service_code: str,
    quota_code: str,
    connection: Connection = Depends(get_connection),
    scope: Scope = Depends(get_scope),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[QuotaDetailOut]:
    """One quota, everywhere it applies, with every request against it. FEAT-033, FEAT-034.

    Several rows rather than one, because a quota code is per region: the same limit can be
    nearly full in one region and untouched in another, and answering with whichever row came
    back first would be a number about a region nobody named.

    The requests come with their status history, so the page can say when an increase was
    approved rather than only that it is. A request for a quota in the unmeasured list still
    appears: tracking and measuring are independent, and the requests somebody made because
    they had no figure to look at are exactly the ones worth not losing.
    """
    quota_rows = QuotaRepository(connection, context).one(scope, service_code, quota_code)
    if not quota_rows:
        raise HTTPException(status_code=404, detail=NO_SUCH_QUOTA)

    request_rows = QuotaRequestRepository(connection, context).for_quota(
        scope, service_code, quota_code
    )
    history = QuotaRequestHistoryRepository(connection, context)
    transitions = {
        row.request_id: tuple(
            RequestTransitionOut(status=entry.status, changed_at=entry.changed_at)
            for entry in history.for_request(scope, row.request_id)
        )
        for row in request_rows
    }

    drafted = [_draft(row) for row in quota_rows]
    first = quota_rows[0]
    found = QuotaDetailOut(
        service_code=first.service_code,
        quota_code=first.quota_code,
        quota_name=first.quota_name,
        is_adjustable=first.is_adjustable,
        measurable=tuple(_measured(row) for row in quota_rows if row.usage_source != "NONE"),
        unmeasurable=tuple(_unmeasured(row) for row in quota_rows if row.usage_source == "NONE"),
        requests=tuple(_request(row) for row in request_rows),
        history={key: value for key, value in transitions.items() if value},
        drafts=tuple(one for one in drafted if isinstance(one, QuotaDraftOut)),
        draft_refusals=tuple(one for one in drafted if isinstance(one, DraftRefusalOut)),
    )
    meta = build_meta(
        connection,
        scope,
        context,
        visible=len({row.sub_account_id for row in quota_rows}),
        rows=list(quota_rows),
    )
    return Envelope(data=found, meta=meta)
