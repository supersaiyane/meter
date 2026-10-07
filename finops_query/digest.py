"""A week of spend, said in sentences whose every figure is cited. FEAT-041.

TASK-P7-012, P7 spec sections 6.2 and 9. A digest is composed from the rows the allocation
screen shows, under the rule every answer obeys: no figure in the prose, a placeholder and
a citation instead, so a digest read in an inbox carries the same provenance as the screen.

**Composed here, and no model writes it.** Summarization is one of the model's four roles
under ADR-0007, and a rephrasing pass may come later. It would have to keep every
placeholder, and nothing in a digest's guarantees would change. Until then a template says
what the figures say and no more.

**A week with nothing before it says so.** Where the bill holds no spend for the week
before, the comparison is not drawn, because a missing week rendered as zero would show
every figure as growth from nothing.

**Spend no team tag claims is said as that,** never as a team called `unallocated`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from enum import StrEnum

from finops_core.constants import TEAM_TAG
from finops_core.domain.insight import Answer, Citation, Provenance, Unit
from finops_core.domain.platform import UNALLOCATED

#: Where a digest's figures are read from: the daily cost rows the allocation screen reads.
SOURCE = "cost_focus_daily"


class Audience(StrEnum):
    TEAM = "team"
    EXECUTIVE = "executive"


@dataclass(frozen=True)
class WeekOfSpend:
    """What the bill holds for one audience over one week, and over the week before."""

    audience: Audience
    #: The bill's `team` tag value, `unallocated` for spend no tag claims, None for the
    #: executive digest.
    team: str | None
    week_start: date
    #: The week's last day, inclusive.
    week_end: date
    spend: Decimal
    spend_as_of: datetime
    #: None where the week before holds no billed spend at all.
    previous: Decimal | None
    previous_as_of: datetime | None
    top_service: str | None
    top_service_spend: Decimal | None
    top_as_of: datetime | None


def last_complete_week(at: datetime) -> tuple[date, date]:
    """Monday to Sunday, the latest week that has ended by `at`, in UTC."""
    today = at.astimezone(UTC).date()
    start = today - timedelta(days=today.weekday() + 7)
    return start, start + timedelta(days=6)


def compose(week: WeekOfSpend) -> Answer:
    """The digest for one week, as prose with placeholders and the citations behind them."""
    reference = f"{week.audience.value}:{week.team or 'organization'}:{week.week_start}"

    def cite(
        placeholder: str, field: str, value: Decimal | str, as_of: datetime, *, unit: Unit | None
    ) -> Citation:
        return Citation(
            placeholder=placeholder,
            tool=SOURCE,
            call_id=reference,
            field=field,
            value=value,
            unit=unit,
            provenance=Provenance.MEASURED,
            as_of=as_of,
        )

    # Every figure a digest cites is effective cost summed, so dollars, and each says so
    # where it is cited rather than by a rule that a figure added later would inherit.
    citations = [
        cite(
            "week_end",
            "the week's last day",
            week.week_end.isoformat(),
            week.spend_as_of,
            unit=None,
        ),
        cite(
            "spend",
            "effective_cost summed over the week",
            week.spend,
            week.spend_as_of,
            unit=Unit.USD,
        ),
    ]
    if week.audience is Audience.EXECUTIVE:
        opening = "In the week to {{week_end}}, the organization spent {{spend}}"
    elif week.team == UNALLOCATED:
        opening = "In the week to {{week_end}}, spend no team tag claims came to {{spend}}"
    else:
        opening = "In the week to {{week_end}}, {{team}} spent {{spend}}"
        citations.append(
            cite("team", f"tags.{TEAM_TAG}", str(week.team), week.spend_as_of, unit=None)
        )

    if week.previous is not None and week.previous_as_of is not None:
        sentences = [f"{opening}, against {{{{previous}}}} the week before."]
        citations.append(
            cite(
                "previous",
                "effective_cost summed over the week before",
                week.previous,
                week.previous_as_of,
                unit=Unit.USD,
            )
        )
    else:
        sentences = [f"{opening}, and nothing billed the week before is held to compare it with."]

    if week.top_service and week.top_service_spend is not None and week.top_as_of is not None:
        sentences.append("The largest service was {{service}}, at {{service_spend}}.")
        citations.append(
            cite("service", "service_name", week.top_service, week.top_as_of, unit=None)
        )
        citations.append(
            cite(
                "service_spend",
                "effective_cost of that service over the week",
                week.top_service_spend,
                week.top_as_of,
                unit=Unit.USD,
            )
        )
    return Answer(prose=" ".join(sentences), citations=tuple(citations))
