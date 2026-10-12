"""An AI provider's admin key, read from Secrets Manager at the moment it is needed. FEAT-083.

P13 spec section 5.5 and plan rule 2. The key lives in one secret per provider organization, under
`meter/<env>/ai/`, which is the one path the hub's task role may read for it, and the name is all
`ai_provider_account` holds. This reads the value when a request is about to be made and hands it
to the adapter, and nothing here logs it, raises it or keeps it past the call.

A name outside the path is refused before any call, Misconfigured, so a row cannot point the
worker at another secret even where the role would let it.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from finops_core.errors import Misconfigured
from finops_providers.aws.client import error_code, translate


def ai_key_prefix(env: str) -> str:
    """The only path an AI provider's key may be read from, in this environment."""
    return f"meter/{env}/ai/"


class AiKeyReader:
    """Reads one AI provider organization's admin key from Secrets Manager, by name."""

    def __init__(self, env: str, client: Any) -> None:
        self._prefix = ai_key_prefix(env)
        self._client = client

    def reader(self, name: str, *, scope_key: str, collector: str) -> Callable[[], str]:
        """A callable that reads the key when called, every failure typed."""

        def read() -> str:
            if not name.startswith(self._prefix):
                raise Misconfigured(
                    scope_key=scope_key,
                    collector=collector,
                    detail=f"the key's secret {name!r} is not under {self._prefix}, the only "
                    "path an AI provider's key may be read from",
                )
            try:
                answer = self._client.get_secret_value(SecretId=name)
            except ClientError as error:
                if error_code(error) == "ResourceNotFoundException":
                    raise Misconfigured(
                        scope_key=scope_key,
                        collector=collector,
                        detail=f"no secret named {name!r}; create it with the organization's "
                        "admin key, docs/runbooks/ai-providers.md",
                    ) from error
                raise translate(error, scope_key, collector) from error
            except BotoCoreError as error:
                raise translate(error, scope_key, collector) from error
            value = answer.get("SecretString")
            if not isinstance(value, str) or not value.strip():
                raise Misconfigured(
                    scope_key=scope_key,
                    collector=collector,
                    detail=f"the secret {name!r} holds no key as a string",
                )
            return value.strip()

        return read
