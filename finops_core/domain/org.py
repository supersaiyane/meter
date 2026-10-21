"""The organization tree, as a set of nodes that know their own parent.

The node type is a closed set. An open one attracts a fourth member the first
time a provider says something unfamiliar, and the tree then has a shape the
renderer has never seen. An unfamiliar node is a `SchemaDrift` failure at
ingest, which is loud, rather than a new enum member, which is silent.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from finops_core.domain.account import Provider
from finops_core.domain.fact import Fact


class OrgNodeType(StrEnum):
    ROOT = "ROOT"
    OU = "OU"
    ACCOUNT = "ACCOUNT"


@dataclass(frozen=True, kw_only=True)
class OrgNode(Fact):
    """One node of the organization tree at `as_of`."""

    node_id: str
    node_type: OrgNodeType
    name: str
    parent_id: str | None
    provider: Provider

    def __post_init__(self) -> None:
        if self.node_type is OrgNodeType.ROOT and self.parent_id is not None:
            raise ValueError(
                "A ROOT node has no parent. A root with one means the tree has two "
                "roots, and a walk over it does not end."
            )
        if self.node_type is not OrgNodeType.ROOT and self.parent_id is None:
            raise ValueError(
                f"A {self.node_type.value} node must name its parent, or it is "
                "unreachable from the root and silently disappears from the tree."
            )
