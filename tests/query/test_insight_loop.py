"""The loop's own rules, one at a time, with an in memory toolbox and no database.

TASK-P7-006. The evaluation sets in `tests/query/insight/` judge the loop against the real
API. These pin each rule on its own, so a failure names the rule: where a cited value is
read from, which absences are refusals and which mistakes are failures, and that nothing a
model wrote is repeated back into a detail that will be stored.
"""

from __future__ import annotations

import ast
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from finops_core.domain.insight import Answer, Failure, Gap, Provenance, Refusal, Unit
from finops_core.ports.llm import (
    Completion,
    CompletionRequest,
    Message,
    Role,
    StopReason,
    TokenUsage,
    ToolSchema,
)
from finops_fakes.llm import ScriptedModel
from finops_query import insight
from finops_query.insight import (
    MAX_TOOL_ROUNDS,
    Exchange,
    ToolOutput,
    ToolUnavailableError,
    ask,
    parse_path,
)
from tests.query.insight.harness import answer, call, refuse

AS_OF = datetime(2026, 7, 31, tzinfo=UTC)
ROW_AS_OF = datetime(2026, 7, 30, tzinfo=UTC)
QUESTION = "What did compute cost?"


def envelope(
    data: Any, *, failures: tuple[Mapping[str, Any], ...] = (), as_of: datetime | None = AS_OF
) -> dict[str, Any]:
    return {
        "data": data,
        "meta": {
            "as_of": as_of,
            "collected_at": as_of,
            "scope_coverage": {"visible": 2, "total": 5, "unit": "accounts", "is_partial": True},
            "failures": failures,
        },
    }


#: What the fake tools declare for their numeric fields, as `finops_api/tools.py` does for the
#: real ones: by path, with row selectors taken out.
UNITS = {
    "data.effective_cost": Unit.USD,
    "data.line_items": Unit.COUNT,
    "data.cost": Unit.USD,
    "data.runs": Unit.COUNT,
    "data.change": Unit.USD,
    "data.total": Unit.USD,
    "data.clusters.total": Unit.USD,
    "data.clusters.workloads.cost": Unit.USD,
}


def output(data: Any, *, units: Mapping[str, Unit] = UNITS, **kwargs: Any) -> ToolOutput:
    return ToolOutput(
        envelope=envelope(data, **kwargs),
        text="a result",
        provenance=Provenance.MEASURED,
        units=units,
        screen="/cost",
    )


SERVICES = output(
    [
        {"name": "AmazonEC2", "effective_cost": Decimal("812.40"), "line_items": 40},
        {"name": "AmazonS3", "effective_cost": Decimal("96.10"), "line_items": 12},
    ]
)


class FakeToolbox:
    def __init__(self, **outputs: ToolOutput | ToolUnavailableError) -> None:
        self.outputs = outputs
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def schemas(self) -> tuple[ToolSchema, ...]:
        return tuple(ToolSchema(name=name, description=f"{name}.") for name in self.outputs)

    def call(self, name: str, arguments: Mapping[str, Any]) -> ToolOutput:
        self.calls.append((name, dict(arguments)))
        result = self.outputs[name]
        if isinstance(result, ToolUnavailableError):
            raise result
        return result


def run(
    *turns: Message, **outputs: ToolOutput | ToolUnavailableError
) -> tuple[Exchange, ScriptedModel]:
    model = ScriptedModel({QUESTION: turns})
    return ask(QUESTION, model=model, toolbox=FakeToolbox(**outputs)), model


def failed(exchange: Exchange) -> Failure:
    assert isinstance(exchange.outcome, Failure), exchange.outcome
    return exchange.outcome


def refused(exchange: Exchange) -> Refusal:
    assert isinstance(exchange.outcome, Refusal), exchange.outcome
    return exchange.outcome


# --- where a figure comes from -------------------------------------------------------


def test_the_cited_value_is_read_from_the_result_and_not_from_the_model() -> None:
    exchange, _ = run(
        call("t1", "services"),
        answer("Compute cost {{cost}}.", cost=("t1", "data[name=AmazonEC2].effective_cost")),
        services=SERVICES,
    )

    assert isinstance(exchange.outcome, Answer)
    (cost,) = exchange.outcome.citations
    assert (cost.value, cost.provenance, cost.as_of, cost.tool) == (
        Decimal("812.40"),
        Provenance.MEASURED,
        AS_OF,
        "services",
    )


def test_the_first_prompt_carries_the_question_and_the_tools_and_no_data() -> None:
    _, model = run(
        call("t1", "services"), refuse("tool", "Nothing here answers it."), services=SERVICES
    )

    first = model.received[0]
    assert first.messages == (Message(role=Role.USER, text=QUESTION),)
    assert [tool.name for tool in first.tools] == ["services", "answer", "refuse"]


