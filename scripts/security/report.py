#!/usr/bin/env python3
# Basic boiler Plate Doc | Grade A
# Why this file exists: Merges every scanner into one report, deduplicated across tools, and
# writes the posture file.
# Grade A here: nothing in this file is specific to this project. Copy it unchanged.
# Grades: A copy into a new project as is, no edits. B copy it and swap the
# names, paths or patterns named above. C leave behind, it is this project's
# own content rather than scaffolding, and is not tagged.
"""Merge every scanner's output into one HTML report, a summary, and a posture.

Reads whatever scanner output is present in a report directory, normalises it
into one finding shape, applies the allowlist, and writes:

  index.html     the human readable report, with the suggested fix per finding
  summary.json   the machine readable roll up, used by the pipeline gate
  POSTURE.md     the current posture, regenerated on every scan

Design notes worth keeping.

  * Two vulnerability scanners are merged, not chosen between. Their databases
    differ, and the difference is exactly where a missed finding lives. A
    finding seen by only one scanner is reported, and labelled with which.

  * A finding covered by a valid allowlist entry is shown, not hidden. It moves
    to a separate section carrying its owner and expiry. Hiding it would defeat
    the purpose of writing the entry down.

  * `unresolved_total` drives the exit code of the caller. It counts findings
    with no valid allowlist entry, at any severity. See ADR-0010 for why the
    threshold is zero rather than "no critical".
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import yaml

SEVERITY_ORDER = ["Critical", "High", "Medium", "Low", "Negligible", "Unknown"]
SEVERITY_RANK = {name: index for index, name in enumerate(SEVERITY_ORDER)}


# ------------------------------------------------------------------ parsing

def _norm_sev(value: str | None) -> str:
    if not value:
        return "Unknown"
    text = str(value).strip().capitalize()
    return text if text in SEVERITY_RANK else "Unknown"


def parse_grype(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text() or "{}")
    findings = []
    for match in data.get("matches", []):
        vuln = match.get("vulnerability", {})
        artifact = match.get("artifact", {})
        fix = vuln.get("fix", {}) or {}
        versions = fix.get("versions") or []
        findings.append(
            {
                "id": vuln.get("id", "UNKNOWN"),
                "severity": _norm_sev(vuln.get("severity")),
                "package": artifact.get("name", "unknown"),
                "installed": artifact.get("version", ""),
                "fixed_in": versions[0] if versions else "",
                "ecosystem": artifact.get("type", ""),
                "target": path.stem.replace("grype-", ""),
                "scanner": "grype",
                "description": (vuln.get("description") or "")[:400],
                "url": vuln.get("dataSource", ""),
            }
        )
    return findings


def parse_trivy(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text() or "{}")
    findings = []
    for result in data.get("Results", []) or []:
        for vuln in result.get("Vulnerabilities", []) or []:
            findings.append(
                {
                    "id": vuln.get("VulnerabilityID", "UNKNOWN"),
                    "severity": _norm_sev(vuln.get("Severity")),
                    "package": vuln.get("PkgName", "unknown"),
                    "installed": vuln.get("InstalledVersion", ""),
                    "fixed_in": vuln.get("FixedVersion", ""),
                    "ecosystem": result.get("Type", ""),
                    "target": path.stem.replace("trivy-", ""),
                    "scanner": "trivy",
                    "description": (vuln.get("Description") or "")[:400],
                    "url": vuln.get("PrimaryURL", ""),
                }
            )
    return findings


def parse_pip_audit(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text() or "{}")
    entries = data.get("dependencies", data if isinstance(data, list) else [])
    findings = []
    for dep in entries:
        for vuln in dep.get("vulns", []) or []:
            fixes = vuln.get("fix_versions") or []
            findings.append(
                {
                    "id": vuln.get("id", "UNKNOWN"),
                    "severity": "Unknown",
                    "package": dep.get("name", "unknown"),
                    "installed": dep.get("version", ""),
                    "fixed_in": fixes[0] if fixes else "",
                    "ecosystem": "python",
                    "target": "python-dependencies",
                    "scanner": "pip-audit",
                    "description": (vuln.get("description") or "")[:400],
                    "url": "",
                }
            )
    return findings


def parse_npm_audit(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text() or "{}")
    findings = []
    for name, item in (data.get("vulnerabilities") or {}).items():
        via = item.get("via") or []
        detail = next((v for v in via if isinstance(v, dict)), {})
        fix = item.get("fixAvailable")
        findings.append(
            {
                "id": str(detail.get("source", detail.get("url", "NPM-ADVISORY"))),
                "severity": _norm_sev(item.get("severity")),
                "package": name,
                "installed": item.get("range", ""),
                "fixed_in": fix.get("version", "") if isinstance(fix, dict) else "",
                "ecosystem": "npm",
                "target": "frontend-dependencies",
                "scanner": "npm-audit",
                "description": (detail.get("title") or "")[:400],
                "url": detail.get("url", ""),
            }
        )
    return findings


def parse_gitleaks(path: Path) -> list[dict[str, Any]]:
    raw = path.read_text().strip()
    if not raw:
        return []
    data = json.loads(raw)
    return [
        {
            "id": "SECRET",
            "severity": "Critical",
            "package": item.get("File", "unknown"),
            "installed": f"line {item.get('StartLine', '?')}",
            "fixed_in": "",
            "ecosystem": "repository",
            "target": "secrets",
            "scanner": "gitleaks",
            "description": f"{item.get('Description', 'Potential secret')} "
            f"(rule {item.get('RuleID', 'unknown')})",
            "url": "",
        }
        for item in (data if isinstance(data, list) else [])
    ]


PARSERS = (
    ("grype-", parse_grype),
    ("trivy-", parse_trivy),
    ("pip-audit", parse_pip_audit),
    ("npm-audit", parse_npm_audit),
    ("gitleaks", parse_gitleaks),
)


def collect(directory: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        for prefix, parser in PARSERS:
            if path.name.startswith(prefix):
                try:
                    findings.append(parser(path))
                except (json.JSONDecodeError, KeyError, TypeError) as exc:
                    # A scanner output we cannot parse is loud, never silent.
                    # A silently skipped file reports a clean scan for the
                    # wrong reason, which is worse than a failure.
                    print(f"WARN: could not parse {path.name}: {exc}", file=sys.stderr)
                break
    return [item for group in findings for item in group]


# ------------------------------------------------------------------ merging

def dedupe(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge the same finding seen by more than one scanner, keeping both names."""
    merged: dict[tuple[str, str, str], dict[str, Any]] = {}
    for finding in findings:
        key = (finding["id"], finding["package"], finding["target"])
        existing = merged.get(key)
        if existing is None:
            finding["scanners"] = [finding.pop("scanner")]
            merged[key] = finding
            continue
        existing["scanners"].append(finding.pop("scanner"))
        if SEVERITY_RANK[finding["severity"]] < SEVERITY_RANK[existing["severity"]]:
            existing["severity"] = finding["severity"]
        if not existing["fixed_in"] and finding["fixed_in"]:
            existing["fixed_in"] = finding["fixed_in"]
    return sorted(
        merged.values(),
        key=lambda f: (SEVERITY_RANK[f["severity"]], f["package"], f["id"]),
    )


