"""A question, the asker's own tools, and an answer whose every figure is cited.

TASK-P7-006 and FEAT-038, P7 spec sections 5.1, 5.2 and 7. The loop, and the provenance
check that refuses an unattributed figure before it reaches a route.

**The tools are the HTTP API.** This module reaches data only through a `Toolbox`, and the
one the product runs, `finops_api.toolbox.ApiToolbox`, calls the routes with the asker's
own token. Scope is therefore not reimplemented here: an asker who can see two accounts
gets tool results about two accounts, decided by the same dependency and the same guard as
the screen, because it is the same call. This module imports nothing from `finops_api`,
which the layer contract forbids and a test names anyway.

**The model names where a figure is, never what it is.** The first prompt carries the
question and the tool schemas, and no data. The model finishes by calling one of two tools
this module adds. `answer` takes prose holding placeholders and, for each, the call and the
path where its value is, and the value is read out of the result that call returned. A
model that misreads a figure cites a path, and the path resolves to the real figure or it
does not resolve. `refuse` takes the kind of thing missing and a reason.

**Three refusals are made here rather than by the model,** because each is decidable from
what the tools returned:

- A tool that does not exist. Every tool is a route a screen reads, so no screen answers
  that either. `Gap.TOOL`, naming it.
- A figure the tool says is absent: a null value, a row whose own `..._reason` explains why
  it has nothing to show, or an empty result beside an open collection failure.
  `Gap.FIGURE`, with the product's own reason and the screen that would show it.
- A row nothing visible to the asker matches. The guard removed it or it never existed,
  and this module cannot tell those apart and does not try to. `Gap.SCOPE`.

**Failed, with a typed cause, is everything else that went wrong.** A model that could not
be reached keeps its own cause. A model that wrote a bare figure, cited a call that never
returned, named a path that is not there, ran out of room or never finished is
`SchemaDrift`, spec section 7, and the detail never repeats what the model wrote, because
what it wrote may hold a secret it was asked to echo.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID

from finops_core.domain.insight import (
    PLACEHOLDER_NAME,
    Answer,
    Citation,
    Failure,
    Gap,
    Provenance,
    ProvenanceError,
    Refusal,
    check_prose,
)
from finops_core.errors import CollectionError
from finops_core.ports.llm import (
    CompletionRequest,
    LlmProvider,
    Message,
    Role,
    StopReason,
    TokenUsage,
    ToolCall,
    ToolResult,
    ToolSchema,
)

ANSWER = "answer"
REFUSE = "refuse"

#: Turns of tool calls one question may take. Room to read three or four screens and
#: correct one wrong turn. Past that a model is circling, and every turn is spend the
#: asker did not ask for.
MAX_TOOL_ROUNDS = 6

#: The length of one turn. An answer is a few sentences beside its citations, spec section
#: 12, and the cap keeps it short enough for a reader to check against them.
MAX_OUTPUT_TOKENS = 1024

#: The gaps a model may name. Budget and secret are decided before any model is asked, so
#: a model claiming one is claiming something it cannot know.
MODEL_GAPS = frozenset({Gap.TOOL, Gap.FIGURE, Gap.SCOPE})

#: How much of a name the model chose is repeated back to the asker.
NAME_LIMIT = 64

SYSTEM = (
    "You answer questions about cloud cost using only the tools you are given. Every tool "
    "is a screen of this product, read with the asker's own access, so a tool returns only "
    "what the asker may see.\n"
    "Never write a figure: not a number, not a number in words, not a date, and not a name "
    "that holds a digit. Write a placeholder such as {{total}} instead. When you finish, "
    "call the answer tool with your prose and, for each placeholder, the call_id of the "
    "tool result that holds its value and the path to it, such as "
    "data[name=AmazonEC2].effective_cost or meta.scope_coverage.visible. The product reads "
    "the value from that result itself.\n"
    "When meta.scope_coverage shows a figure covers part of the organization, say so.\n"
    "When the tools cannot answer, call the refuse tool and name what is missing: tool when "
    "no tool answers the question, figure when a tool says the figure is not measured, and "
    "scope when it is outside what the asker can see. Never estimate, and never forecast."
)

ANSWER_TOOL = ToolSchema(
    name=ANSWER,
    description=(
        "Finish with an answer. The prose holds a {{placeholder}} wherever a figure goes "
        "and no figure itself, and every placeholder is cited by call_id and path."
    ),
    parameters={
        "type": "object",
        "properties": {
            "prose": {"type": "string"},
            "citations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "placeholder": {"type": "string"},
                        "call_id": {"type": "string"},
                        "path": {"type": "string"},
                    },
                    "required": ["placeholder", "call_id", "path"],
                },
            },
        },
        "required": ["prose", "citations"],
    },
)

REFUSE_TOOL = ToolSchema(
    name=REFUSE,
    description="Finish by declining, naming the kind of thing that is missing and why.",
    parameters={
        "type": "object",
        "properties": {
            "gap": {"type": "string", "enum": sorted(gap.value for gap in MODEL_GAPS)},
            "reason": {"type": "string"},
        },
        "required": ["gap", "reason"],
    },
)


# --- what the loop is given, and what it returns ----------------------------------


@dataclass(frozen=True)
class ToolOutput:
    """What one tool returned: the envelope with its values typed, and the text a model reads."""

    envelope: Mapping[str, Any]
    text: str
    #: How the tool's figures were arrived at, where a row does not say.
    provenance: Provenance
    #: The screen that shows the same rows.
    screen: str | None = None


class ToolUnavailableError(Exception):
    """A tool could not return a result.

    The message is shown to the model, so it says what happened and never repeats an
    argument the model passed, which may be the thing an attack was reaching for.
    """


class Toolbox(Protocol):
    """The asker's tools. In the product, the HTTP API called with the asker's token."""

    def schemas(self) -> tuple[ToolSchema, ...]: ...

    def call(self, name: str, arguments: Mapping[str, Any]) -> ToolOutput: ...


@dataclass(frozen=True)
class ToolCallRecord:
    """One call the model asked for, in order, so an exchange can be replayed."""

    call_id: str
    tool: str
    arguments: Mapping[str, Any]
    #: True only where the tool returned a result the answer could cite.
    returned: bool


@dataclass(frozen=True)
class Exchange:
    """A question, which of three things came back, the calls behind it and what it spent."""

    question: str
    outcome: Answer | Refusal | Failure
    tool_calls: tuple[ToolCallRecord, ...]
    usage: TokenUsage


# --- the loop ---------------------------------------------------------------------


def ask(question: str, *, model: LlmProvider, toolbox: Toolbox) -> Exchange:
    """Answer `question` from the asker's own tools, or refuse, or fail with a typed cause."""
    data_tools = toolbox.schemas()
    known = {tool.name for tool in data_tools}
    offered = (*data_tools, ANSWER_TOOL, REFUSE_TOOL)
    conversation: list[Message] = [Message(role=Role.USER, text=question)]
    returned: dict[str, tuple[str, ToolOutput]] = {}
    records: list[ToolCallRecord] = []
    spent = TokenUsage(input_tokens=0, output_tokens=0)

    def ended(outcome: Answer | Refusal | Failure) -> Exchange:
        return Exchange(question=question, outcome=outcome, tool_calls=tuple(records), usage=spent)

    for _ in range(MAX_TOOL_ROUNDS):
        request = CompletionRequest(
            system=SYSTEM,
            messages=tuple(conversation),
            tools=offered,
            max_output_tokens=MAX_OUTPUT_TOKENS,
        )
        try:
            completion = model.complete(request)
        except CollectionError as unreachable:
            return ended(Failure.from_error(unreachable))
        spent = spent + completion.usage
        if completion.stop_reason is StopReason.MAX_TOKENS:
            return ended(_drift("the model was cut off before it finished, so nothing is shown"))
        calls = completion.message.tool_calls
        if not calls:
            return ended(_drift("the model stopped without answering or refusing"))
        if any(call.name in (ANSWER, REFUSE) for call in calls):
            if len(calls) > 1:
                return ended(_drift("the model finished and asked for tools in the same turn"))
            return ended(_conclude(calls[0], returned))
        ids = [call.call_id for call in calls]
        if len(set(ids)) != len(ids) or any(record.call_id in ids for record in records):
            return ended(_drift("the model reused a call id, so a citation could name either"))
        unknown = [call for call in calls if call.name not in known]
        if unknown:
            records.extend(_record(call, returned=False) for call in calls)
            return ended(_no_such_tool(unknown[0].name))
        results = tuple(_run(call, toolbox, records, returned) for call in calls)
        conversation.append(completion.message)
        conversation.append(Message(role=Role.USER, tool_results=results))
    return ended(_drift(f"the model asked for tools {MAX_TOOL_ROUNDS} times without finishing"))