def test_every_call_is_recorded_in_order_with_its_arguments() -> None:
    exchange, _ = run(
        call("t1", "services"),
        call("t2", "accounts"),
        refuse("scope", "Neither result holds what was asked about."),
        services=SERVICES,
        accounts=output([]),
    )

    assert [(r.call_id, r.tool, dict(r.arguments), r.returned) for r in exchange.tool_calls] == [
        ("t1", "services", {}, True),
        ("t2", "accounts", {}, True),
    ]


def test_spend_is_the_sum_of_every_turn() -> None:
    exchange, model = run(
        call("t1", "services"), refuse("tool", "Nothing answers it."), services=SERVICES
    )

    turns = [model.complete(request).usage for request in model.received]
    assert exchange.usage.total == sum(usage.total for usage in turns) > 0


# --- what fails, with a typed cause ---------------------------------------------------


def test_a_bare_numeral_fails_and_is_counted_rather_than_repeated() -> None:
    failure = failed(
        run(call("t1", "services"), answer("Compute cost 812.40."), services=SERVICES)[0]
    )

    assert failure.cause == "SchemaDrift"
    assert "no citation placed" in failure.detail
    assert "812" not in failure.detail


def test_a_figure_inside_a_models_own_refusal_fails() -> None:
    """A refusal is a sentence a reader sees, so it cannot carry the estimate it declines."""
    failure = failed(run(refuse("tool", "No tool for that, but it is about forty thousand."))[0])
    assert "carried a figure" in failure.detail


@pytest.mark.parametrize("gap", ["budget", "secret", "forecast"])
def test_a_model_cannot_claim_a_gap_only_the_loop_decides(gap: str) -> None:
    failure = failed(run(refuse(gap, "The budget for this month is spent."))[0])
    assert failure.cause == "SchemaDrift"


def test_a_model_refusal_too_short_to_read_fails() -> None:
    assert failed(run(refuse("tool", "No."))[0]).cause == "SchemaDrift"


def test_a_model_that_stops_without_finishing_fails() -> None:
    failure = failed(run(Message(role=Role.ASSISTANT, text="It looks fine to me."))[0])
    assert "without answering or refusing" in failure.detail


class CutOff:
    """A model that runs out of room on its first turn."""

    def complete(self, request: CompletionRequest) -> Completion:
        assert request.messages, "it was asked something before it ran out of room"
        return Completion(
            message=Message(role=Role.ASSISTANT, text="Compute cost {{c"),
            stop_reason=StopReason.MAX_TOKENS,
            usage=TokenUsage(input_tokens=300, output_tokens=1024),
        )


def test_a_turn_that_was_cut_off_fails_and_still_reports_its_spend() -> None:
    exchange = ask(QUESTION, model=CutOff(), toolbox=FakeToolbox(services=SERVICES))
    assert "cut off" in failed(exchange).detail
    assert (exchange.usage.input_tokens, exchange.usage.output_tokens) == (300, 1024)


def test_a_model_that_circles_stops_at_the_round_limit() -> None:
    turns = [call(f"t{index}", "services") for index in range(MAX_TOOL_ROUNDS + 1)]
    exchange, _ = run(*turns, services=SERVICES)

    assert "without finishing" in failed(exchange).detail
    assert len(exchange.tool_calls) == MAX_TOOL_ROUNDS


def test_a_model_that_cannot_be_reached_keeps_its_own_cause() -> None:
    exchange = ask(QUESTION, model=ScriptedModel.unavailable(), toolbox=FakeToolbox())
    assert failed(exchange).cause == "NotOptedIn"
    assert exchange.usage.total == 0
    assert exchange.tool_calls == ()


def test_a_reused_call_id_fails() -> None:
    exchange, _ = run(
        call("t1", "services"), call("t1", "services"), answer("x {{a}}"), services=SERVICES
    )
    assert "reused a call id" in failed(exchange).detail


def test_finishing_and_asking_in_one_turn_fails() -> None:
    both = Message(
        role=Role.ASSISTANT,
        tool_calls=(*call("t1", "services").tool_calls, *refuse("tool", "Nothing.").tool_calls),
    )
    assert "same turn" in failed(run(both, services=SERVICES)[0]).detail


def test_a_tool_that_failed_is_shown_to_the_model_and_cannot_be_cited() -> None:
    exchange, model = run(
        call("t1", "broken"),
        answer("It cost {{x}}.", x=("t1", "data.total")),
        broken=ToolUnavailableError("broken was refused by the API, status 503"),
    )

    assert "never returned" in failed(exchange).detail
    assert [(r.tool, r.returned) for r in exchange.tool_calls] == [("broken", False)]
    (result,) = model.received[1].messages[-1].tool_results
    assert result.is_error


