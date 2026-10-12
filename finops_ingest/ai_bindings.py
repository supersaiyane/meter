"""The AI provider collectors, built for a deployed environment. FEAT-083, TASK-P13-004.

Beside `aws_bindings.py` rather than in it, because these reach a provider over the internet
through the NAT gateway only the worker may use, ADR-0036, and not AWS through an endpoint: the
only AWS call they make is reading each organization's admin key from Secrets Manager, through
the endpoint, when a request is about to be made. `make first-contact` probes the AWS reads; a
provider's first call is proved by `scripts/ops/connect_ai_provider.py` when it is connected.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Final

from finops_core.domain.ai import ProviderAccount
from finops_core.ports.ai import AiProviderReports
from finops_ingest.collectors.anthropic_usage import COLLECTOR as ANTHROPIC_COLLECTOR
from finops_ingest.collectors.anthropic_usage import anthropic_collector
from finops_ingest.collectors.openai_usage import COLLECTOR as OPENAI_COLLECTOR
from finops_ingest.collectors.openai_usage import openai_collector
from finops_ingest.registry import CollectorContext, CollectorRunner
from finops_providers.anthropic.reports import AnthropicReports
from finops_providers.aws.reach import hub_client
from finops_providers.aws.secrets import AiKeyReader
from finops_providers.openai.reports import OpenAiReports, scope_of

Build = Callable[[CollectorContext], CollectorRunner]


def _openai_usage(context: CollectorContext) -> CollectorRunner:
    settings = context.settings
    keys = AiKeyReader(settings.env, hub_client(settings, "secretsmanager"))
    tenant, run = context.unit.tenant_id, context.run_id

    def reports_for(_context: CollectorContext, account: ProviderAccount) -> AiProviderReports:
        key = keys.reader(
            account.key_secret_name, scope_key=scope_of(account), collector=OPENAI_COLLECTOR
        )
        return OpenAiReports(tenant, run, key)

    return openai_collector(reports_for)


def _anthropic_usage(context: CollectorContext) -> CollectorRunner:
    settings = context.settings
    keys = AiKeyReader(settings.env, hub_client(settings, "secretsmanager"))
    tenant, run = context.unit.tenant_id, context.run_id

    def reports_for(_context: CollectorContext, account: ProviderAccount) -> AiProviderReports:
        key = keys.reader(
            account.key_secret_name, scope_key=scope_of(account), collector=ANTHROPIC_COLLECTOR
        )
        return AnthropicReports(tenant, run, key)

    return anthropic_collector(reports_for)


#: Each AI provider's collector, built from its adapter and the key reader.
AI_PROVIDER_BUILDERS: Final[dict[str, Build]] = {
    ANTHROPIC_COLLECTOR: _anthropic_usage,
    OPENAI_COLLECTOR: _openai_usage,
}
