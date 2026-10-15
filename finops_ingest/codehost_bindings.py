"""The code host collector, built for a deployed environment. FEAT-092, TASK-P15-004.

Beside `ai_bindings.py`, and for the same reason: it reaches GitHub over the internet through the
NAT gateway only the worker may use, ADR-0036, and its only AWS call is reading the GitHub App's
private key from Secrets Manager, through the endpoint, when a request is about to be made.
`make first-contact` makes the app's first call when its key's secret is named, TASK-P15-002.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Final

from finops_ingest.collectors.fix_pull_requests import (
    COLLECTOR,
    Connected,
    FixPullRequestsCollector,
)
from finops_ingest.registry import CollectorContext, CollectorRunner
from finops_providers.aws.reach import hub_client
from finops_providers.aws.secrets import CodeHostKeyReader
from finops_providers.github.app import GitHubApp
from finops_providers.github.code_host import GitHubCodeHost

Build = Callable[[CollectorContext], CollectorRunner]


def _now() -> datetime:
    return datetime.now(UTC)


def _fix_pull_requests(context: CollectorContext) -> CollectorRunner:
    settings = context.settings
    keys = CodeHostKeyReader(settings.env, hub_client(settings, "secretsmanager"))

    def code_host_for(_context: CollectorContext, connected: Connected) -> GitHubCodeHost:
        key = keys.reader(
            connected.key_secret_name, scope_key=f"github:{connected.app_id}", collector=COLLECTOR
        )
        return GitHubCodeHost(
            GitHubApp(app_id=connected.app_id, private_key=key, collector=COLLECTOR, clock=_now)
        )

    return FixPullRequestsCollector(code_host_for, clock=_now)


#: The code host's collector, built from the GitHub adapter and the key reader.
CODEHOST_BUILDERS: Final[dict[str, Build]] = {COLLECTOR: _fix_pull_requests}
