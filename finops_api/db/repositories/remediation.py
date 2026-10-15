"""The code host a tenant connected, and where each state's fixes go. P15, FEAT-091, TASK-P15-003.

Both tables belong to the payer, ADR-0025, and are `PayerWide` in the guard, so a narrowed scope
reads nothing from either. Each is changed by a person whose scope is the organization, audited
ALLOWED or DENIED in the write's own transaction, and a refusal reaches the end of its request
without raising, so the rollback cannot take the audit row with it, as the commitment policy's is.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, ClassVar, Final
from uuid import uuid4

from sqlalchemy import Row, Table, select
from sqlalchemy.dialects.postgresql import insert

from finops_api.db import models
from finops_api.db.repositories.base import ScopedRepository
from finops_api.guards import ScopeViolationError, require_scope, scope_predicate
from finops_core.domain.tenant import Scope

#: Through `Any`, as the other repositories read their rows.
RemediationRow = Row[*tuple[Any, ...]]

NEEDS_A_PERSON = (
    "The code host and where fixes go are the organization's, so only a person whose scope is the "
    "whole organization may change them. See ADR-0025."
)


def _person(scope: Scope) -> Scope:
    confirmed = require_scope(scope)
    if not confirmed.is_global or confirmed.principal_id is None:
        raise ScopeViolationError(NEEDS_A_PERSON)
    return confirmed


@dataclass(frozen=True)
class Mapping:
    """Where one Terraform state's fixes go."""

    state_reference: str
    repository: str
    base_branch: str
    folder: str


class CodeHostConnectionRepository(ScopedRepository):
    """The GitHub App a tenant connected: its id and its key's secret name, never the key."""

    table: ClassVar[Table] = models.code_host_connection
    resource: ClassVar[str] = "code_host_connection"

    def current(self, scope: Scope) -> RemediationRow | None:
        """The tenant's connection, or None where none was made."""
        rows: Sequence[RemediationRow] = self.fetch(scope, self.scoped_select(scope))
        return rows[0] if rows else None

    def connect(
        self, scope: Scope, *, host: str, app_id: str, key_secret_name: str, at: datetime
    ) -> RemediationRow:
        """Set the connection, audited ALLOWED. Only a global scope naming a person may."""
        confirmed = _person(scope)
        values = {
            "host": host,
            "app_id": app_id,
            "key_secret_name": key_secret_name,
            "connected_by": confirmed.principal_id,
            "connected_at": at,
        }
        statement = (
            insert(self.table)
            .values(tenant_id=confirmed.tenant_id, **values)
            .on_conflict_do_update(index_elements=[self.table.c.tenant_id], set_=values)
            .returning(*self.table.c)
        )
        row: RemediationRow = self._connection.execute(statement).one()
        self._audit(confirmed, action="change", outcome="ALLOWED")
        return row

    def refuse(self, scope: Scope) -> None:
        """Record a refused change, so a narrowed attempt is in the audit trail."""
        self._audit(require_scope(scope), action="change", outcome="DENIED")


class RepositoryMappingRepository(ScopedRepository):
    """Which repository, branch and folder each Terraform state's fixes go to. OPEN-42."""

    table: ClassVar[Table] = models.repository_mapping
    resource: ClassVar[str] = "repository_mapping"

    def all(self, scope: Scope) -> Sequence[RemediationRow]:
        """Every mapping, by state reference."""
        statement = self.scoped_select(scope).order_by(self.table.c.state_reference)
        rows: Sequence[RemediationRow] = self.fetch(scope, statement)
        return rows

    def unmapped(self, scope: Scope) -> tuple[str, ...]:
        """The states FEAT-057 read resources from that no mapping names.

        So a reader sees which fixes would have nowhere to go. Nothing for a narrowed scope, which
        reads no mapping either.
        """
        confirmed = require_scope(scope)
        if not confirmed.is_global:
            return ()
        managed = models.resource_management
        mapped = select(self.table.c.state_reference).where(
            self.table.c.tenant_id == confirmed.tenant_id
        )
        statement = (
            select(managed.c.state_reference)
            .distinct()
            .where(managed.c.tenant_id == confirmed.tenant_id)
            .where(scope_predicate(managed, confirmed))
            .where(managed.c.state_reference.not_in(mapped))
            .order_by(managed.c.state_reference)
        )
        return tuple(str(one) for one in self._connection.execute(statement).scalars())

    def replace(self, scope: Scope, mappings: Sequence[Mapping], *, at: datetime) -> None:
        """Make the tenant's mapping exactly `mappings`, audited ALLOWED.

        A mapping that did not change keeps who set it and when; a new or changed one is the
        person's, now; one left out is removed.
        """
        confirmed = _person(scope)
        table = self.table
        kept = {row.state_reference: row for row in self.all(confirmed)}
        wanted = {one.state_reference for one in mappings}
        gone = [reference for reference in kept if reference not in wanted]
        if gone:
            self._connection.execute(
                table.delete()
                .where(table.c.tenant_id == confirmed.tenant_id)
                .where(table.c.state_reference.in_(gone))
            )
        for one in mappings:
            before = kept.get(one.state_reference)
            target = (one.repository, one.base_branch, one.folder)
            if before is not None and (before.repository, before.base_branch, before.folder) == (
                target
            ):
                continue
            values = {
                "repository": one.repository,
                "base_branch": one.base_branch,
                "folder": one.folder,
                "set_by": confirmed.principal_id,
                "set_at": at,
            }
            self._connection.execute(
                insert(table)
                .values(
                    tenant_id=confirmed.tenant_id, state_reference=one.state_reference, **values
                )
                .on_conflict_do_update(
                    index_elements=[table.c.tenant_id, table.c.state_reference], set_=values
                )
            )
        self._audit(confirmed, action="change", outcome="ALLOWED")

    def refuse(self, scope: Scope) -> None:
        """Record a refused change, so a narrowed attempt is in the audit trail."""
        self._audit(require_scope(scope), action="change", outcome="DENIED")


