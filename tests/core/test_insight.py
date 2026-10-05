"""The answer that cannot hold a figure it did not cite, and its two siblings.

TASK-P7-002. Every test here is one way a number could reach a reader without a
source, refused at construction. The loop in `finops_query/insight.py` checks the
same things, and these exist so a route that builds an `Answer` itself cannot skip it.
"""

from __future__ import annotations

from dataclasses import fields
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from finops_core.constants import REASON_MIN_LENGTH
from finops_core.domain.insight import (
    CAUSES,
    Answer,
    Citation,
    Failure,
    Gap,
    Outcome,
    Provenance,
    ProvenanceError,
    Refusal,
    Unit,
    bare_figures,
)
from finops_core.errors import CollectionError, NotOptedIn

AS_OF = datetime(2026, 10, 3, 0, 0, tzinfo=UTC)


def citation(**overrides: Any) -> Citation:
    fields_: dict[str, Any] = {
        "placeholder": "total",
        "tool": "get_cost_by_service",
        "call_id": "t1",
        "field": "data[service=AmazonEC2].billed_cost",
        "value": Decimal("4123.50"),
        "unit": Unit.USD,
        "provenance": Provenance.MEASURED,
        "as_of": AS_OF,
    }
    fields_.update(overrides)
    return Citation(**fields_)


# --- no figure without a citation -------------------------------------------------


@pytest.mark.parametrize(
    "prose",
    [
        "Compute cost 4123 dollars this month.",
        "Compute cost about four thousand dollars.",
        "Spend fell by half.",
        "Thousands went on storage.",
        # The same figure in another script, as a superscript and as a fraction.
        "Compute cost ٤١٢٣ dollars.",
        "Compute grew by a factor of ².",
        "Storage is ½ of the bill.",
    ],
)
def test_prose_holding_a_figure_outside_a_placeholder_cannot_be_constructed(prose: str) -> None:
    with pytest.raises(ProvenanceError, match="no citation placed"):
        Answer(prose=prose, citations=())


def test_the_refusal_counts_the_figures_and_never_repeats_them() -> None:
    """The message becomes a stored failure detail, and the figure may be a secret's digits."""
    with pytest.raises(ProvenanceError) as refused:
        Answer(prose="Your key is AKIA5521EXAMPLE.", citations=())
    assert "5521" not in str(refused.value)
    assert "4 of them" in str(refused.value)


def test_the_spec_example_of_the_failure_is_refused() -> None:
    """Spec section 1. It contains no digit, which is why digits are not enough."""
    assert bare_figures("It cost about forty thousand dollars.") == ("forty", "thousand")


def test_a_digit_inside_a_placeholder_says_nothing_about_a_value() -> None:
    answer = Answer(
        prose="The largest service cost {{c1}}.",
        citations=(citation(placeholder="c1"),),
    )
    assert answer.citations[0].value == Decimal("4123.50")


def test_ordinary_prose_is_not_mistaken_for_a_figure() -> None:
    """`tenant` holds `ten` and `one of` holds `one`. Neither is a count."""
    assert bare_figures("One of the tenant's accounts is often the largest.") == ()


def test_a_label_whose_name_holds_a_digit_goes_in_a_placeholder() -> None:
    """EC2 and eu-west-1 hold digits, so the prose cannot name them directly."""
    with pytest.raises(ProvenanceError, match="no citation placed"):
        Answer(prose="EC2 cost the most.", citations=())
    answer = Answer(
        prose="{{svc}} cost the most, at {{total}}.",
        citations=(citation(placeholder="svc", value="AmazonEC2", unit=None), citation()),
    )
    assert {c.placeholder: c.is_figure for c in answer.citations} == {"svc": False, "total": True}


# --- placeholders and citations, matched both ways ---------------------------------


def test_a_placeholder_with_no_citation_cannot_be_constructed() -> None:
    with pytest.raises(ProvenanceError, match="with no citation: total"):
        Answer(prose="Compute cost {{total}}.", citations=())


def test_a_citation_no_placeholder_uses_cannot_be_constructed() -> None:
    with pytest.raises(ProvenanceError, match="no placeholder uses: total"):
        Answer(prose="Compute cost the most.", citations=(citation(),))


def test_two_citations_cannot_claim_one_placeholder() -> None:
    with pytest.raises(ProvenanceError, match="claim one placeholder"):
        Answer(prose="Compute cost {{total}}.", citations=(citation(), citation()))


def test_a_placeholder_may_be_used_twice_and_cited_once() -> None:
    answer = Answer(prose="{{total}}, and again {{total}}.", citations=(citation(),))
    assert len(answer.citations) == 1


@pytest.mark.parametrize("prose", ["Compute cost {{ total }}.", "Compute cost {total}."])
def test_a_broken_placeholder_cannot_reach_the_reader_as_braces(prose: str) -> None:
    with pytest.raises(ProvenanceError):
        Answer(prose=prose, citations=())


def test_an_answer_with_no_prose_answers_nothing() -> None:
    with pytest.raises(ProvenanceError, match="answers nothing"):
        Answer(prose="  ", citations=())


# --- what a citation carries ------------------------------------------------------


def test_a_citation_without_its_provenance_flag_cannot_be_constructed() -> None:
    with pytest.raises(ProvenanceError, match="measured or modelled"):
        citation(provenance=None)
    with pytest.raises(ProvenanceError, match="measured or modelled"):
        citation(provenance="measured")


