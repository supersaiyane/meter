"""Reading the organization tree.

`org_node` carries no account column, so the tenant filter is the whole of its
scoping today. That is a decision rather than an oversight: a principal scoped
to two accounts still needs the units above them or the map is unnavigable, and
an organizational unit name is structure rather than cost. If a tenant ever
treats unit names as sensitive, this needs a decision recorded in an ADR and a
subtree filter here, not a quiet change.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import ClassVar

from sqlalchemy import Row, Table

from finops_api.db import models
from finops_api.db.repositories.base import ScopedRepository
from finops_core.domain.tenant import Scope


class OrgRepository(ScopedRepository):
    table: ClassVar[Table] = models.org_node
    resource: ClassVar[str] = "org_node"

    def list_tree(self, scope: Scope) -> Sequence[Row[*tuple[object, ...]]]:
        statement = self.scoped_select(scope).order_by(self.table.c["depth"])
        return self.fetch(scope, statement)
