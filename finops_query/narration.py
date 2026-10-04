"""A detected anomaly, explained by what changed near it and never by what caused it.

TASK-P7-008 and FEAT-039, P7 spec section 2. `cost_anomaly` found a day that did not look
like the days before it, and that finding is deterministic and right, so a reader already
trusts the row. A narration saying "caused by the deployment at 14:02" would borrow that
trust for a claim nothing verified. So every event near the anomaly is a correlation,
labelled as one with its source and its distance in time, and the prose says correlated
and never caused, held by a check on the words rather than by care.

**The figures are the anomaly's own,** cited from the row unchanged, under the same rule as
an answer: no figure in the prose, a placeholder and a citation instead. The narration
computes one thing, the distance between two timestamps, and both are measured.

**An absence is said, and an unread source is not an absence.** An anomaly with nothing
near it gets a sentence saying so. A source that could not be read gets a sentence saying
that, and never the sentence about absence, which is the distinction the topology coverage
makes between an empty account and one nobody could read.

**In this cut the narration is composed here, and no model writes it.** The acceptance
criteria are all properties of the sentences, so a template meets them exactly, and a
model pass that rephrased them would have to keep every placeholder and pass both checks.
Adding one changes nothing in this module's guarantees.

**Nothing collects change history yet.** The events are an input and the caller says which
sources it read. Until a collector reads Config and CloudTrail, every caller passes those as
unread with `NOT_COLLECTED`, and the narration says so rather than reporting a quiet week.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from enum import StrEnum

from finops_core.domain.insight import Answer, Citation, Provenance

#: How far before the anomaly's day a change is looked for. A change late the evening
#: before is billed the next day, and one made on a Friday is first billed in full over a
#: weekend, so two days back catches both without reaching into last week.
WINDOW = timedelta(hours=48)

#: Words that claim a cause. None may appear in a narration, whoever wrote it.
CAUSAL = ("caused", "causing", "because", "due to", "led to", "resulted", "drove", "triggered")

#: What a caller passes for a source nothing reads yet.
NOT_COLLECTED = "no collector reads this history yet"

#: Where a narration's own arithmetic is cited from.
NARRATION = "narration"


class EventSource(StrEnum):
    CONFIG = "config"
    CLOUDTRAIL = "cloudtrail"
    DEPLOY = "deploy"


SOURCE_NAMES = {
    EventSource.CONFIG: "Config",
    EventSource.CLOUDTRAIL: "CloudTrail",
    EventSource.DEPLOY: "deploy",
}


@dataclass(frozen=True)
class AnomalyFacts:
    """The `cost_anomaly` row, as it was stored."""

    anomaly_id: str
    sub_account_id: str
    service_name: str
    day: date
    observed: Decimal
    baseline: Decimal
    severity: str
    as_of: datetime


@dataclass(frozen=True)
class ChangeEvent:
    """Something that changed, from one source, at one time."""

    source: EventSource
    event_id: str
    at: datetime
    resource: str
    what: str


@dataclass(frozen=True)
class Correlation:
    """An event near the anomaly. A guess about a cause, and labelled as one."""

    event: ChangeEvent
    #: How long before the anomaly's day began. Negative is a change during the day.
    lead: timedelta


@dataclass(frozen=True)
class Narration:
    """The explanation, the correlations behind it, and the sources nobody could read."""

    anomaly_id: str
    answer: Answer
    correlations: tuple[Correlation, ...]
    #: Each unread source, with why. Shown beside the prose rather than in it, because a
    #: reason may hold an account number and the prose may hold no figure.
    unread: tuple[tuple[EventSource, str], ...]


def assert_correlational(prose: str) -> None:
    """Refuse a narration that claims a cause.

    Raises:
        ValueError: Naming the word, which is ours to repeat because it is on this list.
    """
    lowered = prose.lower()
    for word in CAUSAL:
        if word in lowered:
            raise ValueError(f"a narration claims a cause with {word!r}, which nothing verified")


def narrate(
    anomaly: AnomalyFacts,
    events: Sequence[ChangeEvent],
    readings: Mapping[EventSource, str | None],
) -> Narration:
    """Explain `anomaly` by the events near it.

    `readings` says, per source, None where it was read and the reason where it could not
    be. A source missing from it was not read, and is said to be.
    """
    unread = tuple(
        (source, readings.get(source) or NOT_COLLECTED)
        for source in EventSource
        if source not in readings or readings[source] is not None
    )
    unreadable = {source for source, _ in unread}
    day_start = datetime.combine(anomaly.day, time.min, tzinfo=UTC)
    day_end = day_start + timedelta(days=1)
    nearby = sorted(
        (
            event
            for event in events
            if event.source not in unreadable and day_start - WINDOW <= event.at < day_end
        ),
        key=lambda event: abs(day_start - event.at),
    )
    correlations = tuple(Correlation(event=event, lead=day_start - event.at) for event in nearby)

    parts = [
        "On {{day}}, {{service}} in {{account}} cost {{observed}} against a usual "
        "{{baseline}}, which the detector rated {{severity}}."
    ]
    citations = _anomaly_citations(anomaly)
    for index, correlation in enumerate(correlations, start=1):
        sentence, cited = _correlation(index, correlation)
        parts.append(sentence)
        citations.extend(cited)
    parts.extend(_absences(correlations, unread))

    prose = " ".join(parts)
    assert_correlational(prose)
    return Narration(
        anomaly_id=anomaly.anomaly_id,
        answer=Answer(prose=prose, citations=tuple(citations)),
        correlations=correlations,
        unread=unread,
    )


def _anomaly_citations(anomaly: AnomalyFacts) -> list[Citation]:
    def cite(placeholder: str, field: str, value: Decimal | str) -> Citation:
        return Citation(
            placeholder=placeholder,
            tool="cost_anomaly",
            call_id=anomaly.anomaly_id,
            field=field,
            value=value,
            provenance=Provenance.MEASURED,
            as_of=anomaly.as_of,
        )

    return [
        cite("day", "day", anomaly.day.isoformat()),
        cite("service", "service_name", anomaly.service_name),
        cite("account", "sub_account_id", anomaly.sub_account_id),
        cite("observed", "observed", anomaly.observed),
        cite("baseline", "baseline", anomaly.baseline),
        cite("severity", "severity", anomaly.severity),
    ]


def _correlation(index: int, correlation: Correlation) -> tuple[str, list[Citation]]:
    event = correlation.event
    when = "before that day began" if correlation.lead >= timedelta(0) else "into that day"
    hours = (Decimal(str(abs(correlation.lead).total_seconds())) / 3600).quantize(Decimal("0.1"))
    sentence = (
        f"Correlated, and not shown to be the cause: a {SOURCE_NAMES[event.source]} change, "
        f"{{{{what{index}}}}} on {{{{resource{index}}}}}, {{{{hours{index}}}}} hours {when}."
    )

    def cite(placeholder: str, tool: str, field: str, value: Decimal | str) -> Citation:
        return Citation(
            placeholder=placeholder,
            tool=tool,
            call_id=event.event_id,
            field=field,
            value=value,
            provenance=Provenance.MEASURED,
            as_of=event.at,
        )

    return sentence, [
        cite(f"what{index}", event.source.value, "what", event.what),
        cite(f"resource{index}", event.source.value, "resource", event.resource),
        cite(f"hours{index}", NARRATION, "hours between the change and the day", hours),
    ]


def _absences(
    correlations: tuple[Correlation, ...], unread: tuple[tuple[EventSource, str], ...]
) -> list[str]:
    sentences = [
        f"{SOURCE_NAMES[source]} history could not be read, so finding no change there "
        f"says nothing."
        for source, _ in unread
    ]
    read = [SOURCE_NAMES[source] for source in EventSource if source not in dict(unread)]
    if not correlations and read:
        sentences.append(
            f"No change recorded by {_listed(read)} falls in the window searched before it, "
            f"so nothing here points to a cause."
        )
    return sentences


def _listed(names: list[str]) -> str:
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} or {names[-1]}"
