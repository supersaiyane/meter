"""The `LlmProvider` sentences, held to the fake and to the Bedrock adapter alike.

Four sentences, and the last is the one the plan names:

1. It satisfies the port.
2. A completion says what it spent, and a turn that asks for tools stopped to wait for
   them, with an id per call so each result pairs with its request.
3. Every failure is one of the typed causes, never a bare exception, because a caller
   that has to guess writes `except Exception` and the taxonomy collapses.
4. A model this deployment was never given access to is `NotOptedIn`, never
   `Unreachable`. The first is a setting somebody has not changed and the second is an
   outage, and a screen that says broken when it means not enabled teaches its reader
   to stop asking.

The fake's own promise, that the same request gets the same completion, is held at
the bottom. It is true of the fake by construction and of no real model, which is the
reason the evaluation sets run against the fake.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pytest

from finops_core.config import Settings
from finops_core.errors import CollectionError, NotOptedIn, Unreachable
from finops_core.ports.llm import (
    CompletionRequest,
    LlmProvider,
    Message,
    Role,
    StopReason,
    ToolCall,
    ToolResult,
    ToolSchema,
)
from finops_fakes.llm import UNSCRIPTED, Script, ScriptedModel
from finops_providers.aws.bedrock import BedrockModel
from tests.providers.aws.converse import (
    NOT_ENABLED,
    ConverseDouble,
    client_error,
    reply,
    text,
    tool_use,
)

COST_TOOL = ToolSchema(name="get_cost_by_service", description="Cost by service, this month.")

ASKS_FOR_A_TOOL = "Which service cost the most this month?"
ANSWERS_IN_PROSE = "Which tools can you call?"


def _request(question: str, *history: Message) -> CompletionRequest:
    return CompletionRequest(
        system="Answer from tools. Cite every figure.",
        messages=(Message(role=Role.USER, text=question), *history),
        tools=(COST_TOOL,),
        max_output_tokens=256,
    )


@dataclass(frozen=True)
class ModelUnderTest:
    available: LlmProvider
    unavailable: LlmProvider
    tool_request: CompletionRequest
    answer_request: CompletionRequest


def _script() -> Script:
    return {
        ASKS_FOR_A_TOOL: (
            Message(
                role=Role.ASSISTANT,
                tool_calls=(ToolCall(call_id="t1", name="get_cost_by_service"),),
            ),
        ),
        ANSWERS_IN_PROSE: (Message(role=Role.ASSISTANT, text="One tool reads cost by service."),),
    }


def _fake(_settings: Settings) -> ModelUnderTest:
    return ModelUnderTest(
        available=ScriptedModel(_script()),
        unavailable=ScriptedModel.unavailable(),
        tool_request=_request(ASKS_FOR_A_TOOL),
        answer_request=_request(ANSWERS_IN_PROSE),
    )


def _bedrock(settings: Settings) -> ModelUnderTest:
    """TASK-P7-004. The adapter over a double that validates every request it is sent
    against the Converse input shape, and answers by question."""
    configured = settings.model_copy(update={"assistant_model_id": "a-configured-model"})
    answering = ConverseDouble(
        replies={
            ASKS_FOR_A_TOOL: reply(tool_use("tooluse_a", "get_cost_by_service"), stop="tool_use"),
            ANSWERS_IN_PROSE: reply(text("One tool reads cost by service.")),
        }
    )
    refusing = ConverseDouble(error=client_error("AccessDeniedException", NOT_ENABLED))
    return ModelUnderTest(
        available=BedrockModel(configured, client_factory=lambda: answering),
        unavailable=BedrockModel(configured, client_factory=lambda: refusing),
        tool_request=_request(ASKS_FOR_A_TOOL),
        answer_request=_request(ANSWERS_IN_PROSE),
    )


#: The same sentences hold the adapter and the fake.
SUBJECTS: dict[str, Callable[[Settings], ModelUnderTest]] = {"fake": _fake, "bedrock": _bedrock}


@pytest.fixture(params=sorted(SUBJECTS))
def subject(request: pytest.FixtureRequest, settings: Settings) -> ModelUnderTest:
    return SUBJECTS[request.param](settings)


def test_the_model_satisfies_the_port(subject: ModelUnderTest) -> None:
    assert isinstance(subject.available, LlmProvider)
    assert isinstance(subject.unavailable, LlmProvider)


def test_a_turn_that_asks_for_tools_stopped_to_wait_for_them(subject: ModelUnderTest) -> None:
    completion = subject.available.complete(subject.tool_request)

    assert completion.stop_reason is StopReason.TOOL_USE
    ids = [call.call_id for call in completion.message.tool_calls]
    assert ids and len(ids) == len(set(ids)), "each result must pair with exactly one call"
    assert completion.usage.total > 0


def test_a_turn_that_answers_says_what_it_spent(subject: ModelUnderTest) -> None:
    """Both counts, because the cost of an exchange is priced per direction."""
    completion = subject.available.complete(subject.answer_request)

    assert completion.stop_reason is StopReason.END_TURN
    assert completion.message.text.strip()
    assert completion.usage.input_tokens > 0
    assert completion.usage.output_tokens > 0


def test_a_model_that_was_never_enabled_is_not_opted_in(subject: ModelUnderTest) -> None:
    with pytest.raises(NotOptedIn) as raised:
        subject.unavailable.complete(subject.answer_request)

    assert not isinstance(raised.value, Unreachable)
    assert raised.value.remediation, "a typed failure says what to do next"


def test_every_failure_is_one_of_the_typed_causes(subject: ModelUnderTest) -> None:
    try:
        subject.unavailable.complete(subject.tool_request)
    except Exception as failure:  # the assertions below are the classification
        assert isinstance(failure, CollectionError)
        assert type(failure) is not CollectionError
    else:  # pragma: no cover - the subject is built to fail
        pytest.fail("the unavailable model answered")


# --- the fake's own promises ---------------------------------------------------------


def test_the_fake_answers_the_same_request_the_same_way_twice() -> None:
    """The plan's acceptance criterion, asserted by calling it twice."""
    model = ScriptedModel(_script())

    first = model.complete(_request(ASKS_FOR_A_TOOL))
    second = model.complete(_request(ASKS_FOR_A_TOOL))

    assert first == second


