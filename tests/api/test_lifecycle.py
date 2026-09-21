"""The two guards a route makes unreachable, called directly.

`finops_api/routes/waste.py` reads through the scoped repository before it moves
anything, and FastAPI refuses a blank `reason` at the query string. So neither of
these branches can be reached through the HTTP surface, which is exactly why they
need a test of their own: a guard with no test is a guard that stops working
quietly the day somebody adds a second caller.

Constraint 3's reasoning, applied one layer down. A rule enforced in one place is
a rule that holds until the second place exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text

from finops_api.lifecycle import TransitionRefusedError, move
from finops_core.domain.waste import Lifecycle
from finops_fakes.recommendations import FakeRecommendationSource
from finops_ingest.collectors.recommendations import RecommendationCollector
from finops_ingest.registry import CollectorContext

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 21, 6, 0, tzinfo=UTC)


@dataclass(frozen=True)
class Unit:
    tenant_id: UUID


def one_recommendation(engine: Engine, tenant: UUID) -> UUID:
    with engine.begin() as connection:
        RecommendationCollector(FakeRecommendationSource(), clock=lambda: NOW)(
            CollectorContext(unit=Unit(tenant_id=tenant), connection=connection, run_id=uuid4())
        )
        found = connection.execute(
            text("SELECT recommendation_id FROM recommendation WHERE tenant_id = :t LIMIT 1"),
            {"t": tenant},
        ).scalar_one()
    assert isinstance(found, UUID)
    return found


def test_a_recommendation_in_another_tenant_is_refused(engine: Engine, tenant_id: UUID) -> None:
    """Absent and out of scope give the same refusal, on purpose.

    A caller able to tell them apart could enumerate another tenant's
    recommendations by trying ids until the message changed.
    """
    one_recommendation(engine, tenant_id)
    with (
        engine.begin() as connection,
        pytest.raises(TransitionRefusedError, match="no such recommendation in this scope"),
    ):
        move(
            connection,
            tenant_id=uuid4(),
            recommendation_id=uuid4(),
            target=Lifecycle.ACCEPTED,
            actor="test",
            owner="alice",
        )


@pytest.mark.parametrize("reason", [None, "", "   "])
def test_a_dismissal_without_a_reason_is_refused_here_too(
    engine: Engine, tenant_id: UUID, reason: str | None
) -> None:
    # Whitespace included. A reason of three spaces satisfies the database's
    # `length(reason) > 0` and tells a reviewer nothing.
    identifier = one_recommendation(engine, tenant_id)
    with (
        engine.begin() as connection,
        pytest.raises(TransitionRefusedError, match="a dismissal needs a reason"),
    ):
        move(
            connection,
            tenant_id=tenant_id,
            recommendation_id=identifier,
            target=Lifecycle.DISMISSED,
            actor="test",
            reason=reason,
        )
