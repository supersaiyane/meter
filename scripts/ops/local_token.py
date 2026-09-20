"""A session token for the local stack, and nothing else.

There is no login screen and no login route. `get_principal` verifies a signed
session, and nothing in the product mints one, so until this existed the only way to
open a screen locally was a Python one liner inside the API container that nobody had
written down. That is a real obstacle to demonstrating the product, and a reader who
cannot get past it concludes the build is broken.

**Local only, and it refuses before it signs.** It signs with the key the local stack
is configured with, so it can only ever produce a token that stack accepts. Running it
against a production configuration would mint a real session from a command line,
which is why `METER_ENV` is checked before a key is read rather than after.

**It mints the scope the subject is entitled to, and that matters here.** A commitment
is payer wide, so `/cost/commitments` returns nothing to a narrowed session and the
screen says so. Demonstrating that screen needs a subject with `is_global`, and a
person who does not know that concludes the feature is broken. The default is such a
subject, and the help text says why.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from uuid import UUID

from finops_api.identity.local_config import load_users
from finops_api.identity.session import SessionSigner
from finops_core.config import load_settings
from finops_core.domain.account import AccountKey, Provider
from finops_core.domain.tenant import Scope

#: Environments this may run in. `staging` is absent as well as `prod`: a staging
#: session is still somebody's session.
LOCAL_ENVIRONMENTS = frozenset({"local", "dev"})


class NotLocalError(RuntimeError):
    """The configuration is not one this script is allowed to sign for."""


def require_local(environment: str) -> None:
    """Refuse anything that is not a local configuration.

    The whole risk of a token minting tool is that it runs somewhere real.
    """
    if environment not in LOCAL_ENVIRONMENTS:
        raise NotLocalError(
            f"METER_ENV is {environment!r}. This mints a session from a command line "
            f"and may only run in {', '.join(sorted(LOCAL_ENVIRONMENTS))}."
        )


def build(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mint a local session token.")
    parser.add_argument(
        "--subject",
        default="auditor@example.local",
        help=(
            "Who to sign in as, from local-auth.yaml. The default sees every account, "
            "which is what the commitments screen needs: a commitment is payer wide "
            "and a narrowed session reads nothing there."
        ),
    )
    parser.add_argument(
        "--tenant",
        default=None,
        help="Tenant id. Defaults to METER_LOCAL_TENANT_ID, which `make seed` prints.",
    )
    parser.add_argument(
        "--explain",
        action="store_true",
        help=(
            "Print the browser console line and the two sentences somebody needs "
            "before they can use the token. `make token` passes this; a script "
            "capturing the token should not."
        ),
    )
    options = parser.parse_args(argv)

    settings = load_settings()
    require_local(settings.env)

    users = load_users(Path(settings.local_auth_file))
    user = users.get(options.subject)
    if user is None:
        known = ", ".join(sorted(users)) or "none"
        print(
            f"No such subject {options.subject!r} in {settings.local_auth_file}. "
            f"Known subjects: {known}",
            file=sys.stderr,
        )
        return 2

    tenant = UUID(options.tenant) if options.tenant else settings.local_tenant_id
    scope = Scope(
        tenant_id=tenant,
        is_global=user.is_global,
        accounts=frozenset(
            AccountKey(provider=Provider.AWS, account_id=account) for account in user.accounts
        ),
    )
    signer = SessionSigner(settings.session_signing_key, ttl_hours=settings.session_ttl_hours)
    token = signer.issue(user.subject, user.subject, scope)

    if not options.explain:
        # The token alone on stdout, so a script can capture it.
        print(token)
        return 0

    print()
    print("Paste this into the browser console at the app, then reload:")
    print()
    print(f"localStorage.setItem('meter.token', '{token}'); location.reload()")
    print()
    print(f"Valid for {settings.session_ttl_hours} hours. Subject {user.subject}.")
    if user.is_global:
        print(
            "This subject sees every account, which the commitments screen needs: a "
            "commitment is payer wide and a narrowed session reads nothing there."
        )
    else:
        print(
            f"{user.subject} is scoped to {len(user.accounts)} account ids. If the seed "
            "never created them, every screen shows an empty estate that looks like a "
            "bug rather than like a scope."
        )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(build())
