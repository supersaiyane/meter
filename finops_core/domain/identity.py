"""Who is asking, and what they are entitled to read.

ADR-0008 defers the identity provider decision, so nothing here names one. A
principal is an identifier, a display name and a set of group names, which is
the intersection of what every provider can supply.

An entitlement is a fact rather than a plain value because it is resolved from
somewhere else and cached, and a cached authorization answer that cannot say
how old it is, is one nobody can reason about during an incident.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from finops_core.domain.fact import Fact
from finops_core.domain.tenant import Scope


@dataclass(frozen=True, kw_only=True)
class Principal:
    principal_id: str
    display_name: str
    tenant_id: UUID
    groups: frozenset[str]


@dataclass(frozen=True, kw_only=True)
class Entitlement(Fact):
    """The scope a principal held at `as_of`."""

    principal: Principal
    scope: Scope
