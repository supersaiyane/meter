"""Every image carries every package its processes import. TASK-P12-004, ISS-274.

A Dockerfile copies Meter's packages one by one and then installs them, and a package it does
not copy is silently missing from the image: `pip install .` finds nothing to install and says
nothing. The worker image lacked `finops_relay` until 2026-10-12, which nothing noticed because
no process in it imported the relay until TASK-P12-002 composed the collectors. These import
every module of the packages an image runs, in a process of their own, and hold the image to
the first party packages that pulls in.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
COPIED = re.compile(r"^COPY (finops_[a-z_]+)/", re.MULTILINE)
#: Each image, and the packages whose processes it runs.
IMAGES = {
    "Dockerfile.worker": ("finops_ingest",),
    "Dockerfile.api": ("finops_api", "finops_mcp"),
}
IMPORT_ALL = """
import importlib, json, pkgutil, sys
for root in sys.argv[1:]:
    package = importlib.import_module(root)
    for found in pkgutil.walk_packages(package.__path__, root + "."):
        importlib.import_module(found.name)
print(json.dumps(sorted({m.split(".")[0] for m in sys.modules if m.startswith("finops_")})))
"""


def copied(dockerfile: str) -> set[str]:
    return set(COPIED.findall((ROOT / "docker" / dockerfile).read_text()))


def imported(packages: tuple[str, ...], cwd: Path) -> set[str]:
    result = subprocess.run(
        [sys.executable, "-c", IMPORT_ALL, *packages],
        cwd=cwd,
        env={"PATH": os.environ["PATH"], "PYTHONPATH": str(ROOT)},
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    found: list[str] = json.loads(result.stdout)
    return set(found)


@pytest.mark.parametrize(("dockerfile", "packages"), sorted(IMAGES.items()))
def test_an_image_copies_every_package_its_processes_import(
    dockerfile: str, packages: tuple[str, ...], tmp_path: Path
) -> None:
    missing = imported(packages, tmp_path) - copied(dockerfile)
    assert not missing, f"{dockerfile} does not copy {sorted(missing)}"


@pytest.mark.parametrize("dockerfile", sorted(IMAGES))
def test_no_runtime_image_copies_the_fakes(dockerfile: str) -> None:
    assert "finops_fakes" not in copied(dockerfile)