#: The statuses in which a fix is live: asked for and not yet opened, or open. One per
#: recommendation, held by a partial unique index too.
LIVE: Final = ("REQUESTED", "OPEN")


class FixPullRequestRepository(ScopedRepository):
    """The fixes asked for, scoped as their recommendation's account. FEAT-092, TASK-P15-004."""

    table: ClassVar[Table] = models.fix_pull_request
    resource: ClassVar[str] = "fix_pull_request"

    def request(
        self, scope: Scope, recommendation: Any, *, note: str | None, at: datetime
    ) -> RemediationRow | None:
        """Record an ask, audited ALLOWED, or None where a fix is already requested or open.

        The caller has read `recommendation` through its own scoped repository, so the scope
        covers its account. Only a person asks.
        """
        confirmed = require_scope(scope)
        if confirmed.principal_id is None:
            raise ScopeViolationError("A fix is asked for by a person, so a scope names one.")
        table = self.table
        statement = (
            insert(table)
            .values(
                fix_id=uuid4(),
                tenant_id=confirmed.tenant_id,
                recommendation_id=recommendation.recommendation_id,
                sub_account_id=recommendation.sub_account_id,
                status="REQUESTED",
                note=note,
                requested_by=confirmed.principal_id,
                requested_at=at,
                as_of=at,
                collected_at=at,
            )
            .on_conflict_do_nothing(
                index_elements=[table.c.tenant_id, table.c.recommendation_id],
                index_where=table.c.status.in_(LIVE),
            )
            .returning(*table.c)
        )
        row: RemediationRow | None = self._connection.execute(statement).first()
        if row is None:
            return None
        self._connection.execute(
            models.fix_pull_request_event.insert().values(
                event_id=uuid4(),
                fix_id=row.fix_id,
                tenant_id=confirmed.tenant_id,
                sub_account_id=row.sub_account_id,
                from_status=None,
                to_status="REQUESTED",
                principal=confirmed.principal_id,
                note=note,
                at=at,
            )
        )
        self._audit(confirmed, action="request", outcome="ALLOWED")
        return row

    def all(self, scope: Scope) -> Sequence[RemediationRow]:
        """Every fix the scope reaches, the newest ask first."""
        statement = self.scoped_select(scope).order_by(
            self.table.c.requested_at.desc(), self.table.c.fix_id
        )
        rows: Sequence[RemediationRow] = self.fetch(scope, statement)
        return rows

    def steps(self, scope: Scope, fixes: Sequence[Any]) -> dict[Any, list[RemediationRow]]:
        """Each fix's steps, oldest first, through the steps table's own scope rule."""
        confirmed = require_scope(scope)
        events = models.fix_pull_request_event
        found: dict[Any, list[RemediationRow]] = {fix: [] for fix in fixes}
        if not fixes:
            return found
        statement = (
            select(events)
            .where(events.c.tenant_id == confirmed.tenant_id)
            .where(scope_predicate(events, confirmed))
            .where(events.c.fix_id.in_(list(fixes)))
            .order_by(events.c.at, events.c.event_id)
        )
        for row in self._connection.execute(statement):
            found[row.fix_id].append(row)
        return found


class MergePolicyRepository(ScopedRepository):
    """Which reversible fixes the tenant lets Meter merge. FEAT-094, ADR-0038, TASK-P15-007."""

    table: ClassVar[Table] = models.merge_policy
    resource: ClassVar[str] = "merge_policy"

    def current(self, scope: Scope) -> Sequence[RemediationRow]:
        """Each class the policy names, with its reason."""
        statement = self.scoped_select(scope).order_by(self.table.c.waste_class)
        rows: Sequence[RemediationRow] = self.fetch(scope, statement)
        return rows

    def replace(self, scope: Scope, classes: Sequence[str], *, reason: str, at: datetime) -> None:
        """Make the policy exactly `classes`, each with this reason, audited ALLOWED."""
        confirmed = _person(scope)
        table = self.table
        self._connection.execute(table.delete().where(table.c.tenant_id == confirmed.tenant_id))
        for waste_class in classes:
            self._connection.execute(
                table.insert().values(
                    tenant_id=confirmed.tenant_id,
                    waste_class=waste_class,
                    reason=reason,
                    set_by=confirmed.principal_id,
                    set_at=at,
                )
            )
        self._audit(confirmed, action="change", outcome="ALLOWED")

    def refuse(self, scope: Scope) -> None:
        """Record a refused change, so a narrowed attempt is in the audit trail."""
        self._audit(require_scope(scope), action="change", outcome="DENIED")
