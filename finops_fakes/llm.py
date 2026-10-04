"""A model that plays a script. Same request in, same completion out.

P7 spec section 11. An evaluation suite run against a sampling model measures the
sampler, so everything above `LlmProvider` is tested against this instead, and the
evaluation sets run inside `make verify` with no model and no network.

**How it chooses a reply.** The question is the first user message, and the turn is
how many assistant messages the conversation already holds. A script maps a question
to the turns it plays, in order. Nothing else is read, so the same request gets the
same completion every time, and a test asserts that rather than assuming it.

**An unscripted question gets one fixed reply**, prose that answers nothing. A test
that forgot to script its question then fails on a reply that is visibly not an
answer, rather than passing on something the fake improvised.

**Token counts are a pure function of the text,** at a fixed number of characters a
token. Not a provider's tokenizer and not meant to be one: they exist so the cost path
carries a figure that is neither zero nor random. A self metering product whose newest
feature reported a cost of zero would be making the mistake it was built to catch.

**It can be unavailable.** `ScriptedModel.unavailable()` raises `NotOptedIn` on every
call, which is what a deployment with no access to its configured model sees.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from finops_core.errors import CollectionError, NotOptedIn
from finops_core.ports.llm import (
    Completion,
    CompletionRequest,
    Message,
    Role,
    StopReason,
    TokenUsage,
)

#: Not a tokenizer. A fixed ratio keeps the count a pure function of the text, which
#: is the property the tests need, and four is the figure usually quoted for prose.
CHARACTERS_PER_TOKEN = 4

#: Where a failure is said to have happened. The assistant is not a collector, and a
#: typed cause still needs both fields, so these name the thing that failed.
SCOPE = "hub"
COLLECTOR = "assistant"

UNSCRIPTED = "This scripted model has no reply for that question at this turn."

UNAVAILABLE = "the configured model is not enabled for this deployment"

Script = Mapping[str, Sequence[Message]]


class ScriptedModel:
    """An `LlmProvider` that plays the turns a script names, in order."""

    def __init__(
        self,
        script: Script | None = None,
        *,
        failure: type[CollectionError] | None = None,
        failure_detail: str = "",
    ) -> None:
        for question, turns in (script or {}).items():
            if any(turn.role is not Role.ASSISTANT for turn in turns):
                raise ValueError(f"the script for {question!r} hands the model a user turn")
        self._script = dict(script or {})
        self._failure = failure
        self._failure_detail = failure_detail
        self._received: list[CompletionRequest] = []

    @classmethod
    def unavailable(cls) -> ScriptedModel:
        """A deployment with no access to its configured model."""
        return cls(failure=NotOptedIn, failure_detail=UNAVAILABLE)

    @property
    def received(self) -> tuple[CompletionRequest, ...]:
        """Every request this model was sent, in order. Empty means nothing was sent."""
        return tuple(self._received)

    def complete(self, request: CompletionRequest) -> Completion:
        self._received.append(request)
        if self._failure is not None:
            # A new instance each time. Raising one instance twice carries the first
            # traceback into the second failure, and a test reading it is misled.
            raise self._failure(scope_key=SCOPE, collector=COLLECTOR, detail=self._failure_detail)
        message = self._reply(request)
        return Completion(
            message=message,
            stop_reason=StopReason.TOOL_USE if message.tool_calls else StopReason.END_TURN,
            usage=TokenUsage(
                input_tokens=_tokens(_rendered_request(request)),
                output_tokens=_tokens(_rendered_message(message)),
            ),
        )

    def _reply(self, request: CompletionRequest) -> Message:
        turn = sum(1 for message in request.messages if message.role is Role.ASSISTANT)
        turns = self._script.get(request.question, ())
        if turn < len(turns):
            return turns[turn]
        return Message(role=Role.ASSISTANT, text=UNSCRIPTED)


def _tokens(text: str) -> int:
    return -(-len(text) // CHARACTERS_PER_TOKEN)


def _json(value: Mapping[str, Any]) -> str:
    return json.dumps(dict(value), sort_keys=True, default=str)


def _rendered_message(message: Message) -> str:
    calls = "".join(f"{call.name}{_json(call.arguments)}" for call in message.tool_calls)
    results = "".join(result.content for result in message.tool_results)
    return f"{message.text}{calls}{results}"


def _rendered_request(request: CompletionRequest) -> str:
    tools = "".join(
        f"{tool.name}{tool.description}{_json(tool.parameters)}" for tool in request.tools
    )
    messages = "".join(_rendered_message(message) for message in request.messages)
    return f"{request.system}{messages}{tools}"