@pytest.mark.parametrize(
    ("path", "detail"),
    [
        ("data[name=AmazonEC2].missing", "does not return"),
        ("data[name=AmazonEC2].line_items[a=b]", "not a list"),
        ("data[name=AmazonEC2]", "not a figure or a label"),
        ("data[[name", "not a path"),
        ("", "not a path"),
    ],
)
def test_a_path_that_does_not_resolve_to_a_value_fails(path: str, detail: str) -> None:
    exchange, _ = run(
        call("t1", "services"), answer("It cost {{x}}.", x=("t1", path)), services=SERVICES
    )
    assert detail in failed(exchange).detail


def test_two_rows_matching_one_selector_fail_as_ambiguous() -> None:
    twice = output([{"name": "a", "cost": Decimal(1)}, {"name": "a", "cost": Decimal(2)}])
    exchange, _ = run(
        call("t1", "rows"), answer("{{x}}", x=("t1", "data[name=a].cost")), rows=twice
    )
    assert "more than one row" in failed(exchange).detail


# --- what is refused, and why ---------------------------------------------------------


def test_a_tool_that_does_not_exist_is_refused_and_nothing_is_called() -> None:
    model = ScriptedModel({QUESTION: (call("t1", "forecast_next_month"),)})
    toolbox = FakeToolbox(services=SERVICES)

    exchange = ask(QUESTION, model=model, toolbox=toolbox)

    refusal = refused(exchange)
    assert refusal.gap is Gap.TOOL
    assert "forecast_next_month" in refusal.reason
    assert toolbox.calls == []


def test_a_null_figure_is_refused_with_its_rows_own_reason() -> None:
    summary = output({"change": None, "change_reason": "there is no previous period to compare"})
    exchange, _ = run(
        call("t1", "summary"), answer("{{x}}", x=("t1", "data.change")), summary=summary
    )

    refusal = refused(exchange)
    assert (refusal.gap, refusal.screen) == (Gap.FIGURE, "/cost")
    assert "no previous period" in refusal.reason


def test_a_null_figure_with_no_reason_says_it_has_none() -> None:
    exchange, _ = run(
        call("t1", "summary"),
        answer("{{x}}", x=("t1", "data.change")),
        summary=output({"change": None}),
    )
    assert "does not say why" in refused(exchange).reason


def test_a_row_explaining_why_its_list_is_empty_is_refused_with_that_reason() -> None:
    clusters = output(
        {
            "clusters": [
                {"cluster_name": "c1", "workloads": [], "unmeasurable_reason": "no split rows"}
            ]
        }
    )
    path = "data.clusters[cluster_name=c1].workloads[workload_name=api].cost"

    exchange, _ = run(
        call("t1", "containers"), answer("{{x}}", x=("t1", path)), containers=clusters
    )

    refusal = refused(exchange)
    assert refusal.gap is Gap.FIGURE
    assert "no split rows" in refusal.reason


def test_an_empty_result_beside_a_collection_failure_is_refused_naming_the_failure() -> None:
    failure = {
        "cause": "Misconfigured",
        "collector": "cost_focus",
        "remediation": "Enable split cost allocation data.",
    }
    empty = output({"clusters": []}, failures=(failure,))
    path = "data.clusters[cluster_name=c1].total"

    exchange, _ = run(call("t1", "containers"), answer("{{x}}", x=("t1", path)), containers=empty)

    refusal = refused(exchange)
    assert refusal.gap is Gap.FIGURE
    assert "Misconfigured in cost_focus" in refusal.reason


def test_a_row_nothing_visible_matches_is_a_scope_refusal_naming_what_was_asked() -> None:
    exchange, _ = run(
        call("t1", "services"),
        answer("{{x}}", x=("t1", "data[name=AmazonRDS].effective_cost")),
        services=SERVICES,
    )

    refusal = refused(exchange)
    assert refusal.gap is Gap.SCOPE
    assert "name AmazonRDS" in refusal.reason


def test_a_forecast_is_never_cited() -> None:
    forecast = output([{"name": "next", "cost": Decimal(5), "provenance": "forecast"}])
    exchange, _ = run(
        call("t1", "rows"), answer("{{x}}", x=("t1", "data[name=next].cost")), rows=forecast
    )
    assert "ADR-0015" in refused(exchange).reason


def test_a_figure_with_no_date_anywhere_is_refused() -> None:
    undated = output([{"name": "a", "cost": Decimal(5)}], as_of=None)
    exchange, _ = run(
        call("t1", "rows"), answer("{{x}}", x=("t1", "data[name=a].cost")), rows=undated
    )
    assert "no date" in refused(exchange).reason


# --- provenance, dates and labels -----------------------------------------------------