def _run(
    call: ToolCall,
    toolbox: Toolbox,
    records: list[ToolCallRecord],
    returned: dict[str, tuple[str, ToolOutput]],
) -> ToolResult:
    try:
        output = toolbox.call(call.name, call.arguments)
    except ToolUnavailableError as unavailable:
        records.append(_record(call, returned=False))
        return ToolResult(call_id=call.call_id, content=str(unavailable), is_error=True)
    records.append(_record(call, returned=True))
    returned[call.call_id] = (call.name, output)
    return ToolResult(call_id=call.call_id, content=output.text)


def _record(call: ToolCall, *, returned: bool) -> ToolCallRecord:
    return ToolCallRecord(
        call_id=call.call_id, tool=call.name, arguments=dict(call.arguments), returned=returned
    )


def _drift(detail: str) -> Failure:
    return Failure(cause="SchemaDrift", detail=detail)


def _no_such_tool(name: str) -> Refusal:
    return Refusal(
        gap=Gap.TOOL,
        reason=(
            f"There is no tool named {name[:NAME_LIMIT]}. Every tool is a route a screen "
            f"reads, so no screen in this product answers that either."
        ),
    )


# --- finishing --------------------------------------------------------------------


def _conclude(
    call: ToolCall, returned: Mapping[str, tuple[str, ToolOutput]]
) -> Answer | Refusal | Failure:
    if call.name == REFUSE:
        return _models_refusal(call.arguments)
    return _answer(call.arguments, returned)


