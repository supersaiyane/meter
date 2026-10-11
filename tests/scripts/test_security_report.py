"""The scan report reads npm's fix as npm states it, so a fixable finding is never accepted.

Found 2026-10-11. npm says a fix exists in three ways: an object naming the version, `true` when
updating within the declared ranges reaches a fixed version, and `false` when nothing can. The
report read `true` as no fix, so source-map-js, fixable since 1.2.2, was recorded as unfixable
and an acceptance from before the fix absorbed it. ADR-0018's threshold is zero findings with a
published fix, and a fix that exists is one, whether or not npm names its version.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = ROOT / "scripts" / "security" / "report.py"
spec = importlib.util.spec_from_file_location("security_report", SCRIPT)
assert spec and spec.loader
report = importlib.util.module_from_spec(spec)
sys.modules["security_report"] = report
spec.loader.exec_module(report)

ADVISORY = "1241209"


def audit(fix: object) -> dict[str, Any]:
    """npm audit's JSON for one advisory in source-map-js, with the fix as given."""
    return {
        "vulnerabilities": {
            "source-map-js": {
                "severity": "high",
                "range": "1.0.0 - 1.2.1",
                "fixAvailable": fix,
                "via": [
                    {
                        "source": int(ADVISORY),
                        "title": "source-map-js allows event-loop denial of service",
                        "url": "https://github.com/advisories/GHSA-68fv-2mgg-jv7q",
                    }
                ],
            }
        }
    }


@pytest.mark.parametrize(
    ("fix", "fixed_in"),
    [
        ({"name": "vite", "version": "8.3.0", "isSemVerMajor": False}, "8.3.0"),
        (True, report.NPM_UPDATE),
        (False, ""),
        (None, ""),
    ],
)
def test_the_fix_is_read_as_npm_states_it(fix: object, fixed_in: str) -> None:
    assert report.npm_fix(fix) == fixed_in


def test_a_fix_npm_names_no_version_for_is_still_a_fix(tmp_path: Path) -> None:
    path = tmp_path / "npm-audit.json"
    path.write_text(json.dumps(audit(True)))
    (finding,) = report.parse_npm_audit(path)
    assert (finding["id"], finding["package"], finding["fixed_in"]) == (
        ADVISORY,
        "source-map-js",
        report.NPM_UPDATE,
    )


def test_the_remedy_for_such_a_fix_is_npm_update_never_an_invented_version() -> None:
    finding = {
        "package": "source-map-js",
        "fixed_in": report.NPM_UPDATE,
        "ecosystem": "npm",
        "scanner_family": "dependencies",
    }
    assert "npm update source-map-js" in report.suggest_fix(finding)
    assert "@" not in report.suggest_fix(finding)


def gate(
    tmp_path: Path, fix: object, accepted: list[dict[str, Any]]
) -> subprocess.CompletedProcess[str]:
    """The report run as the scan runs it, gate only, over one npm finding."""
    found = tmp_path / "found"
    found.mkdir()
    (found / "npm-audit.json").write_text(json.dumps(audit(fix)))
    allowlist = tmp_path / "allowlist.yaml"
    allowlist.write_text(yaml.safe_dump({"exceptions": []}))
    policy = tmp_path / "accepted.yaml"
    policy.write_text(yaml.safe_dump({"accepted": accepted}))
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--input",
            str(found),
            "--allowlist",
            str(allowlist),
            "--accepted",
            str(policy),
            "--gate-only",
        ],
        capture_output=True,
        text=True,
        check=False,
    )


STALE = [{"id": ADVISORY, "package": "source-map-js", "unfixable": True}]


def test_an_acceptance_cannot_absorb_a_finding_that_has_a_fix(tmp_path: Path) -> None:
    ran = gate(tmp_path, True, STALE)
    assert ran.returncode == 1, ran.stdout
    assert "FAIL: 1 finding(s)" in ran.stdout


def test_an_acceptance_still_covers_a_finding_with_no_fix(tmp_path: Path) -> None:
    ran = gate(tmp_path, False, STALE)
    assert ran.returncode == 0, ran.stdout
    assert "1 unfixable finding(s) accepted under ADR-0018" in ran.stdout