def load_accepted(path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    """Unfixable findings accepted with a reachability argument. See ADR-0018.

    Distinct from the allowlist. The allowlist covers findings that HAVE a fix
    we are temporarily not taking, and every entry expires. This covers
    findings with no published fix, where no rebuild makes them go away, and
    each carries an argument that the vulnerable code path does not exist here.
    """
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text()) or {}
    return {(e.get("id"), e.get("package")): e for e in data.get("accepted") or []}


def load_allowlist(path: Path, today: date) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text()) or {}
    valid = {}
    for entry in data.get("exceptions") or []:
        expires = entry.get("expires")
        if isinstance(expires, date) and expires < today:
            continue  # Expired entries do not suppress. scan.sh already failed.
        valid[(entry.get("id"), entry.get("package"))] = entry
    return valid


def suggest_fix(finding: dict[str, Any]) -> str:
    """The exact remediation, as a command where one exists."""
    package, fixed = finding["package"], finding["fixed_in"]
    if finding["scanner_family"] == "secrets":
        return (
            "Remove the value, rotate the credential, and move it to Secrets "
            "Manager. Rewriting history alone is not sufficient, the credential "
            "must be treated as compromised."
        )
    if not fixed:
        return (
            "No fixed version published. Options, in order: replace the "
            "dependency, remove the code path that needs it, or add a time "
            "boxed allowlist entry with an owner in "
            "security/policy/allowlist.yaml."
        )
    if finding["ecosystem"] in ("python", "python-pkg"):
        return f'Pin `{package}>={fixed}` in pyproject.toml, then `make setup`.'
    if finding["ecosystem"] in ("npm", "node-pkg"):
        return f'`cd finops-web && npm install {package}@{fixed}`'
    return (
        f"Upgrade `{package}` to {fixed}. If it comes from the base image, "
        f"rebuild against the current Minimus tag, which is rebuilt daily."
    )


