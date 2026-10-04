"""A digest, composed: the sentences each kind of week gets, and the week it covers.

TASK-P7-012. The collector's tests prove the figures equal the bill's. These pin the prose:
every digest obeys the rule every answer obeys, a missing week is not drawn as zero, and
spend no team claims is never named as if it were a team.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from finops_core.domain.insight import bare_figures
from finops_core.domain.platform import UNALLOCATED
from finops_query.digest import Audience, WeekOfSpend, compose, last_complete_week

AS_OF = datetime(2026, 7, 20, 6, 0, tzinfo=UTC)


def week(**overrides: Any) -> WeekOfSpend:
    fields: dict[str, Any] = {
        "audience": Audience.TEAM,
        "team": "payments",
        "week_start": date(2026, 7, 13),
        "week_end": date(2026, 7, 19),
        "spend": Decimal("1840.20"),
        "spend_as_of": AS_OF,
        "previous": Decimal("1610.75"),
        "previous_as_of": AS_OF,
        "top_service": "AmazonEC2",
        "top_service_spend": Decimal("905.10"),
        "top_as_of": AS_OF,
    }
    fields.update(overrides)
    return WeekOfSpend(**fields)


def cited(**overrides: Any) -> dict[str, Decimal | str]:
    return {c.placeholder: c.value for c in compose(week(**overrides)).citations}


def test_a_team_digest_cites_every_figure_and_names_its_team() -> None:
    answer = compose(week())

    assert bare_figures(answer.prose) == ()
    assert cited() == {
        "week_end": "2026-07-19",
        "spend": Decimal("1840.20"),
        "team": "payments",
        "previous": Decimal("1610.75"),
        "service": "AmazonEC2",
        "service_spend": Decimal("905.10"),
    }


def test_a_week_with_nothing_before_it_is_not_compared_with_zero() -> None:
    answer = compose(week(previous=None, previous_as_of=None))

    assert "previous" not in {c.placeholder for c in answer.citations}
    assert "nothing billed the week before" in answer.prose


def test_spend_no_team_claims_is_not_named_as_a_team() -> None:
    answer = compose(week(team=UNALLOCATED))

    assert "spend no team tag claims" in answer.prose
    assert "team" not in {c.placeholder for c in answer.citations}


def test_the_organizations_digest_names_no_team() -> None:
    answer = compose(week(audience=Audience.EXECUTIVE, team=None))

    assert "the organization spent" in answer.prose
    assert "team" not in {c.placeholder for c in answer.citations}


def test_a_week_with_no_largest_service_says_nothing_about_one() -> None:
    answer = compose(week(top_service=None, top_service_spend=None, top_as_of=None))
    assert "largest service" not in answer.prose


def test_the_week_is_the_last_one_that_has_ended() -> None:
    """Monday to Sunday in UTC. On a Sunday the week still running is not complete."""
    assert last_complete_week(datetime(2026, 7, 20, 6, tzinfo=UTC)) == (
        date(2026, 7, 13),
        date(2026, 7, 19),
    )
    assert last_complete_week(datetime(2026, 7, 19, 23, tzinfo=UTC)) == (
        date(2026, 7, 6),
        date(2026, 7, 12),
    )
