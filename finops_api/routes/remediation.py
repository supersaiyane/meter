"""Where fixes go: the code host connection and the repository mapping. P15, FEAT-091.

TASK-P15-003, spec sections 5.1, 5.3 and 8, OPEN-13 and OPEN-42. Both are the organization's: a
narrowed reader is answered 404 with the reason, as the commitment routes answer, and a change
needs a person whose scope is the whole organization, audited ALLOWED or DENIED. Nothing here
reaches GitHub; only the worker does, ADR-0036, so a connection is recorded as given and proved by
`make first-contact` and by the collector's first run.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy import Connection

from finops_api.db.repositories import AccessContext
from finops_api.db.repositories.remediation import (
    CodeHostConnectionRepository,
    FixPullRequestRepository,
    Mapping,
    RemediationRow,
    RepositoryMappingRepository,
)
from finops_api.db.repositories.waste import RecommendationRepository
from finops_api.deps import get_access_context, get_connection, get_scope, get_settings
from finops_api.routes import API_PREFIX, build_meta
from finops_api.schemas import (
    CodeHostConnectionIn,
    CodeHostConnectionOut,
    Envelope,
    FixPullRequestFollowedOut,
    FixPullRequestOut,
    FixPullRequestsOut,
    FixRequestIn,
    FixStepOut,
    Meta,
    RepositoryMappingOut,
    RepositoryMappingsIn,
    RepositoryMappingsOut,
)
from finops_core.config import Settings
from finops_core.domain.tenant import Scope
from finops_providers.aws.secrets import codehost_key_prefix

router = APIRouter(prefix=API_PREFIX, tags=["remediation"])

NEEDS_THE_ORGANIZATION = (
    "The code host and where fixes go belong to the organization, so they need a scope that "
    "covers the whole organization. See ADR-0025."
)


def _organization_only(scope: Scope) -> None:
    """A 404 for a narrowed reader, as the commitment routes answer, never an empty answer."""
    if not scope.is_global:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NEEDS_THE_ORGANIZATION)


def _refused(
    repository: CodeHostConnectionRepository | RepositoryMappingRepository, scope: Scope
) -> JSONResponse | None:
    """Refuse a change by anyone but a person whose scope is the organization, audited DENIED.

    Answered rather than raised, so the rollback cannot take the DENIED audit row with it.
    """
    if scope.is_global and scope.principal_id is not None:
        return None
    repository.refuse(scope)
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN, content={"detail": NEEDS_THE_ORGANIZATION}
    )


class _Stamp:
    """A setting's change as a fact: true and fetched when it was made."""

    def __init__(self, at: datetime) -> None:
        self.as_of = at
        self.collected_at = at


def _meta(
    connection: Connection, scope: Scope, context: AccessContext, stamps: Sequence[Any]
) -> Meta:
    """One organization of one, ADR-0025, with the oldest and newest change of the rows."""
    return build_meta(
        connection,
        scope,
        context,
        visible=1,
        coverage=(1, 1),
        coverage_unit="payer",
        as_of=min((one.as_of for one in stamps), default=None),
        collected_at=max((one.collected_at for one in stamps), default=None),
    )


def _connection_out(row: RemediationRow | None) -> CodeHostConnectionOut:
    if row is None:
        return CodeHostConnectionOut(
            connected=False,
            host=None,
            app_id=None,
            key_secret_name=None,
            connected_by=None,
            connected_at=None,
        )
    return CodeHostConnectionOut(
        connected=True,
        host=row.host,
        app_id=row.app_id,
        key_secret_name=row.key_secret_name,
        connected_by=row.connected_by,
        connected_at=row.connected_at,
    )


@router.get("/remediation/connection", response_model=Envelope[CodeHostConnectionOut])
def remediation_connection(
    connection: Connection = Depends(get_connection),
    scope: Scope = Depends(get_scope),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[CodeHostConnectionOut]:
    """The GitHub App fixes go through, or that none is connected. FEAT-091."""
    _organization_only(scope)
    row = CodeHostConnectionRepository(connection, context).current(scope)
    stamps = [] if row is None else [_Stamp(row.connected_at)]
    return Envelope(data=_connection_out(row), meta=_meta(connection, scope, context, stamps))


@router.put("/remediation/connection", response_model=Envelope[CodeHostConnectionOut])
def change_remediation_connection(
    body: CodeHostConnectionIn,
    connection: Connection = Depends(get_connection),
    scope: Scope = Depends(get_scope),
    context: AccessContext = Depends(get_access_context),
    settings: Settings = Depends(get_settings),
) -> Envelope[CodeHostConnectionOut] | JSONResponse:
    """Connect the GitHub App, by its id and its key's secret name. The organization's only."""
    repository = CodeHostConnectionRepository(connection, context)
    refused = _refused(repository, scope)
    if refused is not None:
        return refused
    prefix = codehost_key_prefix(settings.env)
    if not body.key_secret_name.startswith(prefix):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"The key's secret must be under {prefix}, the only path the worker may read "
            "it from. docs/runbooks/code-host.md",
        )
    row = repository.connect(
        scope,
        host=body.host,
        app_id=body.app_id,
        key_secret_name=body.key_secret_name,
        at=datetime.now(UTC),
    )
    stamps = [_Stamp(row.connected_at)]
    return Envelope(data=_connection_out(row), meta=_meta(connection, scope, context, stamps))


