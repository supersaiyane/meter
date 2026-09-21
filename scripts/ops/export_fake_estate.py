"""Write the fake utilization, container, topology and quota estates to files.

    python scripts/ops/export_fake_estate.py --out build/fake-estate

Every file is byte identical between runs at the same `--at`: rows are emitted
in a fixed order, numbers are fixed point text, and gzip is written with no
timestamp and no file name in its header. `manifest.json` carries a digest per
file, so "did the estate change" is a diff of one small file.

Null is an empty unquoted field, which is what `COPY ... WITH (FORMAT csv)`
reads as NULL. No value in these files is an empty string, so the two cannot be
confused. JSON columns are compact JSON text.

**The recommended seed path is still the collectors.** `make seed` writes cost
through the real collector against the fake, TASK-P1-012, so that the rows on
screen are the product's own output. These files are for inspection, for other
tools, and for seeding a database before a collector for that table exists.
Loading `container_usage` from here proves nothing about TASK-P6-006.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import math
from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict

from finops_providers.fake import containers, fixtures, planted, quotas, topology, utilization
from finops_providers.fake import estate_shape as shape

FORMAT_VERSION = 1

HOURLY_COLUMNS = (
    "sub_account_id",
    "resource_id",
    "dimension",
    "namespace",
    "metric_name",
    "statistic",
    "unit",
    "at",
    "value",
)
SUMMARY_COLUMNS = (
    "sub_account_id",
    "resource_id",
    "namespace",
    "metric_name",
    "statistic",
    "unit",
    "usage_date",
    "samples",
    "avg_value",
    "p95_value",
    "p99_value",
    "max_value",
    "min_value",
)


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return str(value)


class _Writer:
    """A CSV writer to a plain or gzip file with no timestamp in its header."""

    def __init__(self, path: Path, columns: Iterable[str]) -> None:
        self.path = path
        self.columns = tuple(columns)
        self.rows = 0
        raw = path.open("wb")
        self._raw = raw
        self._stream = (
            gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0)
            if path.suffix == ".gz"
            else raw
        )
        self._text = io.TextIOWrapper(self._stream, encoding="utf-8", newline="")
        self._csv = csv.writer(self._text, lineterminator="\n")
        self._csv.writerow(self.columns)

    def write(self, row: Mapping[str, object] | tuple[object, ...]) -> None:
        if isinstance(row, tuple):
            self._csv.writerow(row)
        else:
            self._csv.writerow([_text(row[c]) for c in self.columns])
        self.rows += 1

    def close(self) -> None:
        self._text.flush()
        self._text.detach()
        if self._stream is not self._raw:
            self._stream.close()
        self._raw.close()


def _write(path: Path, rows: Iterable[Mapping[str, object]]) -> _Writer:
    rows = iter(rows)
    first = next(rows)
    writer = _Writer(path, first.keys())
    writer.write(first)
    for row in rows:
        writer.write(row)
    writer.close()
    return writer


def _percentile(sorted_values: list[float], q: float) -> float:
    """Nearest rank, the same definition a reader can check by hand."""
    rank = max(1, math.ceil(q * len(sorted_values)))
    return sorted_values[rank - 1]


def _export_series(out: Path, at: datetime) -> tuple[_Writer, _Writer]:
    hourly = _Writer(out / "metric_point_hourly.csv.gz", HOURLY_COLUMNS)
    buckets: dict[tuple[object, ...], list[float]] = defaultdict(list)
    for stream in (utilization.series(at=at), containers.series(at=at)):
        for sp in stream:
            p = sp.point
            at_text = p.at.isoformat()
            hourly.write(
                (
                    p.account_key.account_id,
                    sp.resource_id,
                    sp.dimension,
                    p.namespace,
                    p.metric_name,
                    p.statistic,
                    p.unit,
                    at_text,
                    str(p.value),
                )
            )
            buckets[
                (
                    p.account_key.account_id,
                    sp.resource_id,
                    p.namespace,
                    p.metric_name,
                    p.statistic,
                    p.unit,
                    p.at.date().isoformat(),
                )
            ].append(float(p.value))
    hourly.close()
    summary = _Writer(out / "metric_daily_summary.csv.gz", SUMMARY_COLUMNS)
    for key in sorted(buckets):
        values = sorted(buckets[key])
        summary.write(
            (
                *key,
                len(values),
                f"{sum(values) / len(values):.4f}",
                f"{_percentile(values, 0.95):.4f}",
                f"{_percentile(values, 0.99):.4f}",
                f"{values[-1]:.4f}",
                f"{values[0]:.4f}",
            )
        )
    summary.close()
    return hourly, summary


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


#: What one exported file is recorded as: how many rows went in and the digest of
#: what came out. The digest is what makes two runs at the same `at` checkable
#: rather than merely believed to be identical.
FileRecord = Mapping[str, object]


class Manifest(TypedDict):
    """The export's own record of itself.

    Typed rather than a bare mapping because the only caller reads `files` and
    iterates it, and an `object` there needs a cast at exactly the place a reader
    most wants to know the shape. It also means adding a key to the literal below
    without declaring it here is a type error rather than a field nobody reads.
    """

    format_version: int
    tenant_id: str
    at: str
    window_start: str
    window_end: str
    hourly_as_of_rule: str
    collected_at: str
    files: Mapping[str, FileRecord]


def export(out: Path, at: datetime = fixtures.AS_OF) -> Manifest:
    out.mkdir(parents=True, exist_ok=True)
    writers: list[_Writer] = []
    writers.append(_write(out / "resource_inventory.csv", utilization.inventory_rows(at=at)))
    writers.extend(_export_series(out, at))
    writers.append(_write(out / "container_cluster.csv", containers.cluster_rows()))
    writers.append(_write(out / "container_usage_daily.csv.gz", containers.usage_rows(at=at)))
    writers.append(
        _write(out / "container_node_group_daily.csv.gz", containers.node_group_rows(at=at))
    )
    writers.append(_write(out / "topology_node.csv", topology.node_rows()))
    writers.append(_write(out / "topology_edge.csv", topology.edge_rows()))
    writers.append(_write(out / "graph_coverage.csv", topology.coverage_rows()))
    writers.append(_write(out / "quota_usage.csv", quotas.usage_rows(at=at)))
    writers.append(_write(out / "quota_usage_history.csv.gz", quotas.history_rows(at=at)))
    writers.append(_write(out / "quota_request.csv", quotas.request_rows(at=at)))
    writers.append(
        _write(out / "quota_request_status_history.csv", quotas.request_history_rows(at=at))
    )

    findings = out / "planted_findings.json"
    findings.write_text(
        json.dumps([p.__dict__ for p in planted.PLANTED], indent=2, default=list) + "\n",
        encoding="utf-8",
    )
    start, end = shape.window(at)
    manifest: Manifest = {
        "format_version": FORMAT_VERSION,
        "tenant_id": str(fixtures.TENANT_ID),
        "at": at.isoformat(),
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "hourly_as_of_rule": "as_of = at + 1 hour",
        "collected_at": fixtures.COLLECTED_AT.isoformat(),
        "files": {
            w.path.name: {"rows": w.rows, "columns": list(w.columns), "sha256": _digest(w.path)}
            for w in writers
        }
        | {findings.name: {"rows": len(planted.PLANTED), "sha256": _digest(findings)}},
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--at",
        type=datetime.fromisoformat,
        default=fixtures.AS_OF,
        help="the clock the estate is built at, ISO 8601 with offset",
    )
    args = parser.parse_args()
    manifest = export(args.out, args.at)
    for name, meta in manifest["files"].items():
        print(f"{meta['rows']:>10,}  {name}")


if __name__ == "__main__":
    main()
