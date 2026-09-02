"""The local identity provider, the session it issues, and what a partial view reports.

Three failures are being prevented here and each one is quiet rather than loud.

ISS-017: a local provider reaching production is not a degraded authentication,
it is no authentication. Nothing in the running system would look wrong.

ISS-016: entitlement based visibility silently makes organization totals
partial. A user entitled to two of five accounts asks for total cost and gets a
true answer to a question nobody asked.

An entitlement cached without an expiry means a revoked user keeps access, and
the only symptom is that nothing happens when access is revoked.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from finops_api.identity import (
    LocalConfigIdentityProvider,
    ScopeCoverage,
    SessionSigner,
    load_users,
)
from finops_core.domain.account import AccountKey, Provider
from finops_core.domain.tenant import Scope
from finops_core.errors import AccessDenied, SchemaDrift

ROOT = Path(__file__).resolve().parent.parent.parent
AUTH_FILE = ROOT / "local-auth.example.yaml"
TENANT = uuid4()
START = datetime(2026, 8, 24, 6, 0, tzinfo=UTC)
KEY = "test-signing-key-not-a-real-one"


class MovableClock:
    """A clock a test moves on purpose, so nothing depends on wall time."""

    def __init__(self, at: datetime) -> None:
        self.at = at

    def __call__(self) -> datetime:
        return self.at


def provider(
    clock: MovableClock | None = None, ttl_minutes: int = 15
) -> LocalConfigIdentityProvider:
    return LocalConfigIdentityProvider(
        AUTH_FILE, TENANT, ttl_minutes, clock=clock or MovableClock(START)
    )


# --- reading the file --------------------------------------------------------


def test_the_provider_reads_users_accounts_and_tiers() -> None:
    users = load_users(AUTH_FILE)
    assert "dev@example.local" in users
    assert users["dev@example.local"].tier == "analyst"
    assert users["dev@example.local"].accounts == ("111122223333", "444455556666")
    assert users["auditor@example.local"].is_global is True


def test_a_malformed_tier_is_loud_rather_than_skipped(tmp_path: Path) -> None:
    """A user silently dropped for a typo cannot sign in and nobody can say why."""
    bad = tmp_path / "local-auth.yaml"
    bad.write_text("users:\n  - subject: a@b\n    tier: superuser\n", encoding="utf-8")
    with pytest.raises(SchemaDrift):
        load_users(bad)


def test_a_user_entry_missing_its_subject_is_loud(tmp_path: Path) -> None:
    bad = tmp_path / "local-auth.yaml"
    bad.write_text("users:\n  - tier: viewer\n", encoding="utf-8")
    with pytest.raises(SchemaDrift):
        load_users(bad)


# --- authentication ----------------------------------------------------------


def test_an_unknown_subject_is_refused() -> None:
    with pytest.raises(AccessDenied):
        provider().authenticate("nobody@example.local")


def test_a_known_subject_resolves_to_its_accounts() -> None:
    subject = provider()
    entitlement = subject.resolve(subject.authenticate("dev@example.local"))
    assert entitlement.scope.is_global is False
    assert {key.account_id for key in entitlement.scope.accounts} == {
        "111122223333",
        "444455556666",
    }


def test_a_global_user_gets_a_global_scope_and_enumerates_nothing() -> None:
    subject = provider()
    entitlement = subject.resolve(subject.authenticate("auditor@example.local"))
    assert entitlement.scope.is_global is True
    assert entitlement.scope.accounts == frozenset()


def test_an_unknown_principal_resolves_to_an_empty_scope_rather_than_raising() -> None:
    from finops_core.domain.identity import Principal

    stranger = Principal(
        principal_id="ghost", display_name="Ghost", tenant_id=TENANT, groups=frozenset()
    )
    entitlement = provider().resolve(stranger)
    assert entitlement.scope.accounts == frozenset()
    assert entitlement.scope.is_global is False


# --- the entitlement cache ---------------------------------------------------


def test_entitlements_are_cached_within_the_expiry() -> None:
    clock = MovableClock(START)
    subject = provider(clock, ttl_minutes=15)
    principal = subject.authenticate("dev@example.local")
    first = subject.resolve(principal)
    clock.at = START + timedelta(minutes=14)
    assert subject.resolve(principal) is first


def test_the_cache_expires_so_a_revoked_user_loses_access() -> None:
    clock = MovableClock(START)
    subject = provider(clock, ttl_minutes=15)
    principal = subject.authenticate("dev@example.local")
    first = subject.resolve(principal)
    clock.at = START + timedelta(minutes=16)
    assert subject.resolve(principal) is not first


def test_a_cached_entitlement_carries_the_time_it_was_resolved() -> None:
    subject = provider()
    entitlement = subject.resolve(subject.authenticate("dev@example.local"))
    assert entitlement.as_of == START
    assert entitlement.collected_at == START


# --- sessions ----------------------------------------------------------------


def scope_of(*account_ids: str) -> Scope:
    return Scope(
        tenant_id=TENANT,
        is_global=False,
        accounts=frozenset(AccountKey(provider=Provider.AWS, account_id=i) for i in account_ids),
    )


def test_a_session_round_trips_the_scope_it_was_issued_with() -> None:
    signer = SessionSigner(KEY, ttl_hours=8, clock=MovableClock(START))
    token = signer.issue("dev@example.local", "dev@example.local", scope_of("a", "b"))
    session = signer.verify(token)
    assert {key.account_id for key in session.scope.accounts} == {"a", "b"}
    assert session.tenant_id == TENANT


def test_session_expires() -> None:
    clock = MovableClock(START)
    signer = SessionSigner(KEY, ttl_hours=8, clock=clock)
    token = signer.issue("dev@example.local", "dev@example.local", scope_of("a"))
    clock.at = START + timedelta(hours=8, seconds=1)
    with pytest.raises(AccessDenied, match="expired"):
        signer.verify(token)


def test_a_session_is_still_valid_just_before_it_expires() -> None:
    clock = MovableClock(START)
    signer = SessionSigner(KEY, ttl_hours=8, clock=clock)
    token = signer.issue("dev@example.local", "dev@example.local", scope_of("a"))
    clock.at = START + timedelta(hours=7, minutes=59)
    assert signer.verify(token).subject == "dev@example.local"


def test_an_edited_scope_is_refused() -> None:
    """The signature is the only thing between a viewer and a global read."""
    signer = SessionSigner(KEY, ttl_hours=8, clock=MovableClock(START))
    token = signer.issue("dev@example.local", "dev@example.local", scope_of("a"))
    body, _, signature = token.partition(".")
    forged = f"{body[:-2]}xx.{signature}"
    with pytest.raises(AccessDenied):
        signer.verify(forged)


def test_a_token_signed_with_another_key_is_refused() -> None:
    issued = SessionSigner(KEY, ttl_hours=8, clock=MovableClock(START)).issue(
        "dev@example.local", "dev@example.local", scope_of("a")
    )
    other = SessionSigner("a-different-key", ttl_hours=8, clock=MovableClock(START))
    with pytest.raises(AccessDenied):
        other.verify(issued)


def test_a_token_with_no_signature_is_refused() -> None:
    signer = SessionSigner(KEY, ttl_hours=8, clock=MovableClock(START))
    with pytest.raises(AccessDenied):
        signer.verify("not-a-token")


def test_a_signer_without_a_key_is_refused_at_construction() -> None:
    with pytest.raises(ValueError, match="signing key"):
        SessionSigner("", ttl_hours=8)


# --- scope coverage, ISS-016 -------------------------------------------------


def test_scope_coverage_reports_partial_visibility() -> None:
    """Two of five, not two of two. The second is the bug itself."""
    coverage = ScopeCoverage(visible=2, total=5)
    assert coverage.is_partial is True
    assert coverage.fraction == pytest.approx(0.4)
    assert coverage.as_dict() == {"visible": 2, "total": 5, "is_partial": True}


def test_full_visibility_is_not_reported_as_partial() -> None:
    assert ScopeCoverage(visible=5, total=5).is_partial is False


def test_coverage_refuses_a_total_computed_from_the_visible_set() -> None:
    """A total smaller than the visible count is ISS-016 arriving in person."""
    with pytest.raises(ValueError, match="ISS-016"):
        ScopeCoverage(visible=5, total=2)


def test_an_empty_organization_is_fully_covered() -> None:
    coverage = ScopeCoverage(visible=0, total=0)
    assert coverage.fraction == 1.0
    assert coverage.is_partial is False


def test_negative_counts_are_refused() -> None:
    with pytest.raises(ValueError, match="negative"):
        ScopeCoverage(visible=-1, total=5)
