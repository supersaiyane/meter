"""The model the assistant runs on, chosen by configuration. ADR-0028.

Composition has to name the adapter somewhere, and ADR-0028 says nothing above the
providers may name a model or a vendor, so it is named here, behind a neutral name the API's
bootstrap can import without naming either.

None where no model is configured, which is OPEN-10 unanswered: the assistant is then
unbuilt and every question says it is not enabled.
"""

from __future__ import annotations

from finops_core.config import Settings
from finops_core.ports.llm import LlmProvider
from finops_providers.aws.bedrock import BedrockModel


def language_model(settings: Settings) -> LlmProvider | None:
    """The configured model, or None where none is."""
    if not settings.assistant_model_id.strip():
        return None
    return BedrockModel(settings)