@pytest.mark.parametrize("missing", ["tool", "call_id", "field"])
def test_a_citation_without_its_source_cannot_be_traced(missing: str) -> None:
    with pytest.raises(ProvenanceError, match=f"without its {missing}"):
        citation(**{missing: " "})


def test_a_citation_has_a_time_zone_on_its_as_of() -> None:
    with pytest.raises(ProvenanceError, match="time zone"):
        citation(as_of=datetime(2026, 10, 3))


@pytest.mark.parametrize("value", [4123.5, True, None, Decimal("NaN"), Decimal("Infinity"), " "])
def test_a_cited_value_is_a_finite_decimal_or_a_label(value: object) -> None:
    with pytest.raises(ProvenanceError):
        citation(value=value)


def test_there_is_no_forecast_provenance_to_cite_under() -> None:
    """Spec section 3: the assistant does not forecast, so it cannot cite one."""
    assert {member.value for member in Provenance} == {"measured", "modelled"}


# --- what a figure counts, ISS-231 ------------------------------------------------


def test_the_units_are_the_two_a_figure_on_the_screen_is_drawn_in() -> None:
    """`Figure` in `finops-web` draws dollars or a count, and a third unit would reach it
    as something it cannot draw."""
    assert {member.value for member in Unit} == {"usd", "count"}


@pytest.mark.parametrize("unit", [None, "usd", "dollars"])
def test_a_figure_without_one_of_the_two_units_cannot_be_constructed(unit: object) -> None:
    """Not defaulted to dollars and not read from the field's name. A plain string is
    refused too, as a plain string is refused for the provenance flag."""
    with pytest.raises(ProvenanceError, match="figure with no unit"):
        citation(unit=unit)


def test_a_label_carries_no_unit() -> None:
    with pytest.raises(ProvenanceError, match="a label has no unit"):
        citation(placeholder="svc", value="AmazonEC2", unit=Unit.COUNT)


def test_a_figure_is_stored_with_its_unit_and_a_label_with_none() -> None:
    figure = citation(unit=Unit.COUNT, value=Decimal("0.4000"))
    label = citation(placeholder="svc", value="AmazonEC2", unit=None)

    assert (figure.as_record()["unit"], figure.as_record()["value"]) == ("count", "0.4000")
    assert "unit" not in label.as_record()


# --- the refusal, and the three outcomes ------------------------------------------


def test_a_refusal_reason_is_at_least_the_shared_floor() -> None:
    """The constant the quota rule and its column use, not a second literal."""
    with pytest.raises(ValueError, match=str(REASON_MIN_LENGTH)):
        Refusal(gap=Gap.TOOL, reason="x" * (REASON_MIN_LENGTH - 1))
    assert Refusal(gap=Gap.TOOL, reason="x" * REASON_MIN_LENGTH).screen is None


def test_a_refusal_names_the_kind_of_thing_missing_and_where_it_would_show() -> None:
    with pytest.raises(ValueError, match="what kind"):
        Refusal(gap="tool", reason="There is no tool that forecasts spend.")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="screen path"):
        Refusal(gap=Gap.FIGURE, reason="Split cost allocation is off.", screen="cost page")
    refusal = Refusal(
        gap=Gap.FIGURE,
        reason="Split cost allocation is not enabled for this cluster.",
        screen="/cost/containers",
    )
    assert refusal.screen == "/cost/containers"


@pytest.mark.parametrize(
    "screen",
    [
        "//evil.example",
        "/\\evil.example",
        "/\t/evil.example",
        "/\n/evil.example",
        "javascript:alert(1)",
        "https://evil.example/cost",
        "",
        "/",
        "/cost/",
        "/Cost",
        "/cost?next=//evil.example",
        "/cost#top",
    ],
)
def test_a_refusal_links_only_to_a_plain_screen_path(screen: str) -> None:
    """The screen becomes a link, and every one of these reaches another site or no screen.
    Found by review on 2026-10-04: the earlier check admitted the first four."""
    with pytest.raises(ValueError, match="screen path"):
        Refusal(gap=Gap.FIGURE, reason="Split cost allocation is off.", screen=screen)


def test_answer_and_refusal_are_two_types_and_neither_holds_the_other() -> None:
    """Not one type with a nullable field. The plan's fifth criterion."""
    answer_fields = {item.name for item in fields(Answer)}
    refusal_fields = {item.name for item in fields(Refusal)}
    assert not issubclass(Answer, Refusal)
    assert not issubclass(Refusal, Answer)
    assert answer_fields.isdisjoint(refusal_fields)


def test_there_are_exactly_three_outcomes() -> None:
    assert {member.value for member in Outcome} == {"ANSWERED", "REFUSED", "FAILED"}


def test_a_failure_is_one_of_the_seven_causes_and_never_a_generic_one() -> None:
    assert len(CAUSES) == 7
    assert {cause.__name__ for cause in CollectionError.__subclasses__()} == CAUSES
    with pytest.raises(ValueError, match="is not one of"):
        Failure(cause="Unknown", detail="something went wrong")
    failure = Failure.from_error(NotOptedIn(scope_key="hub", collector="assistant"))
    assert failure.cause == "NotOptedIn"
    assert failure.detail, "with no detail the remediation stands in, never an empty string"


def test_every_insight_entity_is_frozen() -> None:
    with pytest.raises(Exception, match=r"frozen|cannot assign"):
        citation().value = Decimal(1)  # type: ignore[misc]