def _models_refusal(arguments: Mapping[str, Any]) -> Refusal | Failure:
    gap, reason = arguments.get("gap"), arguments.get("reason")
    if not isinstance(reason, str) or gap not in {member.value for member in MODEL_GAPS}:
        return _drift("the model refused without a gap it may name and a reason")
    try:
        check_prose(reason)
        return Refusal(gap=Gap(gap), reason=reason)
    except ProvenanceError as figure:
        return _drift(f"the model's refusal carried a figure: {figure}")
    except ValueError as unexplained:
        return _drift(f"the model's refusal gave no reason a reader could use: {unexplained}")


def _answer(
    arguments: Mapping[str, Any], returned: Mapping[str, tuple[str, ToolOutput]]
) -> Answer | Refusal | Failure:
    prose, references = arguments.get("prose"), arguments.get("citations")
    if not isinstance(prose, str) or not isinstance(references, list):
        return _drift("the answer is not prose with a list of citations")
    try:
        check_prose(prose)
    except ProvenanceError as figure:
        return _drift(str(figure))
    citations: list[Citation] = []
    for reference in references:
        cited = _cite(reference, returned)
        if not isinstance(cited, Citation):
            return cited
        citations.append(cited)
    try:
        return Answer(prose=prose, citations=tuple(citations))
    except ProvenanceError as unattributed:
        return _drift(str(unattributed))


def _cite(
    reference: object, returned: Mapping[str, tuple[str, ToolOutput]]
) -> Citation | Refusal | Failure:
    if not isinstance(reference, Mapping) or not all(
        isinstance(reference.get(key), str) for key in ("placeholder", "call_id", "path")
    ):
        return _drift("a citation does not name its placeholder, its call and its path")
    if not PLACEHOLDER_NAME.fullmatch(reference["placeholder"]):
        return _drift("a citation's placeholder is not a plain name")
    found = returned.get(reference["call_id"])
    if found is None:
        return _drift("a citation names a call that never returned")
    tool, output = found
    resolved = _resolve(tool, output, reference["path"])
    if not isinstance(resolved, _Resolved):
        return resolved
    return Citation(
        placeholder=reference["placeholder"],
        tool=tool,
        call_id=reference["call_id"],
        field=reference["path"],
        value=resolved.value,
        provenance=resolved.provenance,
        as_of=resolved.as_of,
    )


