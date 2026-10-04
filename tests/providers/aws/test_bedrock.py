"""The Bedrock adapter, against a double that checks every request against the service model.

TASK-P7-004. Never run against AWS, ISS-002. What can be proved offline is proved here:
every request the adapter builds is valid Converse input by the model botocore ships,
every response field it reads exists (`test_response_shapes.py`), every failure is one of
the typed causes, and every error code it names is one Converse declares, so a typo in a
code cannot sit unnoticed in a mapping nothing exercises.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from botocore.exceptions import EndpointConnectionError

from finops_core.config import Settings
from finops_core.errors import (
    AccessDenied,
    CollectionError,
    Misconfigured,
    NotOptedIn,
    SchemaDrift,
    Throttled,
    Unreachable,
)
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
from finops_providers.aws import bedrock
from finops_providers.aws.bedrock import BedrockModel
from tests.providers.aws.converse import (
    CONVERSE,
    NOT_ENABLED,
    ConverseDouble,
    client_error,
    reply,
    text,
    tool_use,
)

ROOT = Path(__file__).resolve().parents[3]
MODEL = "a-configured-model"
QUESTION = "Which service cost the most this month?"
COST_TOOL = ToolSchema(
    name="get_cost_by_service",
    description="Cost by service, this month.",
    parameters={"type": "object", "properties": {"limit": {"type": "integer"}}},
)


def configured(settings: Settings) -> Settings:
    return settings.model_copy(update={"assistant_model_id": MODEL})


def request(*history: Message) -> CompletionRequest:
    return CompletionRequest(
        system="Answer from tools. Cite every figure.",
        messages=(Message(role=Role.USER, text=QUESTION), *history),
        tools=(COST_TOOL,),
        max_output_tokens=512,
    )


def model_answering(settings: Settings, response: object) -> tuple[BedrockModel, ConverseDouble]:
    double = ConverseDouble(replies={QUESTION: response})  # type: ignore[dict-item]
    return BedrockModel(configured(settings), client_factory=lambda: double), double


def model_failing(settings: Settings, error: Exception) -> BedrockModel:
    double = ConverseDouble(error=error)
    return BedrockModel(configured(settings), client_factory=lambda: double)


# --- what the module says about itself ------------------------------------------------


def test_the_first_line_says_it_has_never_met_aws() -> None:
    """The plan's first criterion. ISS-002 belongs where the next reader starts."""
    first = (bedrock.__doc__ or "").splitlines()[0]
    assert "Never run against AWS" in first
    assert "ISS-002" in first


def test_only_this_file_names_the_runtime_client() -> None:
    """ADR-0028: one file knows the vendor, and every other one talks to the port."""
    naming = sorted(
        str(path.relative_to(ROOT))
        for package in ("finops_core", "finops_query", "finops_ingest", "finops_api", "finops_mcp")
        for path in (ROOT / package).rglob("*.py")
        if "bedrock-runtime" in path.read_text(encoding="utf-8")
    )
    providers = sorted(
        str(path.relative_to(ROOT))
        for path in (ROOT / "finops_providers").rglob("*.py")
        if "bedrock-runtime" in path.read_text(encoding="utf-8")
    )
    assert naming == []
    assert providers == ["finops_providers/aws/bedrock.py"]


def test_with_no_model_configured_there_is_no_adapter(settings: Settings) -> None:
    """OPEN-10 unanswered is a deployment without an assistant, not one with a broken one."""
    with pytest.raises(ValueError, match="no model is configured"):
        BedrockModel(settings.model_copy(update={"assistant_model_id": " "}))


def test_the_adapter_satisfies_the_port(settings: Settings) -> None:
    model, _ = model_answering(settings, reply(text("hello")))
    assert isinstance(model, LlmProvider)


# --- the request ---------------------------------------------------------------------


def test_a_whole_conversation_is_valid_converse_input(settings: Settings) -> None:
    """System text, a tool call, a success and a failure, and a tool schema, all at once."""
    history = (
        Message(
            role=Role.ASSISTANT,
            text="Reading cost by service.",
            tool_calls=(
                ToolCall(call_id="t1", name="get_cost_by_service", arguments={"limit": 5}),
            ),
        ),
        Message(
            role=Role.USER,
            tool_results=(
                ToolResult(call_id="t1", content='{"data": [], "meta": {}}'),
                ToolResult(call_id="t2", content="the tool failed", is_error=True),
            ),
        ),
    )
    model, double = model_answering(settings, reply(text("Done.")))

    model.complete(request(*history))

    (sent,) = double.sent
    assert sent["modelId"] == MODEL
    assert sent["inferenceConfig"] == {"maxTokens": 512}
    assert sent["system"] == [{"text": "Answer from tools. Cite every figure."}]
    results = sent["messages"][2]["content"]
    assert [block["toolResult"]["status"] for block in results] == ["success", "error"]
    (spec,) = sent["toolConfig"]["tools"]
    assert spec["toolSpec"]["inputSchema"]["json"]["properties"] == {"limit": {"type": "integer"}}


# --- the response --------------------------------------------------------------------


