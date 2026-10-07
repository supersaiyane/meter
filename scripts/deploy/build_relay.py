"""Zip the relay for its Lambda function. TASK-P9-001, ADR-0035.

The relay's runtime provides boto3 and nothing else, and `finops_relay` imports nothing else, a
contract in `pyproject.toml`, so the package alone is the whole deployment.

**Deterministic.** Every entry carries the same timestamp and the entries are in one order, so
the same code makes the same bytes. Terraform compares the zip's hash to decide whether to
replace the function, and a zip that changed with the clock would replace it on every apply.

    python scripts/deploy/build_relay.py --out build/relay.zip
"""

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "finops_relay"
#: The earliest time a zip entry can carry, and the same for every entry.
EPOCH = (1980, 1, 1, 0, 0, 0)


def sources(root: Path = ROOT) -> list[Path]:
    """Every Python file in the package, in one order, and nothing compiled."""
    return sorted(
        path for path in (root / PACKAGE).rglob("*.py") if "__pycache__" not in path.parts
    )


def build(out: Path, root: Path = ROOT) -> list[str]:
    """Write the zip and return the names in it."""
    out.parent.mkdir(parents=True, exist_ok=True)
    names: list[str] = []
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sources(root):
            name = path.relative_to(root).as_posix()
            entry = zipfile.ZipInfo(name, date_time=EPOCH)
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o644 << 16
            archive.writestr(entry, path.read_bytes())
            names.append(name)
    return names


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=ROOT / "build" / "relay.zip")
    args = parser.parse_args(argv)
    names = build(args.out)
    if not names:
        print(f"no {PACKAGE} sources found", file=sys.stderr)
        return 1
    print(f"OK: {args.out}, {len(names)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
