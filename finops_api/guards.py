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

from sqlalchemy import ColumnElement, Select, Table, and_, false, select, tuple_

from finops_core.domain.tenant import Scope


class ScopeViolationError(RuntimeError):
    """A query was about to run against a scoped table without a scope."""


#: Tables holding tenant data, and the columns that identify the account a row
#: belongs to. `None` means the table carries no account identifier, so the
#: tenant filter is the whole of its scoping.
SCOPED_TABLES: dict[str, tuple[str, str] | None] = {
    "cloud_account": ("provider", "account_id"),
    "org_node": None,
    "ingest_run": None,
    "ingest_watermark": None,
    "sync_error": None,
    "cost_focus_daily": None,
    "cost_provider_extra": None,
    "platform_cost": None,
    "principal": None,
    "principal_scope": None,
    "collector_schedule": None,
    "audit_event": None,
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

    account_columns = SCOPED_TABLES[table.name]
    if account_columns is not None and not scope.is_global:
        if not scope.accounts:
            # Empty means nothing, not everything. This is the fail closed case.
            clauses.append(false())
        else:
            provider_column, account_column = account_columns
            pairs = sorted((key.provider.value, key.account_id) for key in scope.accounts)
            clauses.append(tuple_(table.c[provider_column], table.c[account_column]).in_(pairs))
    return and_(*clauses)


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
