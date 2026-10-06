"""The development only check is what keeps an npm acceptance true, so it is watched failing.

An acceptance in security/policy/accepted.yaml is only as good as the check behind it. This
one says a package never ships; if the check quietly stopped finding the package, its passing
line would read as a guarantee nobody is giving. So the package is planted deep in a fake
production tree, the acceptance is withdrawn, and npm is made to print nonsense, and each has
to fail.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = ROOT / "scripts" / "ci" / "check_dev_only.py"

spec = importlib.util.spec_from_file_location("check_dev_only", SCRIPT)
assert spec and spec.loader
check_dev_only = importlib.util.module_from_spec(spec)
sys.modules["check_dev_only"] = check_dev_only
spec.loader.exec_module(check_dev_only)

ADVISORY = "1241209"


def accepted(tmp_path: Path, ids: list[str]) -> Path:
    path = tmp_path / "accepted.yaml"
    entries = [{"id": advisory, "package": "source-map-js"} for advisory in ids]
    path.write_text(yaml.safe_dump({"accepted": entries}))
    return path


def tree(*nested: str) -> dict[str, Any]:
    """A production tree with the named packages each one level below the last."""
    node: dict[str, Any] = {}
    for name in reversed(nested):
        node = {"dependencies": {name: node}}
    return {"name": "finops-web", "version": "0.0.0", **node}


def test_a_package_deep_in_the_production_tree_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Two levels down, because a check that read only the direct dependencies would pass here.
    shipped = tree("react-aria-components", "postcss", "source-map-js")

    assert check_dev_only.main(lambda: shipped, accepted(tmp_path, [ADVISORY])) == 1
    assert "`source-map-js` is in the production dependency tree" in capsys.readouterr().out


def test_a_tree_without_it_passes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    clean = tree("react", "scheduler")

    assert check_dev_only.main(lambda: clean, accepted(tmp_path, [ADVISORY])) == 0
    assert capsys.readouterr().out.startswith("OK: none of the 1 packages")


def test_a_rule_whose_acceptance_was_withdrawn_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert check_dev_only.main(lambda: tree("react"), accepted(tmp_path, [])) == 1
    assert f"advisory {ADVISORY}, which is no" in capsys.readouterr().out


@pytest.mark.parametrize("failure", [RuntimeError("npm ls printed no tree"), OSError("no npm")])
def test_a_tree_that_cannot_be_read_fails_rather_than_passing(
    tmp_path: Path, failure: Exception, capsys: pytest.CaptureFixture[str]
) -> None:
    def unreadable() -> dict[str, Any]:
        raise failure

    assert check_dev_only.main(unreadable, accepted(tmp_path, [ADVISORY])) == 2
    assert capsys.readouterr().out.startswith("FAIL: could not read")


@pytest.mark.parametrize(
    ("printed", "readable"),
    [('{"name": "finops-web", "dependencies": {}}', True), ("npm error", False), ("[]", False)],
)
def test_the_tree_is_read_from_what_npm_prints(
    monkeypatch: pytest.MonkeyPatch, printed: str, readable: bool
) -> None:
    # npm ls exits 1 for a problem in a tree it still prints, so the exit code is ignored here.
    def npm(*args: Any, **_: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args, 1, stdout=printed, stderr="npm error")

    monkeypatch.setattr(check_dev_only.subprocess, "run", npm)
    if readable:
        assert check_dev_only.production_tree()["name"] == "finops-web"
    else:
        with pytest.raises(RuntimeError):
            check_dev_only.production_tree()


def test_every_rule_has_its_acceptance_in_the_committed_policy() -> None:
    committed = check_dev_only.accepted_ids(check_dev_only.ACCEPTED)

    assert set(check_dev_only.DEVELOPMENT_ONLY.values()) <= committed
