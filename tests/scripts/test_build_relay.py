"""The relay's zip: the package alone, the same bytes for the same code, and enough to run.

TASK-P9-001, ADR-0035. Terraform replaces the function when the zip's hash changes, so a zip
that changed with the clock would redeploy it on every apply; and the runtime has boto3 and
nothing else, so a zip that needed anything more would fail on its first invocation. The import
contract in `pyproject.toml` says the package needs nothing more; this proves it, by importing the
handler from the zip with the repository out of reach.
"""

from __future__ import annotations

import hashlib
import importlib.util
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "deploy" / "build_relay.py"

_spec = importlib.util.spec_from_file_location("build_relay", SCRIPT)
assert _spec is not None and _spec.loader is not None
build_relay = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_relay)


def test_the_zip_holds_the_relay_and_nothing_else(tmp_path: Path) -> None:
    out = tmp_path / "relay.zip"
    names = build_relay.build(out)
    assert "finops_relay/relay.py" in names
    assert all(name.startswith("finops_relay/") and name.endswith(".py") for name in names)
    with zipfile.ZipFile(out) as archive:
        assert sorted(archive.namelist()) == sorted(names)


def test_the_same_code_makes_the_same_bytes(tmp_path: Path) -> None:
    first, second = tmp_path / "a.zip", tmp_path / "b.zip"
    build_relay.build(first)
    build_relay.build(second)
    assert (
        hashlib.sha256(first.read_bytes()).digest() == hashlib.sha256(second.read_bytes()).digest()
    )


def test_the_handler_imports_from_the_zip_alone(tmp_path: Path) -> None:
    out = tmp_path / "relay.zip"
    build_relay.build(out)
    probe = (
        "import sys; sys.path.insert(0, sys.argv[1]); "
        "import finops_relay.relay as relay; "
        "assert relay.__file__.startswith(sys.argv[1]), relay.__file__; "
        "assert not any(m.startswith(('finops_core', 'finops_providers', 'pydantic')) "
        "for m in sys.modules); "
        "print(callable(relay.handler))"
    )
    # Isolated: the repository is not on the path, so the only finops_relay it can find is the
    # one in the zip, and anything else the package needed would fail to import.
    found = subprocess.run(
        [sys.executable, "-I", "-c", probe, str(out)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert found.returncode == 0, found.stderr
    assert found.stdout.strip() == "True"


def test_main_writes_the_zip_and_says_where(tmp_path: Path) -> None:
    out = tmp_path / "relay.zip"
    assert build_relay.main(["--out", str(out)]) == 0
    assert out.exists()
