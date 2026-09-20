"""Fail a pipeline on a dashboard that would cost too much. TASK-P2-018.

Usable in any pipeline, including one that has never heard of Meter: it reads
dashboard JSON from paths on the command line and needs no database, no
credentials and no network.

It exits non zero on a violation. ISS-096 is the argument for that: this gate's
reach already depends on how many dashboards a team keeps as code, and a gate
that warns is ignored regardless of reach.

    python scripts/ci/check_dashboards.py dashboards/*.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from finops_query.cost_model import Rates
from finops_query.gate import DEFAULT_RULE, Rule, Violation, check

#: The model's published assumptions, as constants rather than settings, so the
#: gate runs in a pipeline with no Meter configuration at all. A deployment that
#: has tightened its thresholds passes them with the flags below.
DEFAULT_RATES = Rates(
    logs_scan_price_per_gb=0.005,
    metrics_price_per_1000=0.01,
    manual_loads_per_day=4.0,
    viewing_hours_per_day=8.0,
    metrics_per_call=10.0,
    default_ingest_gb_per_day=10.0,
    assumed_query_seconds=3.0,
    refresh_warn_seconds=60,
    refresh_crit_seconds=15,
    timerange_warn_hours=168.0,
    timerange_crit_hours=720.0,
    quota_logs_concurrent=30,
    quota_getmetricdata_tps=50,
)


def load(path: Path) -> dict[str, Any] | None:
    """One dashboard, or None if this file is not one.

    A file this cannot read is not a violation. The gate blocks what it can
    prove is wrong, and failing on an unparseable file would make every
    unrelated JSON in a repository a pipeline failure.
    """
    try:
        found = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(found, dict) or "panels" not in found:
        return None
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument(
        "--max-refresh-seconds",
        type=int,
        default=DEFAULT_RULE.max_refresh_seconds,
        help="a refresh at or below this, combined with a wide window, is refused",
    )
    parser.add_argument(
        "--max-window-hours",
        type=float,
        default=DEFAULT_RULE.max_window_hours,
        help="a window wider than this, combined with a fast refresh, is refused",
    )
    parser.add_argument(
        "--ingest-gb-per-day",
        type=float,
        default=DEFAULT_RATES.default_ingest_gb_per_day,
        help="assumed log volume, which is what the modelled cost rests on",
    )
    args = parser.parse_args(argv)

    rule = Rule(
        max_refresh_seconds=args.max_refresh_seconds,
        max_window_hours=args.max_window_hours,
    )
    # GB per hour, because the model multiplies it by a window measured in
    # hours. The setting a person writes is per day, and this division is the
    # unit conversion that a previous bug got wrong by a factor of 24.
    per_hour = float(args.ingest_gb_per_day) / 24.0

    def ingest(_log_group: str, _region: str) -> float:
        return per_hour

    violations: list[Violation] = []
    read = 0
    for path in args.paths:
        dashboard = load(path)
        if dashboard is None:
            continue
        read += 1
        violations.extend(check(dashboard, rates=DEFAULT_RATES, ingest_rate=ingest, rule=rule))

    if not read:
        # Nothing examined is not a pass. A glob that matched no dashboard is
        # the most common way a gate ends up protecting nothing.
        print("No dashboard JSON was found in the given paths.", file=sys.stderr)
        return 2

    for violation in violations:
        print(f"REFUSED {violation}", file=sys.stderr)

    if violations:
        total = sum(violation.monthly_cost for violation in violations)
        print(
            f"\n{len(violations)} panel(s) refused across {read} dashboard(s), "
            f"modelled at ${total:,.2f} a month.",
            file=sys.stderr,
        )
        return 1

    print(f"OK: {read} dashboard(s) checked, none refused.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
