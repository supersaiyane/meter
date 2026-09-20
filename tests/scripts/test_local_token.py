"""The one thing about a token minting script that has to be true.

It signs a session from a command line. Everything else in `local_token.py` is
convenience; the refusal is the part that matters, and it is the part that would be
quietly removed by somebody who wanted to run it against staging once.

Deliberately not testing that a minted token verifies. That is `SessionSigner`'s own
suite, and asserting it again here would mean this file passes whenever the signer
does, which tells nobody anything about the refusal.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

# Loaded by path, not imported as a package, because `scripts/` deliberately is not
# one. `tests/scripts/test_seed_demo.py` does the same, and importing it as
# `scripts.ops.local_token` makes mypy resolve one file under two module names.
SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ops" / "local_token.py"
_spec = importlib.util.spec_from_file_location("local_token", SCRIPT)
assert _spec is not None and _spec.loader is not None
local_token = importlib.util.module_from_spec(_spec)
sys.modules["local_token"] = local_token
_spec.loader.exec_module(local_token)

LOCAL_ENVIRONMENTS = local_token.LOCAL_ENVIRONMENTS
NotLocalError = local_token.NotLocalError
require_local = local_token.require_local


class TestItRefusesAnythingNotLocal:
    @pytest.mark.parametrize("environment", ["prod", "staging", "production", "", "LOCAL"])
    def test_a_real_environment_is_refused(self, environment: str) -> None:
        with pytest.raises(NotLocalError):
            require_local(environment)

    def test_staging_is_refused_as_well_as_prod(self) -> None:
        # A staging session is still somebody's session, and staging is the environment
        # a tool like this most plausibly drifts into.
        assert "staging" not in LOCAL_ENVIRONMENTS
        with pytest.raises(NotLocalError):
            require_local("staging")

    def test_the_refusal_names_the_environment_it_refused(self) -> None:
        # Somebody who sees this needs to know which configuration was loaded, not only
        # that something was wrong.
        with pytest.raises(NotLocalError, match="prod"):
            require_local("prod")

    @pytest.mark.parametrize("environment", sorted(LOCAL_ENVIRONMENTS))
    def test_every_allowed_environment_is_accepted(self, environment: str) -> None:
        require_local(environment)

    def test_the_allowed_list_is_small_enough_to_read(self) -> None:
        # A guard that admits most values is not a guard. If this list grows, the
        # growth should be deliberate enough to change a test.
        assert frozenset({"local", "dev"}) == LOCAL_ENVIRONMENTS