def _mappings(
    connection: Connection, scope: Scope, context: AccessContext
) -> Envelope[RepositoryMappingsOut]:
    repository = RepositoryMappingRepository(connection, context)
    rows = repository.all(scope)
    found = RepositoryMappingsOut(
        mappings=[
            RepositoryMappingOut(
                **{name: getattr(row, name) for name in RepositoryMappingOut.model_fields}
            )
            for row in rows
        ],
        unmapped=list(repository.unmapped(scope)),
    )
    stamps = [_Stamp(row.set_at) for row in rows]
    return Envelope(data=found, meta=_meta(connection, scope, context, stamps))


@router.get("/remediation/repositories", response_model=Envelope[RepositoryMappingsOut])
def remediation_repositories(
    connection: Connection = Depends(get_connection),
    scope: Scope = Depends(get_scope),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[RepositoryMappingsOut]:
    """Where each Terraform state's fixes go, and the states that have nowhere yet. OPEN-42."""
    _organization_only(scope)
    return _mappings(connection, scope, context)


@router.put("/remediation/repositories", response_model=Envelope[RepositoryMappingsOut])
def change_remediation_repositories(
    body: RepositoryMappingsIn,
    connection: Connection = Depends(get_connection),
    scope: Scope = Depends(get_scope),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[RepositoryMappingsOut] | JSONResponse:
    """Set the whole mapping. One left out is removed. The organization's only."""
    repository = RepositoryMappingRepository(connection, context)
    refused = _refused(repository, scope)
    if refused is not None:
        return refused
    repository.replace(
        scope,
        [
            Mapping(one.state_reference, one.repository, one.base_branch, one.folder)
            for one in body.mappings
        ],
        at=datetime.now(UTC),
    )
    return _mappings(connection, scope, context)


NO_RECOMMENDATION = "No recommendation has that identifier in this scope."
ACCEPT_FIRST = (
    "A fix is asked for once the recommendation is accepted with an owner, so somebody owns the "
    "pull request it opens. ISS-021."
)
ALREADY_ASKED = "A fix is already asked for, or open, for this recommendation."
A_PERSON_ASKS = "A fix is asked for by a person, and this session names none."


@router.post(
    "/waste/recommendations/{recommendation_id}/pull-request",
    response_model=Envelope[FixPullRequestOut],
)
def ask_for_a_fix(
    recommendation_id: UUID,
    body: FixRequestIn,
    connection: Connection = Depends(get_connection),
    scope: Scope = Depends(get_scope),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[FixPullRequestOut] | JSONResponse:
    """Ask for the fix to be opened as a pull request. FEAT-092, TASK-P15-004.

    Recorded here and opened by the `fix_pull_requests` collector within ten minutes, because only
    the worker reaches GitHub, ADR-0036. A person whose scope includes the account asks, once the
    recommendation is accepted, and one fix is live per recommendation.
    """
    # Read through the scoped repository first, so nobody asks about one they may not see.
    recommendation = RecommendationRepository(connection, context).one(scope, recommendation_id)
    if recommendation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NO_RECOMMENDATION)
    if scope.principal_id is None:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN, content={"detail": A_PERSON_ASKS}
        )
    if recommendation.lifecycle != "ACCEPTED":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{ACCEPT_FIRST} It is {recommendation.lifecycle}.",
        )
    note = body.note.strip() if body.note and body.note.strip() else None
    row = FixPullRequestRepository(connection, context).request(
        scope, recommendation, note=note, at=datetime.now(UTC)
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=ALREADY_ASKED)
    found = FixPullRequestOut(
        **{name: getattr(row, name) for name in FixPullRequestOut.model_fields}
    )
    meta = build_meta(
        connection,
        scope,
        context,
        visible=1,
        rows=[row],
        coverage=(1, 1),
        coverage_unit="recommendations",
    )
    return Envelope(data=found, meta=meta)


@router.get("/remediation/pull-requests", response_model=Envelope[FixPullRequestsOut])
def remediation_pull_requests(
    connection: Connection = Depends(get_connection),
    scope: Scope = Depends(get_scope),
    context: AccessContext = Depends(get_access_context),
) -> Envelope[FixPullRequestsOut]:
    """Every fix asked for in the reader's scope, its status and its steps. TASK-P15-006."""
    repository = FixPullRequestRepository(connection, context)
    rows = repository.all(scope)
    steps = repository.steps(scope, [row.fix_id for row in rows])
    found = FixPullRequestsOut(
        fixes=[
            FixPullRequestFollowedOut(
                **{
                    name: getattr(row, name)
                    for name in FixPullRequestFollowedOut.model_fields
                    if name != "steps"
                },
                steps=[
                    FixStepOut(**{name: getattr(step, name) for name in FixStepOut.model_fields})
                    for step in steps[row.fix_id]
                ],
            )
            for row in rows
        ]
    )
    meta = build_meta(
        connection, scope, context, visible=len(rows), rows=rows, coverage_unit="recommendations"
    )
    return Envelope(data=found, meta=meta)