def test_prose_is_read_with_what_it_spent(settings: Settings) -> None:
    model, _ = model_answering(
        settings,
        reply(text("First part."), text("Second part."), input_tokens=900, output_tokens=70),
    )

    completion = model.complete(request())

    assert completion.stop_reason is StopReason.END_TURN
    assert completion.message.text == "First part.\nSecond part."
    assert (completion.usage.input_tokens, completion.usage.output_tokens) == (900, 70)


def test_a_request_for_tools_is_read_with_ids_names_and_arguments(settings: Settings) -> None:
    model, _ = model_answering(
        settings, reply(tool_use("tooluse_a", "get_cost_by_service", limit=3), stop="tool_use")
    )

    completion = model.complete(request())

    assert completion.stop_reason is StopReason.TOOL_USE
    (call,) = completion.message.tool_calls
    assert (call.call_id, call.name, dict(call.arguments)) == (
        "tooluse_a",
        "get_cost_by_service",
        {"limit": 3},
    )


@pytest.mark.parametrize(
    ("stop", "expected"),
    [("stop_sequence", StopReason.END_TURN), ("max_tokens", StopReason.MAX_TOKENS)],
)
def test_the_other_stop_reasons_map_to_the_port(
    settings: Settings, stop: str, expected: StopReason
) -> None:
    model, _ = model_answering(settings, reply(text("cut"), stop=stop))
    assert model.complete(request()).stop_reason is expected


@pytest.mark.parametrize("stop", ["guardrail_intervened", "content_filtered"])
def test_a_withheld_response_is_schema_drift_naming_the_reason(
    settings: Settings, stop: str
) -> None:
    model, _ = model_answering(settings, reply(text("withheld"), stop=stop))
    with pytest.raises(SchemaDrift, match=stop):
        model.complete(request())


def test_an_unknown_stop_reason_is_schema_drift(settings: Settings) -> None:
    model, _ = model_answering(settings, reply(text("odd"), stop="model_context_window_exceeded"))
    with pytest.raises(SchemaDrift, match="not one this adapter knows"):
        model.complete(request())


def test_a_response_without_usage_is_schema_drift(settings: Settings) -> None:
    """Spend nobody reported cannot be recorded, and recording zero would be a lie."""
    response = reply(text("free?"))
    del response["usage"]
    model, _ = model_answering(settings, response)
    with pytest.raises(SchemaDrift, match="lacks a field"):
        model.complete(request())


@pytest.mark.parametrize(
    "response",
    [reply(stop="end_turn"), reply(text("calling"), stop="tool_use")],
    ids=["empty", "tool_use_without_a_call"],
)
def test_a_reply_that_is_not_a_completion_is_schema_drift(
    settings: Settings, response: object
) -> None:
    model, _ = model_answering(settings, response)
    with pytest.raises(SchemaDrift, match="not a completion"):
        model.complete(request())


# --- failure -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("code", "message", "cause"),
    [
        ("AccessDeniedException", NOT_ENABLED, NotOptedIn),
        (
            "AccessDeniedException",
            "User: arn:aws:sts::111122223333:assumed-role/FinOpsHubTaskRole/x is not "
            "authorized to perform: bedrock:InvokeModel",
            AccessDenied,
        ),
        ("ResourceNotFoundException", "Model not found.", Misconfigured),
        ("ValidationException", "The provided model identifier is invalid.", Misconfigured),
        ("ValidationException", "Malformed input request.", SchemaDrift),
        ("ThrottlingException", "Too many requests.", Throttled),
        ("ModelTimeoutException", "Timed out.", Unreachable),
        ("ModelNotReadyException", "Not ready.", Unreachable),
        ("ModelErrorException", "The model failed.", Unreachable),
        ("InternalServerException", "Internal error.", Unreachable),
        ("ServiceUnavailableException", "Unavailable.", Unreachable),
    ],
)
def test_every_failure_is_one_typed_cause(
    settings: Settings, code: str, message: str, cause: type[CollectionError]
) -> None:
    model = model_failing(settings, client_error(code, message))
    with pytest.raises(cause) as raised:
        model.complete(request())
    assert type(raised.value) is cause
    assert raised.value.scope_key == MODEL, "the failure names the model it was about"


def test_a_model_never_enabled_is_not_opted_in_rather_than_unreachable(settings: Settings) -> None:
    """ADR-0028's sentence about this adapter, on its own so it cannot hide in a table."""
    model = model_failing(settings, client_error("AccessDeniedException", NOT_ENABLED))
    with pytest.raises(NotOptedIn):
        model.complete(request())


def test_an_endpoint_that_does_not_answer_is_unreachable(settings: Settings) -> None:
    model = model_failing(settings, EndpointConnectionError(endpoint_url="https://example.invalid"))
    with pytest.raises(Unreachable):
        model.complete(request())


def test_every_error_code_the_adapter_names_is_one_converse_declares() -> None:
    """A misspelled code would sit in a mapping nothing exercises and fail open."""
    declared = {shape.name for shape in CONVERSE.error_shapes}
    named = {"AccessDeniedException", "ValidationException"} | bedrock.UNANSWERED
    named |= bedrock.MODEL_NOT_FOUND
    assert named <= declared, sorted(named - declared)
