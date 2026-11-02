"""The local identity provider. Reads people out of a file, and never runs in production.

ADR-0008 parks the identity provider decision. That is only affordable because
both halves of identity sit behind ports, so this implementation can be crude
without bending the shape anything else depends on. Nothing here is SAML, and
guessing at the eventual design would produce code that is thrown away and, far
worse, a port shape bent around the guess.

`METER_ENV=prod` with this provider selected is refused by the settings object
at startup, not here. A guard that lives in the thing being guarded is a guard
that a refactor removes. ISS-017.

Entitlements are cached with an explicit expiry. There is no indefinite mode,
because a revoked user has to actually lose access.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import yaml

from finops_core.domain.account import AccountKey, Provider
from finops_core.domain.identity import Entitlement, Principal
from finops_core.domain.tenant import Scope
from finops_core.errors import AccessDenied, SchemaDrift

Clock = Callable[[], datetime]

COLLECTOR = "local_config"
TIERS = ("viewer", "analyst", "owner")


def _system_clock() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class LocalUser:
    subject: str
    display_name: str
    tier: str
    is_global: bool
    accounts: tuple[str, ...]


def load_users(path: Path) -> dict[str, LocalUser]:
    """Read the file, refusing anything malformed rather than skipping it.

    A user silently dropped for a typo is a user who cannot sign in and nobody
    can explain why, so a bad entry is `SchemaDrift` and it is loud.
    """
    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries = document.get("users") or []
    users: dict[str, LocalUser] = {}
    for index, entry in enumerate(entries):
        try:
            subject = str(entry["subject"])
            tier = str(entry["tier"])
        except (KeyError, TypeError) as failure:
            raise SchemaDrift(
                scope_key=f"local_auth:entry:{index}",
                collector=COLLECTOR,
                detail="a user entry is missing subject or tier",
            ) from failure
        if tier not in TIERS:
            raise SchemaDrift(
                scope_key=f"local_auth:{subject}",
                collector=COLLECTOR,
                detail=f"tier {tier!r} is not one of {', '.join(TIERS)}",
            )
        users[subject] = LocalUser(
            subject=subject,
            display_name=str(entry.get("display_name", subject)),
            tier=tier,
            is_global=bool(entry.get("is_global", False)),
            accounts=tuple(str(a) for a in (entry.get("accounts") or ())),
        )
    return users


@dataclass(frozen=True)
class _CachedEntitlement:
    entitlement: Entitlement
    expires_at: datetime


class LocalConfigIdentityProvider:
    """Satisfies both `IdentityProvider` and `EntitlementResolver`."""

    def __init__(
        self,
        path: Path,
        tenant_id: UUID,
        cache_ttl_minutes: int,
        provider: Provider = Provider.AWS,
        clock: Clock = _system_clock,
    ) -> None:
        self._users = load_users(path)
        self._tenant_id = tenant_id
        self._provider = provider
        self._ttl = timedelta(minutes=cache_ttl_minutes)
        self._clock = clock
        self._cache: dict[str, _CachedEntitlement] = {}

    def authenticate(self, token: str) -> Principal:
        """In local development the token is the subject. Unknown is refused."""
        user = self._users.get(token)
        if user is None:
            raise AccessDenied(
                scope_key="principal:unknown",
                collector=COLLECTOR,
                detail="no such subject in the local authentication file",
            )
        return Principal(
            principal_id=user.subject,
            display_name=user.display_name,
            tenant_id=self._tenant_id,
            groups=frozenset({user.tier}),
        )

    def resolve(self, principal: Principal) -> Entitlement:
        """The scope this principal holds, cached until an explicit expiry."""
        now = self._clock()
        cached = self._cache.get(principal.principal_id)
        if cached is not None and cached.expires_at > now:
            return cached.entitlement

        user = self._users.get(principal.principal_id)
        # An unknown principal resolves to an empty scope rather than raising.
        # Empty fails closed, and an exception here tempts a caller into a
        # fallback that does not.
        accounts = (
            frozenset(AccountKey(provider=self._provider, account_id=a) for a in user.accounts)
            if user is not None and not user.is_global
            else frozenset()
        )
        entitlement = Entitlement(
            principal=principal,
            scope=Scope(
                tenant_id=self._tenant_id,
                is_global=bool(user is not None and user.is_global),
                accounts=accounts,
            ),
            as_of=now,
            collected_at=now,
        )
        self._cache[principal.principal_id] = _CachedEntitlement(
            entitlement=entitlement, expires_at=now + self._ttl
        )
        return entitlement
