"""What the estate should cost instead, and whether the bill moved.

Six routes. The shape worth noticing is that the estimate and the realization are
served by **different routes returning different types**, so no response object
holds both. That is TASK-P3-014's requirement and it is a property of this module
rather than a rule somebody has to remember.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Connection

from finops_api.db.repositories import AccessContext
from finops_api.db.repositories.accounts import AccountRepository
from finops_api.db.repositories.containers import (
    ContainerClusterRepository,
    ContainerUsageRepository,
)
from finops_api.db.repositories.waste import (
    RealizedSavingRepository,
    RecommendationEventRepository,
    RecommendationRepository,
    RefusalRepository,
    ScoreComponentRepository,
    ScoreRepository,
)
from finops_api.deps import get_access_context, get_connection, get_scope, get_tickets
from finops_api.lifecycle import TransitionRefusedError, move
from finops_api.routes import API_PREFIX, build_meta
from finops_api.schemas import (
    ClusterUsageOut,
    ContainerUsageRowOut,
    ContainerWasteOut,
    Envelope,
    RealizedSavingOut,
    RealizedSavingsOut,
    RecommendationDetailOut,
    RecommendationEventOut,
    RecommendationOut,
    RecommendationsOut,
    RefusalOut,
    RefusalsOut,
    ScoreComponentOut,
    ScoreOut,
    ScoresOut,
    VerdictTotalOut,
)
from finops_core.domain.containers import OomStatus
from finops_core.domain.tenant import Scope
from finops_core.domain.waste import Lifecycle, WasteClass
from finops_query.actions import risk_of

router = APIRouter(prefix=API_PREFIX, tags=["waste"])

#: What a caller gets when nothing has been collected. A 404 says the thing does
#: not exist; an empty list would say the estate has no waste, which is a claim
#: nobody has earned the right to make about an estate nobody has looked at.
NO_RECOMMENDATIONS = "No recommendation has been collected for this tenant yet."


def _maybe(value: Any) -> Decimal | None:
    """A measured quantity, or None where nothing was published.

    The billing export omits `consumed_quantity` for some services, and a zero in
    its place would read as a workload that vanished rather than as a control nobody
    could measure.
    """
    return None if value is None else Decimal(value)


def recommendation_out(row: Any) -> RecommendationOut:
    """One recommendation row on the wire, risk included.

    Public rather than underscored since FEAT-053, because the entity detail page shows the
    same findings and a second serialiser would be a second answer to what a recommendation
    looks like, including a second chance to forget the risk fields.
    """
    # FEAT-052. Computed here from the closed table rather than stored on the row, because
    # the risk of a class is a property of the class and not of one finding: storing it would
    # need a migration every time the sentence was improved, and eighteen copies of a
    # sentence is eighteen chances for one of them to be the old one.
    risk = risk_of(WasteClass(row.waste_class))
    return RecommendationOut(
        recommendation_id=row.recommendation_id,
        account_id=row.sub_account_id,
        source=row.source,
        waste_class=row.waste_class,
        resource_id=row.resource_id,
        region_id=row.region_id,
        estimated_monthly_saving=Decimal(row.estimated_monthly_saving),
        severity=row.severity,
        confidence=row.confidence,
        observation_days=row.observation_days,
        lifecycle=row.lifecycle,
        owner=row.owner,
        ticket_reference=row.ticket_reference,
        rationale=row.rationale,
        reversible=risk.reversible,
        disturbs_running_work=risk.disturbs_running_work,
        is_no_regret=risk.is_no_regret,
        risk_why=risk.why,
    )


@router.get("/waste/recommendations", response_model=Envelope[RecommendationsOut])
def recommendations(
    lifecycle: str | None = None,
    waste_class: str | None = None,
    owner: str | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    connection: Connection = Depends(get_connection),
    scope: Scope = Depends(get_scope),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[RecommendationsOut]:
    """Worst money first, filterable.

    Ranked by the saving rather than by confidence, per ADR-0016. A list ordered by
    confidence puts a certain twenty dollars above an uncertain ten thousand, and
    only one of those is worth a morning.
    """
    repository = RecommendationRepository(connection, context)
    rows = repository.worst_first(
        scope, lifecycle=lifecycle, waste_class=waste_class, owner=owner, limit=limit
    )
    found = RecommendationsOut(
        recommendations=[recommendation_out(row) for row in rows],
        unowned=repository.unowned(scope),
    )
    meta = build_meta(
        connection,
        scope,
        context,
        # Accounts, not recommendations. A row count in this slot has been the
        # defect three times; see `tasks/lessons.md`.
        visible=repository.accounts_seen(scope),
        rows=rows,
    )
    return Envelope(data=found, meta=meta)


@router.get(
    "/waste/recommendations/{recommendation_id}",
    response_model=Envelope[RecommendationDetailOut],
)
def recommendation_detail(
    recommendation_id: UUID,
    connection: Connection = Depends(get_connection),
    scope: Scope = Depends(get_scope),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[RecommendationDetailOut]:
    """One recommendation, with how it got where it is."""
    repository = RecommendationRepository(connection, context)
    row = repository.one(scope, recommendation_id)
    if row is None:
        # Out of scope and absent are the same answer, so a caller cannot
        # enumerate other accounts' recommendations by id.
        raise HTTPException(status_code=404, detail=NO_RECOMMENDATIONS)

    history = RecommendationEventRepository(connection, context).history(scope, recommendation_id)
    found = RecommendationDetailOut(
        recommendation=recommendation_out(row),
        history=[
            RecommendationEventOut(
                from_lifecycle=event.from_lifecycle,
                to_lifecycle=event.to_lifecycle,
                actor=event.actor,
                reason=event.reason,
                occurred_at=event.occurred_at,
            )
            for event in history
        ],
    )
    meta = build_meta(connection, scope, context, visible=1, rows=[row])
    return Envelope(data=found, meta=meta)


def _transition(
    connection: Connection,
    scope: Scope,
    context: AccessContext,
    recommendation_id: UUID,
    target: Lifecycle,
    *,
    reason: str | None = None,
    owner: str | None = None,
    tickets: Any = None,
) -> Envelope[RecommendationDetailOut]:
    """One transition, refused as a 409 rather than a 500.

    A refused move is a statement about this recommendation's state, not a fault,
    and the message says what moves are available instead.
    """
    # The read happens through the scoped repository first, so a caller cannot
    # move a recommendation they may not see.
    if RecommendationRepository(connection, context).one(scope, recommendation_id) is None:
        raise HTTPException(status_code=404, detail=NO_RECOMMENDATIONS)
    try:
        move(
            connection,
            tenant_id=scope.tenant_id,
            recommendation_id=recommendation_id,
            target=target,
            # Never blank. An event whose actor is unknown is an event that
            # cannot be reviewed, and "unknown" is at least honest about it.
            actor=str(context.principal_id or "unknown"),
            reason=reason,
            owner=owner,
            tickets=tickets,
        )
    except TransitionRefusedError as refused:
        raise HTTPException(status_code=409, detail=str(refused)) from refused
    return recommendation_detail(recommendation_id, connection, scope, context)


@router.post(
    "/waste/recommendations/{recommendation_id}/accept",
    response_model=Envelope[RecommendationDetailOut],
)
def accept(
    recommendation_id: UUID,
    owner: str = Query(min_length=1, max_length=256),
    connection: Connection = Depends(get_connection),
    scope: Scope = Depends(get_scope),
    context: AccessContext = Depends(get_access_context),
    tickets: Any = Depends(get_tickets),
) -> Envelope[RecommendationDetailOut]:
    """Accept it, name an owner, and open a ticket.

    The owner is required. ISS-021: an unowned finding is never fixed, and an
    acceptance with nobody's name on it is the commonest way one becomes unowned.
    """
    return _transition(
        connection,
        scope,
        context,
        recommendation_id,
        Lifecycle.ACCEPTED,
        owner=owner,
        tickets=tickets,
    )


@router.post(
    "/waste/recommendations/{recommendation_id}/dismiss",
    response_model=Envelope[RecommendationDetailOut],
)
def dismiss(
    recommendation_id: UUID,
    reason: str = Query(min_length=1, max_length=1000),
    connection: Connection = Depends(get_connection),
    scope: Scope = Depends(get_scope),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[RecommendationDetailOut]:
    """Dismiss it, with a reason.

    The reason is required by the route, by the service and by the database. A
    dismissal nobody can review is indistinguishable from a recommendation nobody
    looked at, and the three layers agreeing is deliberate.
    """
    return _transition(
        connection, scope, context, recommendation_id, Lifecycle.DISMISSED, reason=reason
    )


@router.get("/waste/refusals", response_model=Envelope[RefusalsOut])
def refusals(
    connection: Connection = Depends(get_connection),
    scope: Scope = Depends(get_scope),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[RefusalsOut]:
    """What a sizing rule examined and declined to recommend. FEAT-062, ADR-0027.

    **Returns no saving and no severity, and that is the point.** A refusal has no money.
    ADR-0016 orders every finding by money, so a zero here would rank as the least valuable
    action rather than as the absence of one, which is the defect that put this in its own
    table rather than in `recommendation`.

    The question it answers is the one the competitive review said Meter could not answer: an
    engineer whose service never appears in a waste list cannot tell whether it was examined
    and found correctly sized or never examined at all. Those are different facts and the
    product rendered them identically.

    Nothing here is new arithmetic. `finops_query/waste.py` computed these all along and the
    collector discarded them on one line.
    """
    repository = RefusalRepository(connection, context)
    rows = repository.latest(scope)
    found = RefusalsOut(
        refusals=tuple(
            RefusalOut(
                resource_id=row.resource_id,
                account_id=row.sub_account_id,
                region_id=row.region_id,
                waste_class=row.waste_class,
                reason=row.reason,
                observation_days=row.observation_days,
            )
            for row in rows
        ),
        examined=repository.counted(scope),
    )
    # The denominator is accounts, like the recommendations list, and it comes from the
    # recommendation repository because that is where the estate wide count lives. A refusal
    # list drawn from two accounts of five is two fifths of an answer.
    meta = build_meta(
        connection,
        scope,
        context,
        visible=RecommendationRepository(connection, context).accounts_seen(scope),
        rows=rows,
    )
    return Envelope(data=found, meta=meta)


@router.get("/waste/savings", response_model=Envelope[RealizedSavingsOut])
def savings(
    connection: Connection = Depends(get_connection),
    scope: Scope = Depends(get_scope),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[RealizedSavingsOut]:
    """What actually appeared in the bill. FEAT-029.

    Returns **no estimated figure at all**. The two are different kinds of number
    and this response deliberately cannot be used to add them, which is the
    property TASK-P3-014 asserts.

    Grouped by verdict rather than totalled, because an inconclusive saving is not
    a saving and a single figure would imply otherwise.
    """
    repository = RealizedSavingRepository(connection, context)
    rows = repository.all_verdicts(scope)
    totals = repository.totals(scope)
    found = RealizedSavingsOut(
        savings=[
            RealizedSavingOut(
                recommendation_id=row.recommendation_id,
                cost_before=Decimal(row.cost_before),
                cost_after=Decimal(row.cost_after),
                # Passed through rather than coerced. An unobserved usage stays
                # None all the way to the response, so the screen can say so.
                usage_before=_maybe(row.usage_before),
                usage_after=_maybe(row.usage_after),
                verdict=row.verdict,
                why=row.why,
                window_before_start=row.window_before_start,
                window_after_end=row.window_after_end,
            )
            for row in rows
        ],
        by_verdict={
            str(row[0]): VerdictTotalOut(count=int(row[1]), realized_monthly=Decimal(row[2]))
            for row in totals
        },
    )
    meta = build_meta(connection, scope, context, visible=len(rows), rows=rows)
    return Envelope(data=found, meta=meta)


@router.get("/waste/score", response_model=Envelope[ScoresOut])
def posture_score(
    connection: Connection = Depends(get_connection),
    scope: Scope = Depends(get_scope),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[ScoresOut]:
    """The score and, with it, the components that produced it. FEAT-043.

    The components are in the same response as the total rather than behind a second
    call, because the feature ships only if it decomposes and a second call is a
    second thing a screen can decline to make.

    Worst first. A list of scores sorted best first is a list nobody scrolls, and the
    account at the bottom is the one the reader came for.
    """
    scores = ScoreRepository(connection, context)
    rows = scores.latest(scope)
    parts: dict[Any, list[ScoreComponentOut]] = {}
    for part in ScoreComponentRepository(connection, context).of(
        scope, [row.score_id for row in rows]
    ):
        parts.setdefault(part.score_id, []).append(
            ScoreComponentOut(
                name=part.name,
                # None stays None all the way out. See `ScoreComponentOut`.
                points=None if part.points is None else Decimal(part.points),
                weight=int(part.weight),
                why=part.why,
                findings=list(part.finding_ids),
            )
        )

    scored = {row.sub_account_id for row in rows}
    found = ScoresOut(
        scores=[
            ScoreOut(
                account_id=row.sub_account_id,
                total=int(row.total),
                available_weight=int(row.available_weight),
                why=row.why,
                components=parts.get(row.score_id, []),
                as_of=row.as_of,
            )
            for row in rows
        ],
        # Accounts in scope that produced no score. Listed, because an account nobody
        # could assess must not simply be missing from a league table.
        unscored=sorted(
            account
            for account in (
                str(row.account_id)
                for row in AccountRepository(connection, context).list_in_scope(scope)
            )
            if account not in scored
        ),
    )
    meta = build_meta(connection, scope, context, visible=len(rows), rows=rows)
    return Envelope(data=found, meta=meta)


@router.get("/waste/containers", response_model=Envelope[ContainerWasteOut])
def waste_containers(
    connection: Connection = Depends(get_connection),
    scope: Scope = Depends(get_scope),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[ContainerWasteOut]:
    """Requested against used, per workload, under Waste per ADR-0020. FEAT-036.

    Two figures for each resource and never one efficiency percentage. A namespace at
    twenty percent could be over requesting by a factor of five or could be idle, and
    those are different conversations with different people, spec section 9.

    A cluster that cannot publish requests is listed with its workloads' use and no
    request, and says why. Absent from this list it would report a tidier estate than
    the one that exists, and the cluster nobody can measure is the one worth asking
    about. Container recommendations themselves are P3's, served by
    `/waste/recommendations` filtered to the container class: there is no second list.
    """
    clusters_repository = ContainerClusterRepository(connection, context)
    usage_repository = ContainerUsageRepository(connection, context)
    clusters = clusters_repository.clusters(scope)
    usage = usage_repository.reservations(scope)

    by_cluster: dict[tuple[str, str, str], list[ContainerUsageRowOut]] = {}
    for row in usage:
        by_cluster.setdefault((row.sub_account_id, row.region_id, row.cluster_name), []).append(
            ContainerUsageRowOut(
                namespace=row.namespace,
                workload=row.workload,
                workload_kind=row.workload_kind,
                launch_type=row.launch_type,
                cpu_requested_millicores=row.cpu_requested_millicores,
                cpu_used_p99_millicores=row.cpu_used_p99_millicores,
                memory_requested_mib=row.memory_requested_mib,
                memory_used_peak_mib=row.memory_used_peak_mib,
                # The column is a nullable boolean and the wire carries the three words,
                # so a client can never read null as not killed.
                oom_status=OomStatus.from_observation(row.was_oom_killed).value,
                observation_days=row.observation_days,
            )
        )

    found_clusters = tuple(
        ClusterUsageOut(
            cluster_name=row.cluster_name,
            account_id=row.sub_account_id,
            region_id=row.region_id,
            platform=row.platform,
            enhanced_observability=row.enhanced_observability,
            request_unavailable_reason=row.request_unavailable_reason,
            workloads=tuple(
                by_cluster.get((row.sub_account_id, row.region_id, row.cluster_name), ())
            ),
        )
        for row in clusters
    )
    measured, found = clusters_repository.request_coverage(scope)
    meta = build_meta(
        connection,
        scope,
        context,
        # Clusters whose requests are readable, against clusters found. Accounts in
        # this slot would call coverage complete while half the clusters had no request.
        visible=measured,
        rows=[*clusters, *usage],
        coverage=(measured, found),
        coverage_unit="clusters",
    )
    return Envelope(
        data=ContainerWasteOut(clusters=found_clusters, measured_count=measured, found_count=found),
        meta=meta,
    )