# --- reading a value out of a result ----------------------------------------------

#: One step of a path: a field, optionally selecting the one row whose `key` is `value`.
_STEP = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)(?:\[([A-Za-z_][A-Za-z0-9_]*)=([^\]]*)\])?")


@dataclass(frozen=True)
class Step:
    field: str
    key: str | None = None
    value: str | None = None


def parse_path(path: str) -> tuple[Step, ...] | None:
    """`data[name=AmazonEC2].effective_cost`, as steps. None for anything else.

    A selector value may hold a dot, `m5.large` for one, so the path is read step by step
    rather than split on dots.
    """
    steps: list[Step] = []
    position = 0
    while True:
        match = _STEP.match(path, position)
        if match is None:
            return None
        steps.append(Step(field=match.group(1), key=match.group(2), value=match.group(3)))
        position = match.end()
        if position == len(path):
            return tuple(steps)
        if path[position] != ".":
            return None
        position += 1


@dataclass(frozen=True)
class _Resolved:
    value: Decimal | str
    provenance: Provenance
    as_of: datetime


def _resolve(tool: str, output: ToolOutput, path: str) -> _Resolved | Refusal | Failure:
    steps = parse_path(path)
    if steps is None:
        return _drift(f"a citation's path into {tool} is not a path")
    node: Any = output.envelope
    rows: list[Mapping[str, Any]] = [output.envelope]
    for step in steps:
        if not isinstance(node, Mapping) or step.field not in node:
            return _drift(f"a citation names a field {tool} does not return")
        holder = node
        node = node[step.field]
        if step.key is not None:
            if not isinstance(node, list | tuple):
                return _drift(f"a citation selects a row of {tool} from something not a list")
            matches = [row for row in node if _selects(row, step)]
            if not matches:
                return _nothing_matches(tool, output, holder, step, empty=not node)
            if len(matches) > 1:
                return _drift(f"a citation selects more than one row of {tool}")
            node = matches[0]
        if isinstance(node, Mapping):
            rows.append(node)
    if node is None:
        return _absent(tool, output, rows[-1], steps[-1].field)
    value = _citable(node)
    if value is None:
        return _drift(f"a citation names something in {tool} that is not a figure or a label")
    provenance = _provenance(rows, output.provenance)
    if provenance is None:
        return Refusal(
            gap=Gap.FIGURE,
            reason=(
                f"{tool} marks that figure as neither measured nor modelled, and only those "
                f"are cited. A forecast is not, ADR-0015."
            ),
            screen=output.screen,
        )
    as_of = _as_of(rows)
    if as_of is None:
        return Refusal(
            gap=Gap.FIGURE,
            reason=(
                f"{tool} gives no date for that figure, and a figure without one is not shown."
            ),
            screen=output.screen,
        )
    return _Resolved(value=value, provenance=provenance, as_of=as_of)


def _selects(row: object, step: Step) -> bool:
    if not isinstance(row, Mapping) or step.key is None:
        return False
    actual = row.get(step.key)
    return actual is not None and str(actual) == step.value


def _nothing_matches(
    tool: str, output: ToolOutput, holder: Mapping[str, Any], step: Step, *, empty: bool
) -> Refusal:
    wanted = f"{step.key} {str(step.value)[:NAME_LIMIT]}"
    reason = _reason_in(holder)
    if reason:
        return Refusal(
            gap=Gap.FIGURE,
            reason=f"{tool} has nothing for {wanted}: {reason}",
            screen=output.screen,
        )
    failures = _failures(output.envelope)
    if empty and failures:
        return Refusal(
            gap=Gap.FIGURE,
            reason=f"{tool} returned nothing for {wanted}, and collection says why. {failures}",
            screen=output.screen,
        )
    return Refusal(
        gap=Gap.SCOPE,
        reason=(
            f"Nothing {tool} returned for you has {wanted}. It may be outside the accounts "
            f"you can see, or it may not exist."
        ),
    )


