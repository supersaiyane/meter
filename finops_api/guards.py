"""The second of the two places scope is enforced. Constraint 3 in CLAUDE.md.

ISS-009 is the reason this exists at all. Scoping only in the API layer is
bypassable by any route that forgets the dependency, and routes get added by
people who have never read this file. So the repository refuses too, and the
two checks are independent: a bug in one does not disarm the other.

The primary mechanism is shape, not vigilance. A caller cannot express an
unscoped query, because the base repository builds the predicate itself from a
`Scope` it was handed and never accepts a finished statement. `assert_scoped`
is the backstop underneath that, for the day someone adds a subclass that hand
rolls a select.

There is deliberately no default scope. A default that grants access is the
single most common cause of this class of leak, so `Scope` is a required
argument everywhere and an empty one returns nothing rather than everything.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import ColumnElement, Select, Table, and_, false, select, tuple_

from finops_core.domain.tenant import Scope


class ScopeViolationError(RuntimeError):
    """A query was about to run against a scoped table without a scope."""


@dataclass(frozen=True)
class ByAccount:
    """The row names the account it belongs to.

    `provider_column` is None for a table whose rows can only come from one
    provider, which is most of the P2 estate: an Amazon Managed Grafana
    workspace is an AWS thing by definition, and adding a provider column to
    say so would be a column with one value in it.
    """

    account_column: str
    provider_column: str | None = None


@dataclass(frozen=True)
class Through:
    """The row names no account, and inherits the scope of the row it hangs off.

    A query definition has no account column. Its account is the account of the
    workspace it was read from, and the only honest way to scope it is to ask
    that question of the workspace. Chains: a finding goes through its
    definition, which goes through its instance.

    The alternative was a denormalised account column on both tables, which is
    a second copy of a fact and therefore a second chance to disagree with the
    first.
    """

    table: str
    local_column: str
    remote_column: str


#: Tables holding tenant data, and how the account a row belongs to is found.
#: `None` means the table carries no account identifier and none can be reached
#: from it, so the tenant filter is the whole of its scoping.
SCOPED_TABLES: dict[str, ByAccount | Through | None] = {
    "cloud_account": ByAccount("account_id", "provider"),
    "org_node": None,
    "ingest_run": None,
    "ingest_watermark": None,
    "sync_error": None,
    # P1. Every charge names the account it was incurred in, so a caller
    # narrowed to two accounts reads two accounts' spend. These were `None`
    # until 2026-09-19, meaning the tenant filter was the whole of their
    # scoping, which was harmless only because nothing read them. The first
    # route over them would have served the whole organization's bill to a
    # narrowly scoped viewer. ISS-184.
    #
    # A charge with no sub account, which is a payer level line item, matches
    # nothing under a narrow scope and is visible to a global one. That is the
    # documented behaviour of `ByAccount` and it is right here: a charge nobody
    # can attribute to an account is not one a caller restricted to two
    # accounts has been given.
    "cost_focus_daily": ByAccount("sub_account_id"),
    "cost_focus_monthly": ByAccount("sub_account_id"),
    # No account column and none reachable. It holds the provider's own fields
    # for a line item, keyed by fingerprint, so the tenant filter is the whole
    # of its scoping.
    "cost_provider_extra": None,
    "platform_cost": None,
    "principal": None,
    "principal_scope": None,
    "collector_schedule": None,
    "audit_event": None,
    # P2. A workspace names its account; everything downstream of it inherits
    # that answer rather than storing a second copy of it.
    "grafana_instance": ByAccount("account_id"),
    "query_definition": Through("grafana_instance", "instance_id", "instance_id"),
    "query_finding": Through("query_definition", "query_id", "query_id"),
    # Ad hoc rows reach no workspace, because a query somebody typed into the
    # console belongs to none. They carry the account they ran in, so they are
    # scoped directly rather than through anything.
    "query_adhoc": ByAccount("account_id"),
    # folder_team_map, enforcement_action and remediation_change are absent on
    # purpose. Nobody has decided how they scope, and the fail closed branch
    # below is a better answer than a guess: the first route to read one gets a
    # loud error rather than a quiet leak.
}


def require_scope(scope: object) -> Scope:
    """Refuse anything that is not a scope, including None.

    A caller that passes None has almost always forgotten the argument rather
    than meant "no restriction", and treating None as unrestricted is how the
    forgetting becomes a leak.
    """
    if not isinstance(scope, Scope):
        raise ScopeViolationError(
            "A scoped read needs a Scope. It has no default, because a default that "
            "grants access is the most common cause of this class of leak. See "
            "constraint 3 in CLAUDE.md and ISS-009."
        )
    return scope


def scope_predicate(table: Table, scope: Scope) -> ColumnElement[bool]:
    """The WHERE clause that confines a read to what the scope permits."""
    if table.name not in SCOPED_TABLES:
        raise ScopeViolationError(
            f"{table.name} is not in SCOPED_TABLES. A table that nobody has decided "
            f"how to scope is a table that must not be read through this path."
        )
    clauses: list[ColumnElement[bool]] = [table.c["tenant_id"] == scope.tenant_id]

    rule = SCOPED_TABLES[table.name]
    if rule is None or scope.is_global:
        return and_(*clauses)

    if not scope.accounts:
        # Empty means nothing, not everything. This is the fail closed case.
        clauses.append(false())
    elif isinstance(rule, ByAccount):
        clauses.append(_account_predicate(table, rule, scope))
    else:
        clauses.append(_inherited_predicate(table, rule, scope))
    return and_(*clauses)


def _account_predicate(table: Table, rule: ByAccount, scope: Scope) -> ColumnElement[bool]:
    """Match the account the row names.

    A row whose account column is null matches nothing here, which excludes it
    from every narrowed scope. That is deliberate: a workspace nobody can
    attribute to an account is not one a caller restricted to two accounts has
    been given. A global scope never reaches this branch and still sees it.
    """
    if rule.provider_column is None:
        return table.c[rule.account_column].in_(sorted(key.account_id for key in scope.accounts))
    pairs = sorted((key.provider.value, key.account_id) for key in scope.accounts)
    return tuple_(table.c[rule.provider_column], table.c[rule.account_column]).in_(pairs)


def _inherited_predicate(table: Table, rule: Through, scope: Scope) -> ColumnElement[bool]:
    """Membership in the scoped rows of the table this one hangs off.

    Recursive, so a chain of any length resolves without each link knowing how
    long the chain is. The parent is scoped by the same function, which is what
    stops a link in the middle from being the one place the tenant filter was
    forgotten.
    """
    from finops_api.db import models

    parent = models.metadata.tables[rule.table]
    permitted = select(parent.c[rule.remote_column]).where(scope_predicate(parent, scope))
    return table.c[rule.local_column].in_(permitted)


#: Execution option stamped on any select this module built. Generative methods
#: such as `where`, `order_by` and `limit` carry it forward, so a repository can
#: refine a scoped query without losing the mark.
SCOPE_APPLIED = "meter_scope_applied"


def scoped_select(table: Table, scope: Scope) -> Select[tuple[object, ...]]:
    """The only constructor of a select against a scoped table."""
    confirmed = require_scope(scope)
    return (
        select(table)
        .where(scope_predicate(table, confirmed))
        .execution_options(**{SCOPE_APPLIED: True})
    )


def assert_scoped(statement: Select[tuple[object, ...]], table: Table) -> None:
    """Backstop. Refuse to run a select that did not come from `scoped_select`.

    This checks for the mark rather than reading the rendered WHERE clause. The
    first version of this function did read the text, and it was wrong in the
    one case that matters most: for an empty scope, SQLAlchemy folds
    `and_(tenant_id = x, false())` down to `false`, the rendered clause stops
    mentioning `tenant_id`, and the check rejected a query that was correctly
    confined to nothing. A backstop that fails closed on the fail closed path is
    worse than no backstop, because it hides behind looking careful.
    """
    if table.name not in SCOPED_TABLES:
        return
    if not statement.get_execution_options().get(SCOPE_APPLIED):
        raise ScopeViolationError(
            f"A select on {table.name} was not built by scoped_select, so nothing "
            f"has confined it to a tenant. Build it with scoped_select rather than "
            f"by hand."
        )