def test_the_fake_plays_its_script_in_turn_order() -> None:
    model = ScriptedModel(
        {
            ASKS_FOR_A_TOOL: (
                Message(role=Role.ASSISTANT, tool_calls=(ToolCall(call_id="t1", name="x"),)),
                Message(role=Role.ASSISTANT, text="second turn"),
            )
        }
    )
    history = (
        Message(role=Role.ASSISTANT, tool_calls=(ToolCall(call_id="t1", name="x"),)),
        Message(role=Role.USER, tool_results=(ToolResult(call_id="t1", content="{}"),)),
    )

    assert model.complete(_request(ASKS_FOR_A_TOOL, *history)).message.text == "second turn"


def test_an_unscripted_question_gets_a_reply_that_is_visibly_not_an_answer() -> None:
    reply = ScriptedModel().complete(_request("Anything at all?"))

    assert reply.message.text == UNSCRIPTED
    assert reply.stop_reason is StopReason.END_TURN


def test_the_fake_records_what_it_was_sent() -> None:
    """What TASK-P7-013 reads to assert a blocked question reached no model."""
    model = ScriptedModel()
    assert not model.received

    model.complete(_request(ANSWERS_IN_PROSE))

    assert [sent.question for sent in model.received] == [ANSWERS_IN_PROSE]


def test_a_script_cannot_hand_the_model_a_user_turn() -> None:
    with pytest.raises(ValueError, match="user turn"):
        ScriptedModel({"q": (Message(role=Role.USER, text="not the model's line"),)})