# ------------------------------------------------------------------ output

HTML_HEAD = """<!doctype html>
<meta charset="utf-8">
<title>Meter security report</title>
<style>
  :root { color-scheme: light dark; --bg:#fff; --fg:#111; --mut:#666;
          --line:#e3e3e3; --card:#fafafa; }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#111417; --fg:#e8e8e8; --mut:#9aa0a6; --line:#2a2f35; --card:#181c20; }
  }
  body { background:var(--bg); color:var(--fg); margin:0;
         font:15px/1.55 ui-sans-serif,system-ui,-apple-system,sans-serif; }
  .wrap { max-width:1180px; margin:0 auto; padding:2.5rem 1.25rem 5rem; }
  h1 { font-size:1.6rem; margin:0 0 .35rem; }
  .sub { color:var(--mut); margin:0 0 2rem; }
  .verdict { padding:1rem 1.25rem; border-radius:10px; font-weight:600;
             margin-bottom:2rem; }
  .pass { background:#0d5c2e; color:#fff; }
  .fail { background:#8c1c1c; color:#fff; }
  .cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(120px,1fr));
           gap:.75rem; margin-bottom:2.25rem; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:8px;
          padding:.85rem 1rem; }
  .card .n { font-size:1.5rem; font-weight:650; }
  .card .l { color:var(--mut); font-size:.78rem; text-transform:uppercase;
             letter-spacing:.05em; }
  h2 { font-size:1.05rem; margin:2.5rem 0 .75rem; }
  .scroll { overflow-x:auto; }
  table { border-collapse:collapse; width:100%; font-size:.88rem; }
  th,td { text-align:left; padding:.6rem .7rem; border-bottom:1px solid var(--line);
          vertical-align:top; }
  th { color:var(--mut); font-weight:600; font-size:.75rem; text-transform:uppercase;
       letter-spacing:.04em; white-space:nowrap; }
  .sev { font-weight:650; white-space:nowrap; }
  .Critical{color:#e5484d}.High{color:#e5734d}.Medium{color:#d9a520}
  .Low{color:#7a9}.Negligible,.Unknown{color:var(--mut)}
  code { background:var(--card); border:1px solid var(--line); border-radius:4px;
         padding:.1rem .35rem; font-size:.85em; }
  .fix { color:var(--mut); }
  .empty { color:var(--mut); font-style:italic; }
  footer { margin-top:4rem; color:var(--mut); font-size:.82rem;
           border-top:1px solid var(--line); padding-top:1rem; }
</style>
<div class="wrap">
"""


