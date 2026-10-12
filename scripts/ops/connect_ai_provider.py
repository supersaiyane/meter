"""Connect one AI provider organization to a tenant, once its key has read a day of its costs.

TASK-P13-004, FEAT-083, P13 spec section 5.5. The owner puts the organization's admin key in a
Secrets Manager secret under `meter/<env>/ai/`, then runs this with the secret's name. It reads
the key through the same reader the worker uses, asks the provider for one day of costs, and only
when that answers records the organization in `ai_provider_account`, so a row exists only for an
organization whose key was proved. The key is never printed, logged or stored; the row holds the
secret's name. Running it again for a connected organization updates its name and secret and
makes it active.

    METER_DATABASE_URL=... AWS_REGION=<hub Region> python scripts/ops/connect_ai_provider.py \\
        --env dev --tenant <uuid> --provider openai --organization org-... \\
        --name "Platform team" --secret meter/dev/ai/openai-platform

Exit codes: 0 connected, 2 a setting or an argument is missing or wrong, 3 the key could not be
read or the provider refused it, with the typed cause.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, Final
from uuid import UUID, uuid4

from sqlalchemy import text

from finops_core.domain.ai import ProviderAccount
from finops_core.errors import CollectionError
from finops_core.ports.ai import AiProviderReports
from finops_providers.aws.secrets import AiKeyReader, ai_key_prefix
from finops_providers.openai.reports import COLLECTOR as OPENAI_COLLECTOR
from finops_providers.openai.reports import OpenAiReports, scope_of

#: How each provider's reports are made from a key, and the collector its failures are named for.
Factory = Callable[[Callable[[], str]], AiProviderReports]
PROVIDERS: Final[dict[str, tuple[Factory, str]]] = {
    "openai": (lambda key: OpenAiReports(uuid4(), uuid4(), key), OPENAI_COLLECTOR),
}

CONNECT = text(
    "INSERT INTO ai_provider_account (provider, organization_id, tenant_id, name, "
    "key_secret_name, enrolled_at, active) VALUES (:provider, :organization, :tenant, :name, "
    ":secret, :now, true) ON CONFLICT ON CONSTRAINT pk_ai_provider_account DO UPDATE SET "
    "name = EXCLUDED.name, key_secret_name = EXCLUDED.key_secret_name, active = true "
    "WHERE ai_provider_account.tenant_id = EXCLUDED.tenant_id"
)


def prove(reports: AiProviderReports, account: ProviderAccount, now: datetime) -> int:
    """One day of costs, read with the key. Returns how many lines it holds."""
    return len(tuple(reports.costs(account, now - timedelta(days=1), now)))


def connect(connection: Any, account: ProviderAccount, tenant: UUID, now: datetime) -> bool:
    """Record the organization for the tenant. False when another tenant already holds it."""
    result = connection.execute(
        CONNECT,
        {
            "provider": account.provider,
            "organization": account.organization_id,
            "tenant": tenant,
            "name": account.name,
            "secret": account.key_secret_name,
            "now": now,
        },
    )
    return bool(result.rowcount)


def main(
    argv: list[str] | None = None,
    *,
    secrets: Any = None,
    factory: Factory | None = None,
    clock: Callable[[], datetime] | None = None,
) -> int:
    parser = argparse.ArgumentParser(description="Connect one AI provider organization.")
    parser.add_argument("--env", required=True, help="the environment whose AI path holds the key")
    parser.add_argument("--tenant", required=True, type=UUID)
    parser.add_argument("--provider", required=True, choices=sorted(PROVIDERS))
    parser.add_argument("--organization", required=True, help="the provider's organization id")
    parser.add_argument("--name", required=True, help="what Meter's screens call it")
    parser.add_argument("--secret", required=True, help="the Secrets Manager secret's name")
    args = parser.parse_args(argv)

    prefix = ai_key_prefix(args.env)
    if not args.secret.startswith(prefix):
        print(f"the secret must be under {prefix}", file=sys.stderr)
        return 2
    url = os.environ.get("METER_DATABASE_URL")
    if not url:
        print("METER_DATABASE_URL is not set", file=sys.stderr)
        return 2

    make, collector = PROVIDERS[args.provider]
    account = ProviderAccount(
        provider=args.provider,
        organization_id=args.organization,
        name=args.name,
        key_secret_name=args.secret,
    )
    if secrets is None:  # pragma: no cover - the deployed path, a real client
        import boto3

        secrets = boto3.client("secretsmanager")
    key = AiKeyReader(args.env, secrets).reader(
        args.secret, scope_key=scope_of(account), collector=collector
    )
    now = (clock or (lambda: datetime.now(UTC)))()
    try:
        lines = prove((factory or make)(key), account, now)
    except CollectionError as failure:
        print(f"not connected: {failure.cause}: {failure.detail}", file=sys.stderr)
        return 3

    from sqlalchemy import create_engine

    with create_engine(url).begin() as connection:
        if not connect(connection, account, args.tenant, now):
            print(
                f"not connected: {args.provider} {args.organization} belongs to another tenant",
                file=sys.stderr,
            )
            return 2
    print(f"connected {args.provider} {args.organization}: its key read {lines} cost lines")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
