"""The P3 invariants, watched refusing.

Constraint 11: if application code is the only thing preventing a bad row, the bad
row will eventually exist. A check constraint nobody has watched refuse anything is
in the same position as the code it was meant to back up, because a constraint with
a typo in it accepts everything and looks exactly like one that works.

Every case here inserts a row the schema should reject and asserts the rejection,
naming the constraint so the failure says which rule was lost.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 21, 6, 0, tzinfo=UTC)
ACCOUNT = "111122223333"

BEFORE_START = date(2026, 6, 1)
BEFORE_END = date(2026, 7, 1)
AFTER_START = date(2026, 7, 31)
AFTER_END = date(2026, 8, 30)

INSERT_RECOMMENDATION = text(
    "INSERT INTO recommendation (recommendation_id, tenant_id, sub_account_id, source, "
    "source_reference, waste_class, resource_id, region_id, estimated_monthly_saving, "
    "confidence, severity, observation_days, lifecycle, rationale, as_of, collected_at) "
    "VALUES (:id, :t, :account, :source, :ref, 'RIGHTSIZE_INSTANCE', 'i-fixture', "
    "'eu-west-1', :saving, :confidence, 'HIGH', :days, :lifecycle, :rationale, :at, :at)"
)

INSERT_EVENT = text(
    "INSERT INTO recommendation_event (event_id, recommendation_id, tenant_id, "
    "from_lifecycle, to_lifecycle, actor, reason, occurred_at, as_of, collected_at) "
    "VALUES (:e, :id, :t, :from, :to, 'test', :reason, :at, :at, :at)"
)

INSERT_REALIZED = text(
    "INSERT INTO realized_saving (realized_id, recommendation_id, tenant_id, "
    "window_before_start, window_before_end, window_after_start, window_after_end, "
    "cost_before, cost_after, usage_before, usage_after, verdict, why, as_of, collected_at) "
    "VALUES (:id, :recommendation, :t, :b_start, :b_end, :a_start, :a_end, :cost_before, "
    ":cost_after, :usage_before, :usage_after, :verdict, :why, :at, :at)"
)


def recommendation(connection: Connection, tenant: UUID, **overrides: object) -> UUID:
    """One valid recommendation, with any field overridden.

    Written as a valid row with overrides rather than as one literal per case, so a
    case that fails proves the override was the reason and not a typo elsewhere.
    """
    identifier = uuid4()
    values: dict[str, object] = {
        "id": identifier,
        "t": tenant,
        "account": ACCOUNT,
        "source": "METER",
        "ref": f"ref:{identifier}",
        "saving": Decimal("100.00"),
        "confidence": "HIGH",
        "days": 30,
        "lifecycle": "OPEN",
        "rationale": "a rationale a reader can argue with",
        "at": NOW,
    }
    values.update(overrides)
    connection.execute(INSERT_RECOMMENDATION, values)
    return identifier


def realized(
    connection: Connection, tenant: UUID, recommendation_id: UUID, **overrides: object
) -> None:
    values: dict[str, object] = {
        "id": uuid4(),
        "recommendation": recommendation_id,
        "t": tenant,
        "b_start": BEFORE_START,
        "b_end": BEFORE_END,
        "a_start": AFTER_START,
        "a_end": AFTER_END,
        "cost_before": Decimal("100.00"),
        "cost_after": Decimal("60.00"),
        "usage_before": Decimal("720"),
        "usage_after": Decimal("720"),
        "verdict": "VERIFIED",
        "why": "the working",
        "at": NOW,
    }
    values.update(overrides)
    connection.execute(INSERT_REALIZED, values)


class TestTheRecommendationTable:
    def test_the_observation_floor(self, engine: Engine, tenant_id: UUID) -> None:
        """Thirteen days is refused, fourteen is not.

        Below the floor a new instance looks exactly like an idle one, and the row
        should not exist at all rather than existing with a low confidence.
        """
        with pytest.raises(IntegrityError, match="observation_floor"), engine.begin() as connection:
            recommendation(connection, tenant_id, days=13)
        with engine.begin() as connection:
            recommendation(connection, tenant_id, days=14)

    def test_a_negative_saving(self, engine: Engine, tenant_id: UUID) -> None:
        # A cost increase is not a recommendation, and a negative here would
        # subtract from a total somebody reports upward.
        with (
            pytest.raises(IntegrityError, match="saving_not_negative"),
            engine.begin() as connection,
        ):
            recommendation(connection, tenant_id, saving=Decimal("-1.00"))

    def test_a_source_nobody_implemented(self, engine: Engine, tenant_id: UUID) -> None:
        with pytest.raises(IntegrityError, match="source_known"), engine.begin() as connection:
            recommendation(connection, tenant_id, source="SOME_VENDOR")

    def test_a_lifecycle_nobody_implemented(self, engine: Engine, tenant_id: UUID) -> None:
        with pytest.raises(IntegrityError, match="lifecycle_known"), engine.begin() as connection:
            recommendation(connection, tenant_id, lifecycle="MAYBE")

    def test_an_empty_rationale(self, engine: Engine, tenant_id: UUID) -> None:
        """A recommendation a reader cannot argue with is one they take on trust.

        Nobody takes a cost recommendation on trust twice, so the working is a NOT
        NULL with a length check rather than a convention.
        """
        with pytest.raises(IntegrityError, match="has_working"), engine.begin() as connection:
            recommendation(connection, tenant_id, rationale="")

    def test_the_same_finding_twice_from_the_same_source(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        # What stops a screen showing the same oversized instance once per
        # collection. A re read updates rather than duplicating.
        with engine.begin() as connection:
            recommendation(connection, tenant_id, ref="the-same-reference")
        with (
            pytest.raises(IntegrityError, match="uq_recommendation__source"),
            engine.begin() as connection,
        ):
            recommendation(connection, tenant_id, ref="the-same-reference")


class TestTheEventLog:
    def test_only_the_first_event_has_no_from(self, engine: Engine, tenant_id: UUID) -> None:
        """`from_lifecycle` is null exactly once per recommendation.

        That is the row recording that it was found. Every later transition names
        where it came from, which is what lets the log be replayed rather than
        merely listed.
        """
        with engine.begin() as connection:
            identifier = recommendation(connection, tenant_id)
        with pytest.raises(IntegrityError, match="first_has_no_from"), engine.begin() as connection:
            connection.execute(
                INSERT_EVENT,
                {
                    "e": uuid4(),
                    "id": identifier,
                    "t": tenant_id,
                    "from": None,
                    "to": "ACCEPTED",
                    "reason": None,
                    "at": NOW,
                },
            )

    def test_a_dismissal_without_a_reason(self, engine: Engine, tenant_id: UUID) -> None:
        # The one transition where the reason is the entire point. Refused by the
        # route, by the service and here.
        with engine.begin() as connection:
            identifier = recommendation(connection, tenant_id)
        with (
            pytest.raises(IntegrityError, match="dismissal_has_a_reason"),
            engine.begin() as connection,
        ):
            connection.execute(
                INSERT_EVENT,
                {
                    "e": uuid4(),
                    "id": identifier,
                    "t": tenant_id,
                    "from": "OPEN",
                    "to": "DISMISSED",
                    "reason": None,
                    "at": NOW,
                },
            )


class TestTheRealizedSavingTable:
    def test_one_verdict_per_recommendation(self, engine: Engine, tenant_id: UUID) -> None:
        """A second would be a second claim about the same change.

        A screen summing them would double the saving, which is the specific way
        this metric gets inflated.
        """
        with engine.begin() as connection:
            identifier = recommendation(connection, tenant_id)
            realized(connection, tenant_id, identifier)
        with (
            pytest.raises(IntegrityError, match="uq_realized_saving__recommendation"),
            engine.begin() as connection,
        ):
            realized(connection, tenant_id, identifier)

    def test_overlapping_windows(self, engine: Engine, tenant_id: UUID) -> None:
        # An after window starting before the before window ends would compare a
        # period partly with itself.
        with engine.begin() as connection:
            identifier = recommendation(connection, tenant_id)
        with pytest.raises(IntegrityError, match="windows_ordered"), engine.begin() as connection:
            realized(connection, tenant_id, identifier, a_start=date(2026, 6, 15))

    def test_a_verdict_nobody_implemented(self, engine: Engine, tenant_id: UUID) -> None:
        with engine.begin() as connection:
            identifier = recommendation(connection, tenant_id)
        with (
            pytest.raises(IntegrityError, match="realized_saving__verdict"),
            engine.begin() as connection,
        ):
            realized(connection, tenant_id, identifier, verdict="PROBABLY")

    @pytest.mark.parametrize("verdict", ["VERIFIED", "REGRESSED"])
    def test_an_unobserved_control_cannot_be_anything_but_inconclusive(
        self, engine: Engine, tenant_id: UUID, verdict: str
    ) -> None:
        """Migration `0012`, and the reason it exists.

        Widening the usage columns to nullable without this check would leave
        VERIFIED reachable with no control behind it, which is a saving nobody
        measured. REGRESSED is refused too: that verdict is decided on cost alone
        and never needs the usage columns, so a null there is a collector that lost
        the figure rather than one that never had it.
        """
        with engine.begin() as connection:
            identifier = recommendation(connection, tenant_id)
        with (
            pytest.raises(IntegrityError, match="unobserved_is_never_verified"),
            engine.begin() as connection,
        ):
            realized(
                connection,
                tenant_id,
                identifier,
                usage_before=None,
                usage_after=None,
                verdict=verdict,
            )

    def test_an_unobserved_control_with_an_inconclusive_verdict_is_accepted(
        self, engine: Engine, tenant_id: UUID
    ) -> None:
        # The other direction. A constraint that refused every null would have made
        # the widening pointless, so the allowed case is watched as well.
        with engine.begin() as connection:
            identifier = recommendation(connection, tenant_id)
            realized(
                connection,
                tenant_id,
                identifier,
                usage_before=None,
                usage_after=None,
                verdict="INCONCLUSIVE",
            )

    def test_a_negative_cost(self, engine: Engine, tenant_id: UUID) -> None:
        # A negative here is a parse failure that reached the database, and it
        # would subtract from a total reported upward.
        with engine.begin() as connection:
            identifier = recommendation(connection, tenant_id)
        with (
            pytest.raises(IntegrityError, match="money_not_negative"),
            engine.begin() as connection,
        ):
            realized(connection, tenant_id, identifier, cost_after=Decimal("-1.00"))

    def test_an_empty_working(self, engine: Engine, tenant_id: UUID) -> None:
        with engine.begin() as connection:
            identifier = recommendation(connection, tenant_id)
        with (
            pytest.raises(IntegrityError, match="realized_saving__has_working"),
            engine.begin() as connection,
        ):
            realized(connection, tenant_id, identifier, why="")
