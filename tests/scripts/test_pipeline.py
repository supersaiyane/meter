"""The pipeline is read the way the documentation is: by a test.

Two things here are the same class of defect, and both happened.

A duplicate job name is silently resolved by YAML in favour of the last one, so
adding a job that already exists deletes the earlier one and every check it ran,
with no error anywhere. That is how a job disappears from a pipeline nobody
reads end to end.

A job that calls `make` on an image without `make` fails before it runs a single
check. `python:slim` is Debian with no build tools, and four jobs called make on
it. The failure is loud when the pipeline runs, and invisible until then.

Neither is caught by a YAML linter, because both files are valid YAML.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
PIPELINE = ROOT / ".gitlab-ci.yml"

#: Images that ship without make. Not a guess: `docker run python:3.13-slim
#: which make` finds nothing.
NO_MAKE = ("python:3.13-slim", "python:3.12-slim", "alpine:3.20")

#: A make invocation, meaning make in command position. Anchored, because the
#: unanchored version matched the word inside `apk add --no-cache grep make
#: bash` and decided the install step was itself the thing needing an install.
MAKE_CALL = re.compile(r"(?:^|&&|;|\|)\s*make\s+[a-z]")


def raw() -> str:
    return PIPELINE.read_text(encoding="utf-8")


def loaded() -> dict[str, Any]:
    parsed = yaml.safe_load(raw())
    assert isinstance(parsed, dict), "the pipeline did not parse to a mapping"
    return parsed


def test_no_two_jobs_share_a_name() -> None:
    """Counted in the text, because the parser is what hides the problem."""
    names = re.findall(r"^([a-zA-Z][\w:.-]*):\s*$", raw(), re.M)
    repeated = sorted(name for name, count in Counter(names).items() if count > 1)

    assert len(names) > 10, "expected to find the jobs, not an empty file"
    assert repeated == [], f"these names each define more than one job: {repeated}"


def test_every_job_that_calls_make_installs_it_first() -> None:
    """A job calling make on an image without it fails before any check runs."""
    pipeline = loaded()
    offenders = []
    for name, job in pipeline.items():
        if not isinstance(job, dict) or "script" not in job:
            continue
        script = [str(step) for step in job["script"]]
        first_use = next((i for i, step in enumerate(script) if MAKE_CALL.search(step)), None)
        if first_use is None or str(job.get("image", "")) not in NO_MAKE:
            continue
        # Everything that runs before the first make call is setup, whether it
        # sits in before_script or at the top of script. Either is fine.
        setup = [str(step) for step in job.get("before_script", [])] + script[:first_use]
        if not any(re.search(r"(apt-get install|apk add).*\bmake\b", step) for step in setup):
            offenders.append(name)

    assert offenders == [], f"these call make on an image without it: {offenders}"


def test_the_documentation_gate_runs_the_whole_target() -> None:
    """It used to run three of the checks in `make check-docs`, and the other
    five ran only on the machine of whoever remembered.

    The number of checks in the target is deliberately not written down here. It
    was, as eight, until a ninth was added on 2026-09-28.
    """
    pipeline = loaded()
    steps = " ".join(str(s) for s in pipeline["docs-consistency"]["script"])

    assert "make check-docs" in steps


def test_the_review_covers_the_branch_everything_deploys_from() -> None:
    """Merge request only would leave the default branch the one branch nothing
    reviews."""
    rules = yaml.safe_dump(loaded()["code-review"]["rules"])

    assert "CI_DEFAULT_BRANCH" in rules
