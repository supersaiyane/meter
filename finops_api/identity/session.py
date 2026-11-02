"""Signed sessions that carry the scope they were issued with.

The scope travels inside the token so a request does not have to resolve
entitlements again on every call, and the signature is what stops a caller
editing it. An unsigned or edited token is refused as `AccessDenied`, with no
detail about which of the two it was: telling the caller is a free oracle for
whoever is guessing.

Every session has an expiry. There is no unbounded variant, because a session
that never ends is a revocation that never takes effect.
"""

from __future__ import annotations

import base64
import hmac
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import UUID

from finops_core.domain.account import AccountKey, Provider
from finops_core.domain.tenant import Scope
from finops_core.errors import AccessDenied

Clock = Callable[[], datetime]

COLLECTOR = "session"


def _system_clock() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class Session:
    """A verified session. Never constructed from an unverified token."""

    principal_id: str
    subject: str
    tenant_id: UUID
    scope: Scope
    issued_at: datetime
    expires_at: datetime


def _encode(payload: dict[str, object]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _account_key(entry: str) -> AccountKey:
    provider, _, account_id = entry.partition(":")
    return AccountKey(provider=Provider(provider), account_id=account_id)


def _decode(segment: str) -> dict[str, object]:
    padded = segment + "=" * (-len(segment) % 4)
    decoded = json.loads(base64.urlsafe_b64decode(padded.encode()).decode())
    if not isinstance(decoded, dict):
        raise ValueError("session payload is not an object")
    return decoded


class SessionSigner:
    """Issues and verifies session tokens."""

    def __init__(self, signing_key: str, ttl_hours: int, clock: Clock = _system_clock) -> None:
        if not signing_key:
            raise ValueError("A session signing key is required. See METER_SESSION_SIGNING_KEY.")
        self._key = signing_key.encode()
        self._ttl = timedelta(hours=ttl_hours)
        self._clock = clock

    def issue(self, principal_id: str, subject: str, scope: Scope) -> str:
        issued_at = self._clock()
        payload: dict[str, object] = {
            "principal_id": principal_id,
            "subject": subject,
            "tenant_id": str(scope.tenant_id),
            "is_global": scope.is_global,
            "accounts": sorted(f"{k.provider.value}:{k.account_id}" for k in scope.accounts),
            "issued_at": issued_at.isoformat(),
            "expires_at": (issued_at + self._ttl).isoformat(),
        }
        body = _encode(payload)
        return f"{body}.{self._signature(body)}"

    def verify(self, token: str) -> Session:
        body, separator, signature = token.partition(".")
        if not separator or not hmac.compare_digest(signature, self._signature(body)):
            # Missing, malformed and forged are one answer on purpose.
            raise AccessDenied(
                scope_key="principal:unknown",
                collector=COLLECTOR,
                detail="the session token was not issued by this service",
            )
        try:
            payload = _decode(body)
            expires_at = datetime.fromisoformat(str(payload["expires_at"]))
            issued_at = datetime.fromisoformat(str(payload["issued_at"]))
        except (ValueError, KeyError) as failure:
            raise AccessDenied(
                scope_key="principal:unknown",
                collector=COLLECTOR,
                detail="the session token could not be read",
            ) from failure

        if self._clock() >= expires_at:
            raise AccessDenied(
                scope_key=f"principal:{payload.get('principal_id')}",
                collector=COLLECTOR,
                detail="the session has expired. Sign in again.",
            )

        encoded_accounts = payload.get("accounts", [])
        if not isinstance(encoded_accounts, list):
            raise AccessDenied(
                scope_key="principal:unknown",
                collector=COLLECTOR,
                detail="the session token carried a malformed scope",
            )
        accounts = frozenset(_account_key(str(entry)) for entry in encoded_accounts)
        return Session(
            principal_id=str(payload["principal_id"]),
            subject=str(payload["subject"]),
            tenant_id=UUID(str(payload["tenant_id"])),
            scope=Scope(
                tenant_id=UUID(str(payload["tenant_id"])),
                is_global=bool(payload["is_global"]),
                accounts=accounts,
            ),
            issued_at=issued_at,
            expires_at=expires_at,
        )

    def _signature(self, body: str) -> str:
        digest = hmac.new(self._key, body.encode(), sha256).digest()
        return base64.urlsafe_b64encode(digest).decode().rstrip("=")
