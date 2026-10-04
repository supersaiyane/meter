"""Anomaly narration: the anomaly's own figures, and every nearby change only a correlation.

TASK-P7-008. Each test is one of the plan's five criteria, plus the two checks that hold
them: the provenance rule every answer obeys, and a refusal of any word claiming a cause.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from finops_core.domain.insight import Provenance, bare_figures
from finops_query.narration import (
    CAUSAL,
    NOT_COLLECTED,
    AnomalyFacts,
    ChangeEvent,
    EventSource,
    assert_correlational,
    narrate,
)

DAY = date(2026, 9, 17)
DAY_START = datetime(2026, 9, 17, tzinfo=UTC)
ANOMALY = AnomalyFacts(
    anomaly_id="anomaly-7",
    sub_account_id="fake-platform-a",
    service_name="AmazonEC2",
    day=DAY,
    observed=Decimal("1480.25"),
    baseline=Decimal("412.10"),
    severity="HIGH",
    as_of=datetime(2026, 9, 18, 6, tzinfo=UTC),
)
EVERYTHING_READ: dict[EventSource, str | None] = dict.fromkeys(EventSource)


def event(
    source: EventSource, hours_before: float, what: str = "instance type changed"
) -> ChangeEvent:
    return ChangeEvent(
        source=source,
        event_id=f"{source.value}-{hours_before}",
        at=DAY_START - timedelta(hours=hours_before),
        resource="i-0a1b2c3d4e5f60718",
        what=what,
    )


def test_the_anomaly_and_its_figures_are_the_rows_own_unchanged() -> None:
    narration = narrate(ANOMALY, (), EVERYTHING_READ)

    cited = {c.placeholder: c for c in narration.answer.citations}
    assert cited["observed"].value == ANOMALY.observed
    assert cited["baseline"].value == ANOMALY.baseline
    assert cited["severity"].value == "HIGH"
    assert all(c.call_id == "anomaly-7" for c in narration.answer.citations)
    assert all(c.provenance is Provenance.MEASURED for c in narration.answer.citations)


def test_every_correlation_carries_its_source_and_distance_nearest_first() -> None:
    events = (
        event(EventSource.CLOUDTRAIL, 30),
        event(EventSource.DEPLOY, 2.5, "release of the api"),
        event(EventSource.CONFIG, -3),
        event(EventSource.CONFIG, 72),  # outside the window, so not a correlation at all
    )

    narration = narrate(ANOMALY, events, EVERYTHING_READ)

    assert [(c.event.source, c.lead) for c in narration.correlations] == [
        (EventSource.DEPLOY, timedelta(hours=2.5)),
        (EventSource.CONFIG, timedelta(hours=-3)),
        (EventSource.CLOUDTRAIL, timedelta(hours=30)),
    ]
    hours = {
        c.placeholder: c.value
        for c in narration.answer.citations
        if c.placeholder.startswith("hours")
    }
    assert hours == {"hours1": Decimal("2.5"), "hours2": Decimal("3.0"), "hours3": Decimal("30.0")}
    assert "into that day" in narration.answer.prose


def test_the_prose_says_correlated_and_never_caused() -> None:
    narration = narrate(
        ANOMALY, (event(EventSource.DEPLOY, 1), event(EventSource.CONFIG, 5)), EVERYTHING_READ
    )

    prose = narration.answer.prose.lower()
    assert prose.count("correlated, and not shown to be the cause") == 2
    assert not [word for word in CAUSAL if word in prose]


def test_an_anomaly_with_nothing_near_it_says_so_rather_than_guessing() -> None:
    narration = narrate(ANOMALY, (), EVERYTHING_READ)

    assert narration.correlations == ()
    assert "No change recorded by Config, CloudTrail or deploy" in narration.answer.prose
    assert "points to a cause" in narration.answer.prose


def test_an_unread_source_is_said_to_be_unread_and_never_reported_as_quiet() -> None:
    """The distinction the topology coverage makes, between empty and unread."""
    readings = {
        EventSource.CONFIG: "AccessDenied reading the aggregator",
        EventSource.CLOUDTRAIL: None,
        EventSource.DEPLOY: None,
    }

    narration = narrate(ANOMALY, (event(EventSource.CONFIG, 1),), readings)

    prose = narration.answer.prose
    assert "Config history could not be read" in prose
    assert "No change recorded by CloudTrail or deploy" in prose
    assert "Config," not in prose.split("No change recorded by")[1]
    assert narration.correlations == (), "an event from an unread source is not evidence"
    assert narration.unread == ((EventSource.CONFIG, "AccessDenied reading the aggregator"),)


def test_a_source_nothing_reads_yet_is_unread_by_default() -> None:
    narration = narrate(ANOMALY, (), {EventSource.DEPLOY: None})

    assert {source for source, _ in narration.unread} == {
        EventSource.CONFIG,
        EventSource.CLOUDTRAIL,
    }
    assert all(reason == NOT_COLLECTED for _, reason in narration.unread)


def test_a_narration_obeys_the_rule_every_answer_obeys() -> None:
    """Resource identifiers hold digits, so they are labels behind placeholders too."""
    narration = narrate(ANOMALY, (event(EventSource.CONFIG, 4),), EVERYTHING_READ)

    assert bare_figures(narration.answer.prose) == ()
    resource = next(c for c in narration.answer.citations if c.placeholder == "resource1")
    assert resource.value == "i-0a1b2c3d4e5f60718"
    assert not resource.is_figure


@pytest.mark.parametrize(
    "claim", ["This was caused by the deploy.", "It rose because of a release."]
)
def test_a_sentence_claiming_a_cause_is_refused(claim: str) -> None:
    with pytest.raises(ValueError, match="claims a cause"):
        assert_correlational(claim)