def render_html(
    findings: list[dict[str, Any]],
    allowed: list[dict[str, Any]],
    generated: str,
    label: str,
    unfixable: list[dict[str, Any]] | None = None,
) -> str:
    unfixable = unfixable or []
    counts = Counter(f["severity"] for f in findings)
    passing = not findings
    out = [HTML_HEAD]
    out.append(f"<h1>Meter security report</h1>")
    out.append(
        f'<p class="sub">{html.escape(label)} &middot; generated {html.escape(generated)}</p>'
    )
    out.append(
        f'<div class="verdict {"pass" if passing else "fail"}">'
        + (
            "PASS. Zero unresolved findings."
            if passing
            else f"FAIL. {len(findings)} unresolved finding(s). "
            "The policy is zero findings that have a published fix, see ADR-0018."
        )
        + "</div>"
    )

    out.append('<div class="cards">')
    for severity in SEVERITY_ORDER:
        out.append(
            f'<div class="card"><div class="n {severity}">{counts.get(severity, 0)}</div>'
            f'<div class="l">{severity}</div></div>'
        )
    out.append(
        f'<div class="card"><div class="n">{len(allowed)}</div>'
        f'<div class="l">Allowlisted</div></div>'
        f'<div class="card"><div class="n">{len(unfixable)}</div>'
        f'<div class="l">Unfixable, accepted</div></div></div>'
    )

    out.append("<h2>Unresolved findings and their fixes</h2>")
    if not findings:
        out.append('<p class="empty">None. Nothing to fix.</p>')
    else:
        out.append('<div class="scroll"><table><thead><tr>')
        for header in (
            "Severity", "Advisory", "Package", "Installed", "Fixed in",
            "Target", "Seen by", "Suggested fix",
        ):
            out.append(f"<th>{header}</th>")
        out.append("</tr></thead><tbody>")
        for f in findings:
            url = html.escape(f.get("url") or "")
            advisory = html.escape(f["id"])
            link = f'<a href="{url}">{advisory}</a>' if url else advisory
            out.append(
                "<tr>"
                f'<td class="sev {f["severity"]}">{f["severity"]}</td>'
                f"<td>{link}</td>"
                f'<td><code>{html.escape(f["package"])}</code></td>'
                f'<td>{html.escape(f["installed"])}</td>'
                f'<td>{html.escape(f["fixed_in"]) or "<em>none</em>"}</td>'
                f'<td>{html.escape(f["target"])}</td>'
                f'<td>{html.escape(", ".join(sorted(set(f["scanners"]))))}</td>'
                f'<td class="fix">{f["fix_html"]}</td>'
                "</tr>"
            )
        out.append("</tbody></table></div>")

    out.append("<h2>Accepted under a time boxed allowlist entry</h2>")
    if not allowed:
        out.append('<p class="empty">None.</p>')
    else:
        out.append('<div class="scroll"><table><thead><tr>')
        for header in ("Advisory", "Package", "Owner", "Expires", "Reason"):
            out.append(f"<th>{header}</th>")
        out.append("</tr></thead><tbody>")
        for f in allowed:
            entry = f["allowlist"]
            out.append(
                "<tr>"
                f'<td>{html.escape(f["id"])}</td>'
                f'<td><code>{html.escape(f["package"])}</code></td>'
                f'<td>{html.escape(str(entry.get("owner", "")))}</td>'
                f'<td>{html.escape(str(entry.get("expires", "")))}</td>'
                f'<td>{html.escape(str(entry.get("reason", "")))}</td>'
                "</tr>"
            )
        out.append("</tbody></table></div>")

    out.append("<h2>Accepted as unfixable, with a reachability argument</h2>")
    if not unfixable:
        out.append('<p class="empty">None.</p>')
    else:
        out.append('<div class="scroll"><table><thead><tr>')
        for header in ("Advisory", "Package", "Owner", "Review",
                       "Why it is not reachable"):
            out.append(f"<th>{header}</th>")
        out.append("</tr></thead><tbody>")
        for f in unfixable:
            e = f["accepted"]
            out.append(
                "<tr>"
                f'<td>{html.escape(f["id"])}</td>'
                f'<td><code>{html.escape(f["package"])}</code></td>'
                f'<td>{html.escape(str(e.get("owner", "")))}</td>'
                f'<td>{html.escape(str(e.get("review", "")))}</td>'
                f'<td>{html.escape(str(e.get("reachability", "")))}</td>'
                "</tr>"
            )
        out.append("</tbody></table></div>")

    out.append(
        "<footer>Policy is zero findings that have a published fix. An accepted "
        "finding with a fix carries a named owner and an expiry no more than 90 "
        "days out. A finding with no published fix carries a reachability "
        "argument instead, reviewed rather than expired. "
        "A posture is only as current as its last scan against the running "
        "digest, not the last build. See <code>docs/05-SECURITY.md</code> and "
        "<code>ADR-0010</code>.</footer></div>"
    )
    return "".join(out)


def render_posture(
    findings: list[dict[str, Any]], allowed: list[dict[str, Any]], generated: str,
    label: str, unfixable: list[dict[str, Any]] | None = None
) -> str:
    unfixable = unfixable or []
    counts = Counter(f["severity"] for f in findings)
    status = ("**ZERO FIXABLE FINDINGS**" if not findings
              else f"**{len(findings)} UNRESOLVED**")
    lines = [
        "# Security posture",
        "",
        "<!-- Basic boiler Plate Doc | Grade A",
        "     Why this file exists: The current security posture, regenerated on every",
        "     scan, so the number on the page is always measured rather than remembered.",
        "     Grade A here: nothing in this file is specific to this project. Copy it",
        "     unchanged.",
        "     Grades: A copy into a new project as is, no edits. B copy it and swap the",
        "     names, paths or patterns named above. C leave behind, it is this",
        "     project's own content rather than scaffolding, and is not tagged.",
        "-->",
        "",
        "Generated by `make security-scan`. Do not edit by hand.",
        "",
        f"Last scan: {generated}",
        f"Scanned: {label}",
        f"Status: {status}",
        "",
        "| Severity | Count |",
        "| --- | --- |",
    ]
    lines += [f"| {sev} | {counts.get(sev, 0)} |" for sev in SEVERITY_ORDER]
    lines += [
        f"| Allowlisted | {len(allowed)} |",
        f"| Unfixable, accepted under ADR-0018 | {len(unfixable)} |",
        "",
        "## Allowlist",
        "",
    ]
    if not allowed:
        lines.append("None active.")
    else:
        lines += ["| Advisory | Package | Owner | Expires |", "| --- | --- | --- | --- |"]
        lines += [
            f'| {f["id"]} | {f["package"]} | {f["allowlist"].get("owner", "")} '
            f'| {f["allowlist"].get("expires", "")} |'
            for f in allowed
        ]
    lines += ["", "Full report: `security/reports/latest/index.html`", ""]
    return "\n".join(lines)


