#!/usr/bin/env python3
"""Regenerate every derived document from docs/registry.yaml. See ADR-0014.

One fact, one place. Feature status used to live in four documents by hand,
which guarantees drift. Now it lives in the registry, and everything derived
from it is generated between markers.

Generated blocks are delimited so hand written prose around them survives:

    <!-- generated:features start -->
    ...regenerated...
    <!-- generated:features end -->

Usage:
  scripts/docs/sync.py            regenerate in place
  scripts/docs/sync.py --check    fail if anything would change, writes nothing
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
REGISTRY = ROOT / "docs" / "registry.yaml"

WARNING = (
    "<!-- This block is GENERATED from docs/registry.yaml by scripts/docs/sync.py. "
    "Edit the registry, then run make doc-sync. Hand edits here are overwritten "
    "and make check-docs will fail. See ADR-0014. -->"
)


def load() -> dict:
    return yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))


def replace_block(text: str, name: str, body: str) -> str:
    start, end = f"<!-- generated:{name} start -->", f"<!-- generated:{name} end -->"
    pattern = re.compile(
        re.escape(start) + r".*?" + re.escape(end), re.DOTALL
    )
    block = f"{start}\n{WARNING}\n\n{body.rstrip()}\n\n{end}"
    if not pattern.search(text):
        raise SystemExit(
            f"FAIL: marker '{name}' not found. Add these two lines where the "
            f"generated block belongs:\n  {start}\n  {end}"
        )
    return pattern.sub(lambda _: block, text)


# ---------------------------------------------------------------- renderers

def render_features(reg: dict) -> str:
    subs = {s["id"]: s["name"] for s in reg["subprojects"]}
    counts = Counter(f["status"] for f in reg["features"])
    lines = [
        f"{len(reg['features'])} features across {len(subs)} sub projects. "
        f"{counts.get('Specified', 0)} specified, {counts.get('Planned', 0)} planned, "
        f"{counts.get('In build', 0)} in build, {counts.get('Delivered', 0)} delivered.",
        "",
        "**Every feature has its own document.** The identifier links to it.",
        "",
    ]
    order = [s["id"] for s in reg["subprojects"]]
    for sub in sorted(order, key=lambda s: (s != "P0", s != "P2", s)):
        rows = [f for f in reg["features"] if f["subproject"] == sub]
        if not rows:
            continue
        lines += [
            f"### {sub} {subs[sub]}",
            "",
            "| ID | Feature | Status | Detail |",
            "| --- | --- | --- | --- |",
        ]
        lines += [
            f"| [{f['id']}]({f['doc']}) | {f['name']} | {f['status']} | {f['detail']} |"
            for f in rows
        ]
        lines.append("")
    return "\n".join(lines)


def render_adrs(reg: dict) -> str:
    lines = ["| ID | Decision | Status | Detail |", "| --- | --- | --- | --- |"]
    lines += [
        f"| {a['id']} | {a['decision']} | {a['status']} | [{a['id']}]({a['doc']}) |"
        for a in reg["adrs"]
    ]
    lines += ["", "Index of records: [docs/adr/README.md](docs/adr/README.md)"]
    return "\n".join(lines)


def render_changes(reg: dict) -> str:
    lines = [
        "| ID | Date | Type | What changed | Commit | Detail |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    lines += [
        f"| {c['id']} | {c['date']} | {c['type']} | {c['what']} | `{c['commit']}` | {c['detail']} |"
        for c in reg["changes"]
    ]
    return "\n".join(lines)


def render_issues(reg: dict) -> str:
    counts = Counter(i["status"] for i in reg["issues"])
    lines = [
        f"**{counts.get('FIXED', 0)} FIXED, {counts.get('OPEN', 0)} OPEN, "
        f"{counts.get('PARKED', 0)} PARKED.** Full detail with evidence in "
        "[tasks/ISSUES.md](tasks/ISSUES.md).",
        "",
        "FIXED means the design decision is recorded, not that code exists. "
        "Implementation status lives only in [tasks/STATUS.md](tasks/STATUS.md).",
        "",
        "| ID | Severity | Issue | Status | Detail |",
        "| --- | --- | --- | --- | --- |",
    ]
    rank = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    for i in sorted(reg["issues"], key=lambda x: (rank.get(x["severity"], 9), x["id"])):
        lines.append(
            f"| {i['id']} | {i['severity']} | {i['summary']} | {i['status']} | {i['detail']} |"
        )
    return "\n".join(lines)


def render_open(reg: dict) -> str:
    lines = [
        "| ID | Question | Status | Blocks | Detail |",
        "| --- | --- | --- | --- | --- |",
    ]
    lines += [
        f"| {o['id']} | {o['question']} | {o['status']} | {o['blocks']} | {o['detail']} |"
        for o in reg["open_questions"]
    ]
    return "\n".join(lines)


def render_roadmap_status(reg: dict) -> str:
    subs = {s["id"]: s["name"] for s in reg["subprojects"]}
    counts: dict[str, Counter] = {s: Counter() for s in subs}
    for f in reg["features"]:
        counts[f["subproject"]][f["status"]] += 1
    lines = [
        "| ID | Name | Features | Specified | Planned |",
        "| --- | --- | --- | --- | --- |",
    ]
    for sub in sorted(subs):
        c = counts[sub]
        lines.append(
            f"| {sub} | {subs[sub]} | {sum(c.values())} | "
            f"{c.get('Specified', 0)} | {c.get('Planned', 0)} |"
        )
    return "\n".join(lines)


def render_status_summary(reg: dict) -> str:
    fc = Counter(f["status"] for f in reg["features"])
    ic = Counter(i["status"] for i in reg["issues"])
    oc = Counter(o["status"].split()[0] for o in reg["open_questions"])
    return "\n".join([
        "| Register | Counts |",
        "| --- | --- |",
        f"| Features | {sum(fc.values())} total, {fc.get('Specified', 0)} specified, "
        f"{fc.get('In build', 0)} in build, {fc.get('Delivered', 0)} delivered |",
        f"| Decisions | {len(reg['adrs'])} architecture decision records |",
        f"| Changes | {len(reg['changes'])} recorded |",
        f"| Issues | {ic.get('FIXED', 0)} fixed, {ic.get('OPEN', 0)} open, "
        f"{ic.get('PARKED', 0)} parked |",
        f"| Open questions | {sum(oc.values())} awaiting a decision |",
        "",
        "Generated from `docs/registry.yaml`. Change a status there, then run "
        "`make doc-sync`.",
    ])


def sync_feature_headers(reg: dict, check: bool) -> list[str]:
    """Regenerate the field table at the top of each feature document."""
    changed = []
    for feature in reg["features"]:
        path = ROOT / feature["doc"]
        if not path.exists():
            changed.append(f"{feature['id']}: {feature['doc']} is missing")
            continue
        text = path.read_text(encoding="utf-8")
        new = re.sub(
            r"^\| Status \| .*? \|$",
            f"| Status | {feature['status']} |",
            text,
            count=1,
            flags=re.MULTILINE,
        )
        new = re.sub(
            r"^\| Sub project \| .*? \|$",
            f"| Sub project | {feature['subproject']} |",
            new,
            count=1,
            flags=re.MULTILINE,
        )
        if new != text:
            changed.append(f"{feature['id']}: header out of step with the registry")
            if not check:
                path.write_text(new, encoding="utf-8")
    return changed


TARGETS = [
    ("INDEX.md", "features", render_features),
    ("INDEX.md", "adrs", render_adrs),
    ("INDEX.md", "changes", render_changes),
    ("INDEX.md", "issues", render_issues),
    ("INDEX.md", "open-questions", render_open),
    ("docs/01-ROADMAP.md", "roadmap-status", render_roadmap_status),
    ("tasks/STATUS.md", "status-summary", render_status_summary),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    reg = load()
    drift: list[str] = []

    by_file: dict[str, str] = {}
    for rel, name, renderer in TARGETS:
        text = by_file.get(rel) or (ROOT / rel).read_text(encoding="utf-8")
        by_file[rel] = replace_block(text, name, renderer(reg))

    for rel, new in by_file.items():
        path = ROOT / rel
        if path.read_text(encoding="utf-8") != new:
            drift.append(f"{rel}: generated block differs from the registry")
            if not args.check:
                path.write_text(new, encoding="utf-8")

    drift += sync_feature_headers(reg, args.check)

    if args.check and drift:
        print(f"FAIL: {len(drift)} generated document(s) out of step\n")
        for item in drift:
            print(f"  {item}")
        print("\nRun 'make doc-sync'. Do not hand edit a generated block, see ADR-0014.")
        return 1

    counts = (
        f"{len(reg['features'])} features, {len(reg['adrs'])} decisions, "
        f"{len(reg['changes'])} changes, {len(reg['issues'])} issues, "
        f"{len(reg['open_questions'])} open questions"
    )
    print(("OK: generated documents match the registry, " if args.check
           else "Regenerated from the registry: ") + counts)
    return 0


if __name__ == "__main__":
    sys.exit(main())
