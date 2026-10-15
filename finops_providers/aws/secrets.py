"""A key read from Secrets Manager at the moment it is needed. FEAT-083 and FEAT-091.

P13 spec section 5.5 and plan rule 2, and P15 spec section 5.1. An AI provider organization's admin
key lives in one secret each under `meter/<env>/ai/`, and the code host app's private key under
`meter/<env>/codehost/`: the paths the hub's task role may read them from, and the name is all a
row holds. This reads the value when a request is about to be made and hands it to the adapter,
and nothing here logs it, raises it or keeps it past the call.

A name outside its path is refused before any call, Misconfigured, so a row cannot point the
worker at another secret even where the role would let it, the other path's included.
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


def codehost_key_prefix(env: str) -> str:
    """The only path the code host app's private key may be read from, in this environment."""
    return f"meter/{env}/codehost/"


class SecretReader:
    """Reads one secret under one path from Secrets Manager, by name, when it is needed."""

    def __init__(self, prefix: str, client: Any, *, holds: str, create: str) -> None:
        self._prefix = prefix
        self._client = client
        #: What the path holds, for a refusal: "an AI provider's key".
        self._holds = holds
        #: How to make the secret, for a refusal when it does not exist.
        self._create = create

    def reader(self, name: str, *, scope_key: str, collector: str) -> Callable[[], str]:
        """A callable that reads the key when called, every failure typed."""

        def read() -> str:
            if not name.startswith(self._prefix):
                raise Misconfigured(
                    scope_key=scope_key,
                    collector=collector,
                    detail=f"the key's secret {name!r} is not under {self._prefix}, the only "
                    f"path {self._holds} may be read from",
                )
            try:
                answer = self._client.get_secret_value(SecretId=name)
            except ClientError as error:
                if error_code(error) == "ResourceNotFoundException":
                    raise Misconfigured(
                        scope_key=scope_key,
                        collector=collector,
                        detail=f"no secret named {name!r}; {self._create}",
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


class AiKeyReader(SecretReader):
    """Reads one AI provider organization's admin key from Secrets Manager, by name."""

    def __init__(self, env: str, client: Any) -> None:
        super().__init__(
            ai_key_prefix(env),
            client,
            holds="an AI provider's key",
            create="create it with the organization's admin key, docs/runbooks/ai-providers.md",
        )


class CodeHostKeyReader(SecretReader):
    """Reads the code host app's private key from Secrets Manager, by name. FEAT-091."""

    def __init__(self, env: str, client: Any) -> None:
        super().__init__(
            codehost_key_prefix(env),
            client,
            holds="the code host app's private key",
            create="create it with the GitHub App's private key, docs/runbooks/code-host.md",
        )
