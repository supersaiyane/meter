"""The language model on Bedrock, in the hub account. Never run against AWS, ISS-002.

ADR-0028. This is the only file that names the Bedrock runtime client, and it is the
whole of what the product knows about the vendor. Everything above it talks to
`finops_core.ports.llm.LlmProvider`, and a test holds both halves of that sentence.

**Converse, not InvokeModel.** Converse speaks one request and response shape for every
model the service carries, tool use included. InvokeModel takes each model family's own
body format, so choosing a model would mean choosing a parser, and OPEN-10 would stop
being a setting.

**Every failure is one of the typed causes, and three are read more closely than the
shared translation reads them.**

- The service answers both an IAM refusal and a model nobody enabled for this account
  with `AccessDeniedException`, and they are different things to whoever reads the
  failure: one is a policy to change and the other is a model to switch on. The message
  is the only thing that tells them apart, so it is read. A model never enabled is
  `NotOptedIn`, ADR-0028. Anything not recognised stays `AccessDenied`, the conservative
  reading, because sending somebody to enable a model when their policy is wrong costs
  them an afternoon.
- A model identifier the service does not recognise is `Misconfigured`. The identifier is
  configuration, and no retry changes a typo.
- A model that did not produce an answer, through a timeout, a model not ready, or an
  error inside the service, is `Unreachable`. Retrying the question later may work, which
  is what that cause tells its reader.

**A response the service withheld is `SchemaDrift`.** A guardrail or content filter
returns a completion with nothing usable in it. None of the seven causes describes that
exactly, and it is recorded as an open question rather than forced into a better sounding
one. The detail names the stop reason, so nobody goes looking for an API change.

**Nothing here writes.** A Converse call is inference. It creates no resource, and the
task role grants it on named models only, `infra/terraform/hub/iam.tf`.

The message wording read below comes from the service documentation, not from a response
this code has seen, which is ISS-002 in one more place.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from finops_core.config import Settings
from finops_core.errors import (
    CollectionError,
    Misconfigured,
    NotOptedIn,
    SchemaDrift,
    Unreachable,
)
from finops_core.ports.llm import (
    Completion,
    CompletionRequest,
    Message,
    Role,
    StopReason,
    TokenUsage,
    ToolCall,
)
from finops_providers.aws.client import botocore_config, error_code, translate

COLLECTOR = "assistant"
SERVICE = "bedrock-runtime"

ClientFactory = Callable[[], Any]

#: An `AccessDeniedException` whose message says one of these is a model nobody enabled
#: for this account, rather than a role the service refused.
MODEL_NOT_ENABLED = ("don't have access to the model", "do not have access to the model")

#: A `ValidationException` whose message says this is a configured identifier the service
#: does not recognise, rather than a request this adapter built wrongly.
UNKNOWN_MODEL = ("model identifier is invalid",)

#: The model did not answer. Retrying the question later may work.
UNANSWERED = frozenset(
    {
        "ModelTimeoutException",
        "ModelNotReadyException",
        "ModelErrorException",
        "InternalServerException",
        "ServiceUnavailableException",
    }
)

#: The configured model does not exist at the service.
MODEL_NOT_FOUND = frozenset({"ResourceNotFoundException"})

STOP_REASONS = {
    "end_turn": StopReason.END_TURN,
    "stop_sequence": StopReason.END_TURN,
    "tool_use": StopReason.TOOL_USE,
    "max_tokens": StopReason.MAX_TOKENS,
}

#: Stop reasons meaning the service withheld the response.
WITHHELD = frozenset({"guardrail_intervened", "content_filtered"})


class BedrockModel:
    """An `LlmProvider` over Converse, for the one model this deployment names."""

    def __init__(self, settings: Settings, client_factory: ClientFactory | None = None) -> None:
        if not settings.assistant_model_id.strip():
            raise ValueError(
                "no model is configured, so there is nothing to invoke. The composition "
                "leaves the assistant unbuilt instead, and it says it is not enabled."
            )
        # What Converse is asked to run: the tagged profile where the hub stack made one,
        # ISS-230, otherwise the model itself. An exchange records the model either way.
        self._model_id = (
            settings.assistant_inference_profile_arn.strip() or settings.assistant_model_id
        )
        self._config = botocore_config(settings)
        self._factory = client_factory or self._default_client

    def _default_client(self) -> Any:
        return boto3.client(SERVICE, config=self._config)

    def complete(self, request: CompletionRequest) -> Completion:
        """One Converse call.

        Raises:
            AccessDenied: The task role may not invoke this model.
            NotOptedIn: The model has not been enabled for this account.
            Throttled: The service rejected the call rate.
            Unreachable: The endpoint or the model did not answer.
            Misconfigured: The configured model identifier is not one the service knows.
            SchemaDrift: The response could not be read as a completion, or was withheld.
        """
        try:
            response = self._factory().converse(**self._payload(request))
        except (ClientError, BotoCoreError) as failure:
            raise self._translate(failure) from failure
        return self._parse(response)

    # --- the request ---------------------------------------------------------------

    def _payload(self, request: CompletionRequest) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "modelId": self._model_id,
            "messages": [_message(message) for message in request.messages],
            "inferenceConfig": {"maxTokens": request.max_output_tokens},
        }
        if request.system.strip():
            payload["system"] = [{"text": request.system}]
        if request.tools:
            payload["toolConfig"] = {
                "tools": [
                    {
                        "toolSpec": {
                            "name": tool.name,
                            "description": tool.description,
                            "inputSchema": {"json": dict(tool.parameters)},
                        }
                    }
                    for tool in request.tools
                ]
            }
        return payload

    # --- the response --------------------------------------------------------------

    def _parse(self, response: Any) -> Completion:
        try:
            blocks = response["output"]["message"]["content"]
            reason = response["stopReason"]
            usage = TokenUsage(
                input_tokens=int(response["usage"]["inputTokens"]),
                output_tokens=int(response["usage"]["outputTokens"]),
            )
            texts = [str(block["text"]) for block in blocks if "text" in block]
            calls = tuple(
                ToolCall(
                    call_id=str(block["toolUse"]["toolUseId"]),
                    name=str(block["toolUse"]["name"]),
                    arguments=dict(block["toolUse"].get("input") or {}),
                )
                for block in blocks
                if "toolUse" in block
            )
        except (KeyError, TypeError, ValueError) as missing:
            detail = f"the response lacks a field this adapter reads: {missing}"
            raise self._drift(detail) from missing
        if reason in WITHHELD:
            raise self._drift(f"the service withheld its response, stop reason {reason}")
        stop = STOP_REASONS.get(reason)
        if stop is None:
            raise self._drift(f"stop reason {reason!r} is not one this adapter knows")
        try:
            return Completion(
                message=Message(role=Role.ASSISTANT, text="\n".join(texts), tool_calls=calls),
                stop_reason=stop,
                usage=usage,
            )
        except ValueError as malformed:
            raise self._drift(f"the response is not a completion: {malformed}") from malformed

    # --- failure -------------------------------------------------------------------

    def _translate(self, failure: Exception) -> CollectionError:
        if isinstance(failure, ClientError):
            code = error_code(failure)
            message = str(failure.response.get("Error", {}).get("Message", ""))
            detail = f"{code}: {message}".strip()
            lowered = message.lower()
            if code == "AccessDeniedException" and any(p in lowered for p in MODEL_NOT_ENABLED):
                return NotOptedIn(scope_key=self._model_id, collector=COLLECTOR, detail=detail)
            if code in MODEL_NOT_FOUND or (
                code == "ValidationException" and any(p in lowered for p in UNKNOWN_MODEL)
            ):
                return Misconfigured(scope_key=self._model_id, collector=COLLECTOR, detail=detail)
            if code in UNANSWERED:
                return Unreachable(scope_key=self._model_id, collector=COLLECTOR, detail=detail)
        return translate(failure, scope_key=self._model_id, collector=COLLECTOR)

    def _drift(self, detail: str) -> SchemaDrift:
        return SchemaDrift(scope_key=self._model_id, collector=COLLECTOR, detail=detail)


def _message(message: Message) -> dict[str, Any]:
    content: list[dict[str, Any]] = []
    if message.text.strip():
        content.append({"text": message.text})
    for call in message.tool_calls:
        content.append(
            {
                "toolUse": {
                    "toolUseId": call.call_id,
                    "name": call.name,
                    "input": dict(call.arguments),
                }
            }
        )
    for result in message.tool_results:
        content.append(
            {
                "toolResult": {
                    "toolUseId": result.call_id,
                    "content": [{"text": result.content}],
                    "status": "error" if result.is_error else "success",
                }
            }
        )
    return {"role": message.role.value, "content": content}