def _absent(tool: str, output: ToolOutput, row: Mapping[str, Any], field: str) -> Refusal:
    reason = _reason_in(row)
    said = f": {reason}" if reason else ", and it does not say why"
    return Refusal(
        gap=Gap.FIGURE,
        reason=f"{tool} holds no figure for {field}{said}.",
        screen=output.screen,
    )


def _reason_in(row: Mapping[str, Any]) -> str | None:
    """The row's own explanation of why it has nothing to show, where it gives one."""
    for key, value in row.items():
        if str(key).endswith("_reason") and isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _failures(envelope: Mapping[str, Any]) -> str:
    meta = envelope.get("meta")
    failures = meta.get("failures") if isinstance(meta, Mapping) else None
    return " ".join(
        f"{failure.get('cause')} in {failure.get('collector')}: {failure.get('remediation')}"
        for failure in failures or ()
        if isinstance(failure, Mapping)
    )


def _citable(node: object) -> Decimal | str | None:
    """A figure as a Decimal, a label as a string, and None for anything else."""
    if isinstance(node, bool):
        return None
    if isinstance(node, Decimal):
        return node if node.is_finite() else None
    if isinstance(node, int):
        return Decimal(node)
    if isinstance(node, float):
        # Through its text, so the figure is the one that was shown rather than the
        # binary approximation of it.
        return Decimal(str(node))
    if isinstance(node, datetime | date):
        return node.isoformat()
    if isinstance(node, UUID):
        return str(node)
    if isinstance(node, str) and node.strip():
        return node
    return None


def _provenance(rows: list[Mapping[str, Any]], default: Provenance) -> Provenance | None:
    """The innermost row's own flag where it has one, otherwise the tool's."""
    for row in reversed(rows):
        stated = row.get("provenance")
        if stated is None:
            continue
        try:
            return Provenance(str(stated))
        except ValueError:
            return None
    return default


def _as_of(rows: list[Mapping[str, Any]]) -> datetime | None:
    """The innermost row's `as_of`, otherwise the envelope's."""
    for row in reversed(rows):
        stamp = row.get("as_of")
        if isinstance(stamp, datetime):
            return stamp
    meta = rows[0].get("meta")
    stamp = meta.get("as_of") if isinstance(meta, Mapping) else None
    return stamp if isinstance(stamp, datetime) else None


# --- what it may spend, and what it spent -----------------------------------------

#: List prices are quoted per million tokens.
PER_MILLION = Decimal(1_000_000)


def month_start(at: datetime) -> datetime:
    """The first instant of `at`'s calendar month in UTC, which is when a budget starts."""
    return at.astimezone(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def next_month_start(at: datetime) -> datetime:
    """When the budget for `at`'s month resets."""
    start = month_start(at)
    if start.month == 12:
        return start.replace(year=start.year + 1, month=1)
    return start.replace(month=start.month + 1)


def budget_refusal(*, spent: int, budget: int, at: datetime) -> Refusal | None:
    """None while the month has budget left, and otherwise the refusal naming it.

    A refusal rather than a failure, TASK-P7-007: nothing is broken, the deployment chose a
    ceiling and it has been reached. Checked before a question rather than during one, so a
    question already running finishes, and two asked at the same instant can each overrun
    by one exchange. The figure is what exchanges recorded, never an estimate kept beside
    them, because two counts of one thing come to disagree.
    """
    if spent < budget:
        return None
    month = at.astimezone(UTC)
    return Refusal(
        gap=Gap.BUDGET,
        reason=(
            f"This tenant's assistant budget of {budget} tokens for {month:%B %Y} is spent, "
            f"with {spent} used. It resets on {next_month_start(at):%Y-%m-%d}, and the "
            f"ceiling is the setting METER_ASSISTANT_MONTHLY_TOKEN_BUDGET."
        ),
    )


def estimated_cost(
    usage: TokenUsage, *, input_per_million: Decimal, output_per_million: Decimal
) -> Decimal:
    """What an exchange cost at list prices. Modelled: the bill is the measurement."""
    spend = Decimal(usage.input_tokens) * input_per_million
    spend += Decimal(usage.output_tokens) * output_per_million
    return spend / PER_MILLION
