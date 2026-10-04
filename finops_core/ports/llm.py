"""What the product needs of a language model, and nothing about which one.

ADR-0028 put the model on a managed service inside the hub account. This module is
the only thing the query layer knows about it: completion, the tools a model may
ask for, and the tokens a completion spent. It names no vendor, no model identifier
and no region. Those are the adapter's configuration, so changing model is a
setting and changes nothing above this line, and `tests/core/test_llm_port.py` holds
that by name rather than by intention.

**Why a port over one adapter.** Not to hedge ADR-0028. The contract suite needs one
set of sentences to hold the real adapter and the fake to, which is how every other
provider here is tested, and the evaluation sets in `tests/query/insight/` have to
run with no model at all inside `make verify`. The fake is the only thing those
tests can talk to.

**The model computes nothing.** ADR-0007. Nothing here carries a figure from a model
to a screen. A completion is prose and tool requests, and the figures an answer
shows are read out of tool results by `finops_query/insight.py`, never out of prose.

**Every refusal is typed.** A provider that declines raises one of the causes in
`finops_core.errors`, never a bare exception. A model this deployment has no access
to is `NotOptedIn` rather than `Unreachable`: a deployment without it has not
failed, it has not been enabled, and the screen says the assistant is unavailable
rather than broken.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

#: The shape a tool name takes. Narrow enough that a managed model service accepts
#: it unchanged, so an adapter never renames a tool and maps the name back, which is
#: where a call meant for one tool ends up at another.
TOOL_NAME = re.compile(r"[a-z][a-z0-9_]{0,63}")


class Role(StrEnum):
    """Who said a message. Two, because a tool result is input the model reads."""

    USER = "user"
    ASSISTANT = "assistant"


class StopReason(StrEnum):
    """Why a completion ended.

    `MAX_TOKENS` is a completion that was cut off. It is never an answer however
    complete the prose looks, because the sentence that was cut may have been the
    one saying a figure was partial.
    """

    END_TURN = "end_turn"
    TOOL_USE = "tool_use"
    MAX_TOKENS = "max_tokens"


def _no_arguments() -> dict[str, Any]:
    return {"type": "object", "properties": {}}


@dataclass(frozen=True)
class ToolSchema:
    """One tool a model may ask for. The description is how a model chooses it."""

    name: str
    description: str
    #: A JSON schema for the arguments, always an object, empty for a tool that
    #: takes none.
    parameters: Mapping[str, Any] = field(default_factory=_no_arguments)

    def __post_init__(self) -> None:
        if not TOOL_NAME.fullmatch(self.name):
            raise ValueError(
                f"tool name {self.name!r} is not lower snake case of at most 64 characters"
            )
        if not self.description.strip():
            raise ValueError(f"tool {self.name} has no description, and a model chooses by it")
        if self.parameters.get("type") != "object":
            raise ValueError(f"tool {self.name} must take its arguments as one object")


@dataclass(frozen=True)
class ToolCall:
    """A model asking for one tool. `call_id` pairs the request with its result.

    The name is deliberately not checked against `TOOL_NAME`. A model can ask for a
    tool that does not exist, and the loop has to see that name to refuse naming it,
    which it could not do if the request were refused here first.
    """

    call_id: str
    name: str
    arguments: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.call_id.strip():
            raise ValueError("a tool call without an id cannot be paired with its result")
        if not self.name.strip():
            raise ValueError("a tool call names the tool it wants")


@dataclass(frozen=True)
class ToolResult:
    """What one call returned, as the text the model reads."""

    call_id: str
    content: str
    #: True when the call failed. The model is told so, rather than handed an empty
    #: result it could read as "nothing there".
    is_error: bool = False


@dataclass(frozen=True)
class Message:
    """One turn of a conversation."""

    role: Role
    text: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    tool_results: tuple[ToolResult, ...] = ()

    def __post_init__(self) -> None:
        if self.role is Role.USER and self.tool_calls:
            raise ValueError("only the assistant asks for tools")
        if self.role is Role.ASSISTANT and self.tool_results:
            raise ValueError("tool results go back to the model, so they arrive as user input")
        if not (self.text.strip() or self.tool_calls or self.tool_results):
            raise ValueError("an empty message says nothing and still costs tokens")


@dataclass(frozen=True)
class TokenUsage:
    """What one completion spent, as the provider counted it. Constraint 7."""

    input_tokens: int
    output_tokens: int

    def __post_init__(self) -> None:
        for name in ("input_tokens", "output_tokens"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} is a count of tokens, an int")
            if value < 0:
                raise ValueError(f"{name} of {value} is not a count")

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens

    def __add__(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
        )


@dataclass(frozen=True)
class CompletionRequest:
    """A conversation, the tools the model may ask for, and how long it may answer."""

    system: str
    messages: tuple[Message, ...]
    tools: tuple[ToolSchema, ...]
    max_output_tokens: int

    def __post_init__(self) -> None:
        if not self.messages:
            raise ValueError("a completion needs something to complete")
        if self.messages[0].role is not Role.USER:
            raise ValueError("a conversation opens with the question")
        names = [tool.name for tool in self.tools]
        if len(names) != len(set(names)):
            raise ValueError("two tools share a name, so a call to that name is ambiguous")
        if self.max_output_tokens < 1:
            raise ValueError("a completion allowed no tokens can only be cut off")

    @property
    def question(self) -> str:
        """What the conversation is about: the first thing the user said."""
        return self.messages[0].text


@dataclass(frozen=True)
class Completion:
    """The model's turn, why it stopped, and what it spent."""

    message: Message
    stop_reason: StopReason
    usage: TokenUsage

    def __post_init__(self) -> None:
        if self.message.role is not Role.ASSISTANT:
            raise ValueError("a completion is the assistant's turn")
        if (self.stop_reason is StopReason.TOOL_USE) != bool(self.message.tool_calls):
            raise ValueError("a completion asks for tools exactly when it stopped to wait for them")


@runtime_checkable
class LlmProvider(Protocol):
    """A model that completes a conversation, and may ask for tools along the way."""

    def complete(self, request: CompletionRequest) -> Completion:
        """The model's next turn: prose, tool requests or both, and what it spent.

        Raises:
            AccessDenied: The platform's role may not invoke the configured model.
            NotOptedIn: This deployment has no access to the configured model. Not
                enabled rather than broken, so the assistant reads as unavailable.
            Throttled: The provider rejected the call rate or a token quota.
            Unreachable: The endpoint did not answer.
            Misconfigured: The configured model does not exist at the provider.
            SchemaDrift: The response could not be read as a completion.
        """
        ...
