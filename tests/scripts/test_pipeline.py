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

#: Images that ship without git, the same slim images that ship without make.
NO_GIT = NO_MAKE

#: A step that can reach git. Every make target and the test suite can, through
#: something they run: `build_file_graph.py` asks git which files the repository
#: holds, since 2026-10-05, `check_memory.py` resolves commits with it, and the
#: suite builds repositories with it. A list of the targets that need it today
#: would miss the next one, which is how `make check-memory` was missed.
GIT_CALL = re.compile(MAKE_CALL.pattern + r"|\bpytest\b|code_review\.py")


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


def test_every_job_that_can_reach_git_installs_it_first() -> None:
    """python:slim and alpine ship without git, and a job that reaches for it on
    either fails, or worse, quietly does less: the code review read an empty diff
    for as long as it ran without it."""
    pipeline = loaded()
    offenders = []
    for name, job in pipeline.items():
        if not isinstance(job, dict) or "script" not in job:
            continue
        script = [str(step) for step in job["script"]]
        first_use = next((i for i, step in enumerate(script) if GIT_CALL.search(step)), None)
        if first_use is None or str(job.get("image", "")) not in NO_GIT:
            continue
        setup = [str(step) for step in job.get("before_script", [])] + script[:first_use]
        if not any(re.search(r"(apt-get install|apk add).*\bgit\b", step) for step in setup):
            offenders.append(name)

    assert offenders == [], f"these can reach git on an image without it: {offenders}"


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


# --- the plan and the deploy, TASK-P12-007, ISS-260, ISS-281, ISS-282 -------------------------


def runnable() -> dict[str, dict[str, Any]]:
    return {
        name: job
        for name, job in loaded().items()
        if isinstance(job, dict) and "script" in job and not name.startswith(".")
    }


def expanded(job: dict[str, Any], text: str) -> str:
    """`text` with the job's own variables in place, as GitLab expands an artifact path."""
    for name, value in (job.get("variables") or {}).items():
        text = text.replace(f"${{{name}}}", str(value))
    return text


def published(job: dict[str, Any]) -> set[str]:
    return {expanded(job, path) for path in (job.get("artifacts") or {}).get("paths", [])}


def joined(steps: list[Any]) -> str:
    return "\n".join(str(step) for step in steps)


def test_no_job_needs_two_jobs_that_publish_the_same_file() -> None:
    """A job that needs two jobs publishing one file gets whichever arrived last, which is how
    deploy:dev received both environments' plans. A directory several jobs write their own files
    into, `security/sbom/`, is not a collision, and neither are two jobs that never meet."""
    jobs = runnable()
    for name, job in jobs.items():
        seen: dict[str, str] = {}
        for needed in job.get("needs") or []:
            needed = needed if isinstance(needed, str) else needed["job"]
            for path in (one for one in published(jobs[needed]) if not one.endswith("/")):
                assert path not in seen, f"{name} needs {needed} and {seen.get(path)}: {path}"
                seen[path] = needed


def test_every_job_a_job_needs_exists() -> None:
    jobs = runnable()
    for name, job in jobs.items():
        for needed in job.get("needs") or []:
            assert (needed if isinstance(needed, str) else needed["job"]) in jobs, (name, needed)


def test_a_deploy_applies_the_plan_its_own_environments_plan_job_published() -> None:
    jobs = runnable()
    deploys = sorted(name for name in jobs if name.startswith("deploy:"))
    assert deploys == ["deploy:dev", "deploy:prod"]
    for deploy in deploys:
        job = jobs[deploy]
        environment = job["variables"]["TF_ENV"]
        plan = f"infra/terraform/hub/tfplan-{environment}"
        assert f"apply -auto-approve tfplan-{environment}" in expanded(job, joined(job["script"]))
        makers = [name for name in job["needs"] if plan in published(jobs[name])]
        assert makers == [f"terraform-plan:{environment}"], (deploy, job["needs"])


def test_every_aws_job_assumes_its_role_from_the_token_file() -> None:
    """The role used to be assumed with `aws sts`, which no image these jobs run has."""
    aws = {name: job for name, job in runnable().items() if "id_tokens" in job}
    assert {"terraform-plan:dev", "terraform-plan:prod", "deploy:dev", "deploy:prod"} <= set(aws)
    for name, job in aws.items():
        before = joined(job["before_script"])
        assert "AWS_WEB_IDENTITY_TOKEN_FILE" in before and "AWS_ROLE_ARN" in before, name
        assert "aws sts" not in before, f"{name}: ISS-281"


def test_a_deploy_waits_through_terraform_not_a_cli_its_image_lacks() -> None:
    jobs = runnable()
    for deploy in ("deploy:dev", "deploy:prod"):
        assert "aws ecs wait" not in joined(jobs[deploy]["script"]), "ISS-282"
    ecs = (ROOT / "infra" / "terraform" / "hub" / "ecs.tf").read_text()
    for service in ("api", "web", "worker"):
        start = ecs.index(f'resource "aws_ecs_service" "{service}" {{')
        body = ecs[start : ecs.index("\n}\n", start)]
        assert re.search(r"wait_for_steady_state\s+=\s+true", body), service


def test_every_script_a_job_runs_exists() -> None:
    for name, job in runnable().items():
        for path in re.findall(r"(?:bash |\./)(scripts/\S+\.sh)", joined(job["script"])):
            assert (ROOT / path).is_file(), (name, path)
