"""Rebuilding the organization tree and the account list, hourly, with no human step.

Two rules shape this and both are about what a reader sees while it runs.

The tree is replaced inside the worker's own transaction. Doing it without one
leaves a window where the tree is empty, and an empty organization renders as
zero cost to anyone who reads it in that moment. The self referencing key on
`org_node` is `DEFERRABLE INITIALLY DEFERRED` precisely so the replacement can
insert children before parents and still be checked at commit.

An account that has left is marked, never deleted. Its cost history has to
survive its departure, and deleting the row would also shrink the denominator
behind every organization total.

An empty discovery result is refused rather than applied. An organization always
contains at least its management account, so zero accounts means the call went
wrong, and applying it would mark every account departed at once.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import column, table, text

from finops_core.domain.account import CloudAccount, Provider
from finops_core.domain.org import OrgNode, OrgNodeType
from finops_core.errors import NoData
from finops_ingest.registry import CollectorContext, CollectorOutcome

COLLECTOR = "org_tree"
PATH_SEPARATOR = "/"

_ORG_NODE = table("org_node", column("tenant_id"))

Clock = Callable[[], datetime]


def _system_clock() -> datetime:
    return datetime.now(UTC)


def compute_paths(nodes: Sequence[OrgNode]) -> dict[str, tuple[str, int]]:
    """The materialised path and depth of every node.

    Both are denormalised so a subtree filter is an index scan rather than a
    recursive walk, and both are recomputed from scratch on every refresh rather
    than patched, because a patched path that drifts is a subtree that silently
    stops matching.
    """
    by_id = {node.node_id: node for node in nodes}
    resolved: dict[str, tuple[str, int]] = {}

    def resolve(node_id: str, seen: frozenset[str]) -> tuple[str, int]:
        if node_id in resolved:
            return resolved[node_id]
        if node_id in seen:
            raise NoData(
                scope_key="organization",
                collector=COLLECTOR,
                detail=f"the organization tree contains a cycle through {node_id}",
            )
        node = by_id[node_id]
        if node.parent_id is None:
            answer = (f"{PATH_SEPARATOR}{node.node_id}", 0)
        else:
            parent_path, parent_depth = resolve(node.parent_id, seen | {node_id})
            answer = (f"{parent_path}{PATH_SEPARATOR}{node.node_id}", parent_depth + 1)
        resolved[node_id] = answer
        return answer

    for node in nodes:
        resolve(node.node_id, frozenset())
    return resolved


class OrgTreeCollector:
    """Reads the organization and writes it, whole, in one transaction."""

    def __init__(self, discovery: Any, clock: Clock = _system_clock) -> None:
        self._discovery = discovery
        self._clock = clock

    def __call__(self, context: CollectorContext) -> CollectorOutcome:
        tenant_id = context.unit.tenant_id
        nodes = tuple(self._discovery.describe_organization())
        accounts = tuple(self._discovery.list_accounts())

        if not accounts:
            # An organization always holds at least its management account, so
            # this is a failed read rather than an empty one. Applying it would
            # mark every account departed in a single transaction.
            raise NoData(
                scope_key="organization",
                collector=COLLECTOR,
                detail="discovery returned no accounts, which an organization cannot have",
            )

        self._replace_tree(context.connection, tenant_id, nodes)
        self._upsert_accounts(context.connection, tenant_id, accounts)
        self._mark_departed(context.connection, tenant_id, accounts)
        return CollectorOutcome(items_written=len(nodes) + len(accounts))

    def _replace_tree(self, connection: Any, tenant_id: Any, nodes: Sequence[OrgNode]) -> None:
        paths = compute_paths(nodes)
        connection.execute(_ORG_NODE.delete().where(_ORG_NODE.c.tenant_id == tenant_id))
        for node in nodes:
            path, depth = paths[node.node_id]
            connection.execute(
                text(
                    "INSERT INTO org_node (node_pk, tenant_id, node_id, node_type, "
                    "parent_node_id, name, path, depth, as_of, collected_at) VALUES "
                    "(gen_random_uuid(), :tenant, :node, :type, :parent, :name, :path, "
                    ":depth, :as_of, :collected)"
                ),
                {
                    "tenant": tenant_id,
                    "node": node.node_id,
                    "type": OrgNodeType(node.node_type).value,
                    "parent": node.parent_id,
                    "name": node.name,
                    "path": path,
                    "depth": depth,
                    "as_of": node.as_of,
                    "collected": node.collected_at,
                },
            )

    def _upsert_accounts(
        self, connection: Any, tenant_id: Any, accounts: Sequence[CloudAccount]
    ) -> None:
        for account in accounts:
            connection.execute(
                # No parent column here on purpose. An account's place in the
                # tree is its own org_node row, so storing the parent twice
                # would create two answers that can disagree after a move.
                text(
                    "INSERT INTO cloud_account (account_pk, tenant_id, provider, account_id, "
                    "name, status, as_of, collected_at) VALUES "
                    "(gen_random_uuid(), :tenant, :provider, :account, :name, :status, "
                    ":as_of, :collected) "
                    "ON CONFLICT (tenant_id, provider, account_id) DO UPDATE SET "
                    "name = EXCLUDED.name, status = EXCLUDED.status, "
                    "as_of = EXCLUDED.as_of, collected_at = EXCLUDED.collected_at"
                ),
                {
                    "tenant": tenant_id,
                    "provider": Provider(account.key.provider).value,
                    "account": account.key.account_id,
                    "name": account.name,
                    "status": account.status.value,
                    "as_of": account.as_of,
                    "collected": account.collected_at,
                },
            )

    def _mark_departed(
        self, connection: Any, tenant_id: Any, accounts: Sequence[CloudAccount]
    ) -> None:
        """Mark, never remove. The cost history has to outlive the membership."""
        present = [account.key.account_id for account in accounts]
        providers = sorted({Provider(account.key.provider).value for account in accounts})
        connection.execute(
            text(
                "UPDATE cloud_account SET status = 'DEPARTED', collected_at = :collected "
                "WHERE tenant_id = :tenant AND provider = ANY(:providers) "
                "AND account_id <> ALL(:present) AND status <> 'DEPARTED'"
            ),
            {
                "tenant": tenant_id,
                "providers": providers,
                "present": present,
                "collected": self._clock(),
            },
        )