def test_a_rows_own_flag_and_date_beat_the_tools() -> None:
    rows = output([{"name": "q", "cost": Decimal(7), "provenance": "modelled", "as_of": ROW_AS_OF}])
    exchange, _ = run(call("t1", "rows"), answer("{{x}}", x=("t1", "data[name=q].cost")), rows=rows)

    assert isinstance(exchange.outcome, Answer)
    (cited,) = exchange.outcome.citations
    assert (cited.provenance, cited.as_of) == (Provenance.MODELLED, ROW_AS_OF)


def test_a_date_and_a_count_are_cited_as_a_label_and_a_figure() -> None:
    rows = output([{"name": "q", "seen_at": ROW_AS_OF, "runs": 14}])
    exchange, _ = run(
        call("t1", "rows"),
        answer(
            "Seen {{when}}, {{runs}} times.",
            when=("t1", "data[name=q].seen_at"),
            runs=("t1", "data[name=q].runs"),
        ),
        rows=rows,
    )

    assert isinstance(exchange.outcome, Answer)
    cited = {c.placeholder: c.value for c in exchange.outcome.citations}
    assert cited == {"when": ROW_AS_OF.isoformat(), "runs": Decimal(14)}


# --- what a figure counts, ISS-231 ----------------------------------------------------


def cited_units(exchange: Exchange) -> dict[str, Unit | None]:
    assert isinstance(exchange.outcome, Answer), exchange.outcome
    return {citation.placeholder: citation.unit for citation in exchange.outcome.citations}


def test_a_figure_carries_the_unit_its_tool_declares_and_a_label_carries_none() -> None:
    exchange, _ = run(
        call("t1", "services"),
        answer(
            "{{service}} cost {{cost}} over {{items}} line items.",
            service=("t1", "data[name=AmazonEC2].name"),
            cost=("t1", "data[name=AmazonEC2].effective_cost"),
            items=("t1", "data[name=AmazonEC2].line_items"),
        ),
        services=SERVICES,
    )

    assert cited_units(exchange) == {"service": None, "cost": Unit.USD, "items": Unit.COUNT}


def test_the_unit_is_the_declared_one_whatever_the_field_is_named() -> None:
    """Money under a name with no money word in it is still money, and a name that sounds
    like money is still a count where the tool says so. Nothing reads the name."""
    rows = output(
        [{"name": "a", "overage": Decimal("12.50"), "cost_lines": 3}],
        units={"data.overage": Unit.USD, "data.cost_lines": Unit.COUNT},
    )
    exchange, _ = run(
        call("t1", "rows"),
        answer(
            "Owed {{owed}} over {{lines}} lines.",
            owed=("t1", "data[name=a].overage"),
            lines=("t1", "data[name=a].cost_lines"),
        ),
        rows=rows,
    )

    assert cited_units(exchange) == {"owed": Unit.USD, "lines": Unit.COUNT}


def test_a_figure_its_tool_declares_no_unit_for_fails_rather_than_being_given_one() -> None:
    undeclared = output([{"name": "AmazonEC2", "effective_cost": Decimal("812.40")}], units={})
    exchange, _ = run(
        call("t1", "services"),
        answer("It cost {{x}}.", x=("t1", "data[name=AmazonEC2].effective_cost")),
        services=undeclared,
    )

    failure = failed(exchange)
    assert failure.cause == "SchemaDrift"
    assert "declares no unit for data.effective_cost" in failure.detail
    assert "AmazonEC2" not in failure.detail, "a selector is what a model chose, so not repeated"


def test_a_number_in_the_envelopes_meta_is_a_count_with_nothing_declared() -> None:
    exchange, _ = run(
        call("t1", "services"),
        answer(
            "These cover {{visible}} of {{total}} accounts.",
            visible=("t1", "meta.scope_coverage.visible"),
            total=("t1", "meta.scope_coverage.total"),
        ),
        services=output([], units={}),
    )

    assert cited_units(exchange) == {"visible": Unit.COUNT, "total": Unit.COUNT}


def test_a_label_needs_no_declared_unit() -> None:
    exchange, _ = run(
        call("t1", "services"),
        answer("{{service}} is listed.", service=("t1", "data[name=AmazonEC2].name")),
        services=output([{"name": "AmazonEC2"}], units={}),
    )

    assert cited_units(exchange) == {"service": None}


def test_a_selector_value_may_hold_a_dot() -> None:
    steps = parse_path("data[name=m5.large].cost")
    assert steps is not None
    assert [(s.field, s.key, s.value) for s in steps] == [
        ("data", "name", "m5.large"),
        ("cost", None, None),
    ]


# --- what this module may reach ---------------------------------------------------------


def test_the_loop_imports_nothing_from_the_api_or_a_database() -> None:
    """The plan's first criterion. The layer contract forbids it too; this names it."""
    tree = ast.parse(Path(insight.__file__).read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    reached = sorted(
        name for name in imported if name.split(".")[0] in {"finops_api", "sqlalchemy", "httpx"}
    )
    assert reached == []