# ------------------------------------------------------------------ main

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--allowlist", type=Path, required=True)
    parser.add_argument(
        "--accepted", type=Path,
        default=Path(__file__).resolve().parent.parent.parent
        / "security" / "policy" / "accepted.yaml")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--posture", type=Path)
    parser.add_argument("--label", default="working tree")
    parser.add_argument("--gate-only", action="store_true")
    args = parser.parse_args()

    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    raw = collect(args.input)
    for finding in raw:
        finding["scanner_family"] = (
            "secrets" if finding["scanner"] == "gitleaks" else "vuln"
        )
    findings = dedupe(raw)

    allowlist = load_allowlist(args.allowlist, date.today())
    accepted = load_accepted(args.accepted)

    # ADR-0018. The threshold is zero findings that have a published fix. A
    # finding with no fix is not a build failure, but it does need an
    # acceptance record carrying a reachability argument, or it fails too.
    unresolved, allowed, unfixable = [], [], []
    for finding in findings:
        entry = allowlist.get((finding["id"], finding["package"]))
        accept = accepted.get((finding["id"], finding["package"]))
        has_fix = bool(finding.get("fixed_in"))

        if entry:
            finding["allowlist"] = entry
            allowed.append(finding)
        elif not has_fix and accept:
            finding["accepted"] = accept
            unfixable.append(finding)
        else:
            finding["fix_html"] = html.escape(suggest_fix(finding)).replace("`", "")
            if not has_fix:
                finding["fix_html"] = (
                    "No published fix and no acceptance record. Add one to "
                    "security/policy/accepted.yaml with a reachability argument, "
                    "or change the version. See ADR-0018."
                )
            unresolved.append(finding)

    if args.gate_only:
        if unfixable:
            print(f"{len(unfixable)} unfixable finding(s) accepted under ADR-0018")
        if unresolved:
            print(f"FAIL: {len(unresolved)} finding(s) in {args.label}\n")
            for f in unresolved[:25]:
                fixed = f["fixed_in"] or "no fix published"
                print(f'  [{f["severity"]:<10}] {f["id"]:<20} {f["package"]} '
                      f'{f["installed"]} -> {fixed}')
            print("\nPolicy is zero findings that have a published fix, ADR-0018.")
            print("  With a fix:    take the fix, or add a time boxed allowlist")
            print("                 entry with an owner in policy/allowlist.yaml.")
            print("  Without a fix: change the version, or add an acceptance record")
            print("                 with a reachability argument in policy/accepted.yaml.")
            return 1
        print(f"PASS: {args.label} has zero fixable findings"
              + (f", {len(unfixable)} accepted as unfixable." if unfixable else "."))
        return 0

    if args.output:
        args.output.write_text(
            render_html(unresolved, allowed, generated, args.label, unfixable),
            encoding="utf-8"
        )
    if args.posture:
        args.posture.write_text(
            render_posture(unresolved, allowed, generated, args.label, unfixable),
            encoding="utf-8"
        )
    if args.summary:
        args.summary.write_text(
            json.dumps(
                {
                    "generated": generated,
                    "label": args.label,
                    "unresolved_total": len(unresolved),
                    "allowlisted_total": len(allowed),
                    "unfixable_accepted_total": len(unfixable),
                    "by_severity": dict(Counter(f["severity"] for f in unresolved)),
                    "findings": unresolved,
                },
                indent=2,
                default=str,
            )
        )
    print(f"{len(unresolved)} unresolved, {len(allowed)} allowlisted, "
          f"{len(unfixable)} accepted as unfixable")
    return 0


if __name__ == "__main__":
    sys.exit(main())
