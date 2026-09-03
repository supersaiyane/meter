"""The prototype copy reaches no image, and that is enforced rather than assumed.

`finops_query/_legacy/sample_lambda.py` imports `urllib.request`, which
CVE-2026-15806's acceptance in `security/policy/accepted.yaml` depends on nobody
importing. The file is a baseline pinned by hash, so it cannot be edited, and
`check_forbidden_imports.py` therefore skips it.

That skip is defensible on two facts and this file checks the second one. The
first is that the advisory concerns `HTTPPasswordMgr` and urllib basic auth,
which the prototype never touches: it builds a `Request` with a bearer header.
The second is that the directory is copied into no image, so nothing it imports
is present at runtime.

Without this test, "it does not ship" is a sentence in a comment, and the first
person to add a COPY line would make a security acceptance quietly false.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOCKERFILES = sorted((ROOT / "docker").glob("Dockerfile.*"))


def test_there_are_dockerfiles_to_check() -> None:
    """Without this, the parametrised test below passes over an empty list."""
    assert len(DOCKERFILES) >= 3


@pytest.mark.parametrize("dockerfile", DOCKERFILES, ids=lambda p: p.name)
def test_no_image_copies_the_prototype(dockerfile: Path) -> None:
    content = dockerfile.read_text(encoding="utf-8")
    offending = [
        line.strip()
        for line in content.splitlines()
        if line.strip().startswith("COPY") and "finops_query" in line
    ]

    assert offending == [], (
        f"{dockerfile.name} copies finops_query into an image. The _legacy copy "
        "imports urllib.request, and CVE-2026-15806 is accepted on the argument "
        "that it is not present at runtime. Shipping it makes that argument false."
    )


def test_the_prototype_never_uses_urllib_basic_auth() -> None:
    """The other half of the acceptance argument.

    The advisory is about HTTPPasswordMgr and its subclasses. The prototype
    builds a Request with a bearer header instead, so the vulnerable code path
    is not reached even though the module is imported.
    """
    source = (ROOT / "finops_query" / "_legacy" / "sample_lambda.py").read_text(encoding="utf-8")

    for construct in ("HTTPPasswordMgr", "HTTPBasicAuthHandler", "HTTPDigestAuthHandler"):
        assert construct not in source, f"the prototype now uses {construct}, so the acceptance"
