# Basic boiler Plate Doc | Grade B
# Why this file exists: Shared test setup, deliberately minimal. It also refuses to run the
# suite against a real cloud account, which is the idea worth copying.
# Grade B here: copy it, then replace the guard's environment variable names.
# Grades: A copy into a new project as is, no edits. B copy it and swap the
# names, paths or patterns named above. C leave behind, it is this project's
# own content rather than scaffolding, and is not tagged.

"""Shared pytest configuration.

Two things are set up here and nothing else. Fixtures that belong to one layer
live next to that layer's tests, because a conftest that grows into a shared
fixture library becomes a file every test depends on and nobody understands.

1. `anyio_backend`, so async tests run on asyncio without each one declaring it.
2. A guard that refuses to run the suite against a real AWS account.
"""

from __future__ import annotations

import os

import pytest


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True, scope="session")
def _refuse_real_aws() -> None:
    """Fail the run rather than let a test touch a real account.

    The port contract suite runs against `moto` and the fake provider, and the
    local stack points at LocalStack. If a real credential is present and no
    endpoint override is set, a test that forgets to patch a client would reach
    a live account, and in this product that means reading somebody's billing
    data from a unit test.

    Cheaper to refuse than to find out afterwards from CloudTrail.
    """
    endpoint = os.environ.get("AWS_ENDPOINT_URL", "")
    profile = os.environ.get("AWS_PROFILE", "")
    key = os.environ.get("AWS_ACCESS_KEY_ID", "")

    looks_real = bool(profile) or (key and key not in {"test", "testing", "dummy"})
    if looks_real and not endpoint:
        pytest.exit(
            "Refusing to run: real AWS credentials are present and "
            "AWS_ENDPOINT_URL is not set.\n"
            "Tests must run against moto, the fake provider, or LocalStack.\n"
            "Unset AWS_PROFILE and AWS_ACCESS_KEY_ID, or set AWS_ENDPOINT_URL.",
            returncode=2,
        )
