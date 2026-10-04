"""A Converse double that refuses any request the service model would refuse.

Shared by the adapter's tests and the `LlmProvider` contract suite. It answers by
question, so two tests asking two things of one model each get their own reply, and it
validates every request against the input shape botocore ships before answering. That
is the half of ISS-002 a test can close offline: whatever the adapter sends is a request
the service would accept, by the same model the SDK builds its client from.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import botocore.session
from botocore.exceptions import ClientError
from botocore.validate import validate_parameters

CONVERSE = (
    botocore.session.get_session().get_service_model("bedrock-runtime").operation_model("Converse")
)

#: The message the service documentation gives for a model never enabled for the account.
NOT_ENABLED = "You don't have access to the model with the specified model ID."


def reply(
    *blocks: Mapping[str, Any],
    stop: str = "end_turn",
    input_tokens: int = 412,
    output_tokens: int = 38,
) -> dict[str, Any]:
    """One Converse response with the given content blocks."""
    return {
        "output": {"message": {"role": "assistant", "content": [dict(b) for b in blocks]}},
        "stopReason": stop,
        "usage": {
            "inputTokens": input_tokens,
            "outputTokens": output_tokens,
            "totalTokens": input_tokens + output_tokens,
        },
        "metrics": {"latencyMs": 900},
    }


def text(words: str) -> dict[str, Any]:
    return {"text": words}


def tool_use(call_id: str, name: str, **arguments: Any) -> dict[str, Any]:
    return {"toolUse": {"toolUseId": call_id, "name": name, "input": arguments}}


def client_error(code: str, message: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": message}}, "Converse")


class ConverseDouble:
    """Answers `converse` by the conversation's first question."""

    def __init__(
        self,
        replies: Mapping[str, Mapping[str, Any]] | None = None,
        error: Exception | None = None,
    ) -> None:
        self._replies = dict(replies or {})
        self._error = error
        self.sent: list[dict[str, Any]] = []

    def converse(self, **params: Any) -> Mapping[str, Any]:
        # Raises ParamValidationError for anything the service model would refuse.
        validate_parameters(params, CONVERSE.input_shape)
        self.sent.append(params)
        if self._error is not None:
            raise self._error
        question = params["messages"][0]["content"][0]["text"]
        return self._replies[question]
