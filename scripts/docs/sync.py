#!/usr/bin/env python3
# Basic boiler Plate Doc | Grade B
# Why this file exists: Regenerates every derived document from the registry, so the same fact
# is never written twice and cannot drift.
# Grade B here: copy it, then replace the document list and the block names.
# Grades: A copy into a new project as is, no edits. B copy it and swap the
# names, paths or patterns named above. C leave behind, it is this project's
# own content rather than scaffolding, and is not tagged.
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

# Most blocks come from the registry. The task status block comes from the plan
# files, so the warning names its own source rather than asserting a wrong one.
WARNING_TEMPLATE = (
    "<!-- This block is GENERATED from {source} by scripts/docs/sync.py. "
    "Edit {source}, then run make doc-sync. Hand edits here are overwritten "
    "and make check-docs will fail. See ADR-0014. -->"
)
SOURCES = {"task-status": "docs/plans/"}
DEFAULT_SOURCE = "docs/registry.yaml"


def load() -> dict:
    return yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))


def replace_block(text: str, name: str, body: str) -> str:
    start, end = f"<!-- generated:{name} start -->", f"<!-- generated:{name} end -->"
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.DOTALL)
    warning = WARNING_TEMPLATE.format(source=SOURCES.get(name, DEFAULT_SOURCE))
    block = f"{start}\n{warning}\n\n{body.rstrip()}\n\n{end}"
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


def render_issue_register(reg: dict) -> str:
    """The full issue register. Generated so identifiers cannot diverge.

    tasks/ISSUES.md used to hold this by hand, and inside one session it had
    drifted from the registry by 22 records. See AUDIT-001, finding A001-F01.
    """
    rank = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    counts = Counter(i["status"] for i in reg["issues"])
    lines = [
        f"{len(reg['issues'])} issues. "
        f"{counts.get('FIXED', 0)} fixed, {counts.get('OPEN', 0)} open, "
        f"{counts.get('PARKED', 0)} parked.",
        "",
        "FIXED means the design decision is recorded, not that code exists. "
        "Implementation status lives only in `tasks/STATUS.md`.",
        "",
        "| ID | Severity | Issue | Status | Detail |",
        "| --- | --- | --- | --- | --- |",
    ]
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


def render_subprojects(reg: dict) -> str:
    """The sub project table, previously hand written alongside a generated one.

    Two tables describing the same thing is the drift ADR-0014 exists to
    prevent. AUDIT-001, finding A001-F10.
    """
    counts: dict[str, Counter] = {s["id"]: Counter() for s in reg["subprojects"]}
    for f in reg["features"]:
        counts[f["subproject"]][f["status"]] += 1
    lines = [
        "| ID | Name | Status | Features | Spec | Plan | Depends on |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for sp in sorted(reg["subprojects"], key=lambda x: x["id"]):
        c = counts[sp["id"]]

        # This table lives in docs/01-ROADMAP.md, so a path recorded from the
        # repository root needs its leading "docs/" removed to resolve.
        def rel(path: str) -> str:
            return path[5:] if path.startswith("docs/") else path

        spec = f"[spec]({rel(sp['spec'])})" if sp.get("spec") else "not written"
        plan = f"[plan]({rel(sp['plan'])})" if sp.get("plan") else "not written"
        lines.append(
            f"| {sp['id']} | {sp['name']} | {sp['status']} | "
            f"{sum(c.values())} ({c.get('Specified', 0)} specified) | "
            f"{spec} | {plan} | {sp.get('depends_on', '')} |"
        )
    return "\n".join(lines)


def render_task_status(reg: dict) -> str:
    """Task state, read from the plan files rather than copied into STATUS.md.

    STATUS.md used to hand-maintain a second copy of the plan's task list. That
    is the drift ADR-0014 exists to prevent, and it had already drifted: the
    list still showed 31 tasks and TASK-P0-029 as not started after it was
    done. The plan is the source, this is a view of it.
    """
    import re

    lines = [
        "| Sub project | Done | Partly | Not started | Total | Plan |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    detail: list[str] = []

    for sub in ("P0", "P2"):
        path = ROOT / "docs" / "plans" / f"{sub}-implementation-plan.md"
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        blocks = re.split(rf"\n### (TASK-{sub}-\d{{3}}): ", text)
        done = partly = notstarted = 0
        rows = []
        for i in range(1, len(blocks), 2):
            tid, body = blocks[i], blocks[i + 1]
            title = body.split("\n", 1)[0].strip()
            match = re.search(r"\| Status \| (.+?) \|", body)
            status = match.group(1).strip() if match else "?"
            if "Done" in status:
                done += 1
                rows.append((tid, title, status))
            elif "Partly" in status:
                partly += 1
                rows.append((tid, title, status))
            else:
                notstarted += 1
        total = done + partly + notstarted
        lines.append(
            f"| {sub} | {done} | {partly} | {notstarted} | {total} | "
            f"[plan](../docs/plans/{sub}-implementation-plan.md) |"
        )
        if rows:
            detail.append(f"\n**{sub}, not in the default state**\n")
            detail.append("| Task | Status | Title |")
            detail.append("| --- | --- | --- |")
            for tid, title, status in rows:
                detail.append(f"| `{tid}` | {status} | {title} |")

    if not detail:
        detail = ["", "No task has started."]
    return "\n".join(lines + detail)


def render_status_summary(reg: dict) -> str:
    fc = Counter(f["status"] for f in reg["features"])
    ic = Counter(i["status"] for i in reg["issues"])
    oc = Counter(o["status"].split()[0] for o in reg["open_questions"])
    return "\n".join(
        [
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
            "Generated from `docs/registry.yaml`. Change a status there, then run `make doc-sync`.",
        ]
    )


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
    ("docs/01-ROADMAP.md", "subprojects", render_subprojects),
    ("tasks/STATUS.md", "status-summary", render_status_summary),
    ("tasks/STATUS.md", "task-status", render_task_status),
    ("tasks/ISSUES.md", "issue-register", render_issue_register),
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
    print(
        (
            "OK: generated documents match the registry, "
            if args.check
            else "Regenerated from the registry: "
        )
        + counts
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
