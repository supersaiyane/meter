#!/usr/bin/env python3
# Basic boiler Plate Doc | Grade B
# Why this file exists: Builds the file dependency graph and fails on a layering violation, so
# the architecture is checked rather than merely described.
# Grade B here: copy it, then replace the layer definitions.
# Grades: A copy into a new project as is, no edits. B copy it and swap the
# names, paths or patterns named above. C leave behind, it is this project's
# own content rather than scaffolding, and is not tagged.
"""Build the file dependency graph: which file depends on which other file.

Covers four edge kinds, because a graph of Python imports alone would miss most
of how this repository actually hangs together.

  python      import and from-import, resolved to a file in this repository
  typescript  import, export-from, and dynamic import
  terraform   module source references between root and child modules
  docker      COPY and the build context each Dockerfile pulls from

Two outputs.

  docs/architecture/file-graph.md    Mermaid, readable in GitLab and in a diff
  docs/architecture/file-graph.json  the same graph, for any tool that wants it

It also enforces the layering contract. Any edge that violates the direction in
`pyproject.toml` under `tool.importlinter` is reported and fails the run, so the
graph is a gate and not only a picture. A drawing nobody checks goes stale in a
fortnight.

Usage:
  scripts/docs/build_file_graph.py            build and check
  scripts/docs/build_file_graph.py --check    check only, write nothing
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections import defaultdict
from collections.abc import Iterator
from pathlib import Path

#: One dependency: the file that depends, the file depended on, and how the
#: dependency was found. A tuple rather than a dataclass because it is built in
#: two hot loops and never mutated, and naming it here is what lets four
#: signatures say what they carry instead of saying `list`.
Edge = tuple[str, str, str]

ROOT = Path(__file__).resolve().parent.parent.parent
OUT_DIR = ROOT / "docs" / "architecture"

PY_PACKAGES = ("finops_core", "finops_providers", "finops_ingest", "finops_api", "finops_mcp")

# Allowed direction. A layer may import anything below it, never above.
# Index 0 is the top of the stack.
#: Highest first. This must equal the `layers are respected` contract in
#: pyproject.toml, and for a while it did not: this list had finops_mcp below
#: finops_api, which is backwards. The MCP server is a facade in front of the
#: API, constraint 8, so it sits above it. A test holds the two equal, because
#: two definitions of one ordering that disagree means one of the two checks is
#: enforcing the opposite of the rule.
LAYERS = ["finops_mcp", "finops_api", "finops_ingest", "finops_providers", "finops_core"]
LAYER_RANK = {name: index for index, name in enumerate(LAYERS)}

SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "htmlcov",
    ".terraform",
    "security",
    "scratch",
    "tmp",
}

TS_IMPORT = re.compile(
    r"""(?:import|export)\s+(?:[\w*\s{},]+\s+from\s+)?['"](\.[^'"]+)['"]"""
    r"""|import\(\s*['"](\.[^'"]+)['"]\s*\)"""
)
TF_MODULE = re.compile(r'source\s*=\s*"(\.[^"]+)"')
DOCKER_COPY = re.compile(r"^\s*COPY\s+(?:--from=\S+\s+)?(.+?)\s+\S+\s*$", re.MULTILINE)


def walk(root: Path) -> Iterator[Path]:
    for path in root.rglob("*"):
        if path.is_dir():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        yield path


def module_to_path(module: str) -> str | None:
    """Resolve a dotted module to a file in this repository, or None."""
    if not module.startswith(PY_PACKAGES):
        return None
    base = module.replace(".", "/")
    for candidate in (f"{base}.py", f"{base}/__init__.py"):
        if (ROOT / candidate).exists():
            return candidate
    # The module may not exist on disk yet. Point at the package so the graph is
    # still useful during a build that is partly written.
    parts = base.split("/")
    while parts:
        if (ROOT / "/".join(parts)).exists():
            return "/".join(parts)
        parts.pop()
    return None


def python_edges(path: Path, rel: str, edges: list[Edge], unresolved: list[str]) -> None:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError) as exc:
        unresolved.append(f"{rel}: could not parse, {exc}")
        return
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names = [node.module]
        for name in names:
            target = module_to_path(name)
            if target and target != rel:
                edges.append((rel, target, "python"))


def text_edges(
    path: Path, rel: str, pattern: re.Pattern[str], kind: str, edges: list[Edge]
) -> None:
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return
    for match in pattern.finditer(content):
        raw = next((g for g in match.groups() if g), None)
        if not raw:
            continue
        for token in raw.split():
            if token.startswith("-") or "*" in token:
                continue
            resolved = (path.parent / token).resolve()
            try:
                target = resolved.relative_to(ROOT).as_posix()
            except ValueError:
                continue
            if kind == "typescript" and not (ROOT / target).exists():
                for suffix in (".ts", ".tsx", "/index.ts", "/index.tsx"):
                    if (ROOT / (target + suffix)).exists():
                        target += suffix
                        break
            if target != rel:
                edges.append((rel, target, kind))


def build() -> tuple[list[Edge], list[str], list[str]]:
    edges: list[tuple[str, str, str]] = []
    unresolved: list[str] = []
    nodes: set[str] = set()

    for path in walk(ROOT):
        rel = path.relative_to(ROOT).as_posix()
        suffix = path.suffix
        if suffix == ".py":
            nodes.add(rel)
            python_edges(path, rel, edges, unresolved)
        elif suffix in (".ts", ".tsx"):
            nodes.add(rel)
            text_edges(path, rel, TS_IMPORT, "typescript", edges)
        elif suffix == ".tf":
            nodes.add(rel)
            text_edges(path, rel, TF_MODULE, "terraform", edges)
        elif path.name.startswith("Dockerfile"):
            nodes.add(rel)
            text_edges(path, rel, DOCKER_COPY, "docker", edges)

    for source, target, _ in edges:
        nodes.add(source)
        nodes.add(target)

    return sorted(set(edges)), sorted(nodes), unresolved


def top_package(rel: str) -> str | None:
    head = rel.split("/", 1)[0]
    return head if head in LAYER_RANK else None


def check_layers(edges: list[tuple[str, str, str]]) -> list[str]:
    """An edge must point down the stack or sideways within a package."""
    violations = []
    for source, target, kind in edges:
        if kind != "python":
            continue
        a, b = top_package(source), top_package(target)
        if a and b and a != b and LAYER_RANK[a] > LAYER_RANK[b]:
            violations.append(
                f"{source} imports {target}. {a} is below {b} in the layer stack, "
                f"so this edge points the wrong way. See ADR-0011 and pyproject.toml."
            )
    return violations


def render_mermaid(edges: list[Edge], nodes: list[str]) -> str:
    groups: dict[str, list[str]] = defaultdict(list)
    for node in nodes:
        groups[node.split("/", 1)[0]].append(node)

    ident = {node: f"n{index}" for index, node in enumerate(nodes)}
    lines = [
        "# File dependency graph",
        "",
        "Generated by `make graph`. Do not edit by hand.",
        "",
        "Every edge is a real dependency read out of the source: a Python import,",
        "a TypeScript import, a Terraform module reference, or a Dockerfile COPY.",
        "",
        f"{len(nodes)} files, {len(edges)} edges.",
        "",
        "Interactive version, pan, zoom and filter: `docs/architecture/file-graph.html`",
        "",
        "```mermaid",
        "graph LR",
    ]
    for group in sorted(groups):
        lines.append(f'  subgraph {group}["{group}"]')
        for node in sorted(groups[group]):
            label = node.split("/")[-1]
            lines.append(f'    {ident[node]}["{label}"]')
        lines.append("  end")
    style = {"python": "-->", "typescript": "-->", "terraform": "-.->", "docker": "==>"}
    for source, target, kind in edges:
        lines.append(f"  {ident[source]} {style.get(kind, '-->')} {ident[target]}")
    lines += ["```", ""]

    lines += ["## Edges by kind", "", "| Kind | Count |", "| --- | --- |"]
    counts: dict[str, int] = defaultdict(int)
    for _, _, kind in edges:
        counts[kind] += 1
    lines += [f"| {kind} | {counts[kind]} |" for kind in sorted(counts)]
    lines.append("")

    lines += ["## Most depended upon", "", "| File | Incoming edges |", "| --- | --- |"]
    incoming: dict[str, int] = defaultdict(int)
    for _, target, _ in edges:
        incoming[target] += 1
    for node, count in sorted(incoming.items(), key=lambda kv: (-kv[1], kv[0]))[:15]:
        lines.append(f"| `{node}` | {count} |")
    lines.append("")

    orphans = sorted(n for n in nodes if n not in incoming and not any(s == n for s, _, _ in edges))
    lines += ["## Files with no edges", ""]
    lines += (
        ["None."]
        if not orphans
        else ["A file with no edges is either an entry point or dead. Check each one.", ""]
        + [f"- `{n}`" for n in orphans[:40]]
    )
    lines.append("")
    return "\n".join(lines)


# The interactive HTML output was removed. It checked for a cytoscape bundle
# that was never vendored, and the content security posture rules out loading
# one from a CDN, so it rendered a header and an apology. The Mermaid output in
# file-graph.md works, renders in GitLab and in a diff, and is what people
# actually read.
#
# Rung zero of the ADR-0013 ladder: does this need to exist at all. It did not.
# AUDIT-001, finding A001-F07. If pan and zoom is ever genuinely needed, vendor
# the bundle into docs/architecture/vendor/ and restore this from git history.


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="check only, write nothing")
    args = parser.parse_args()

    edges, nodes, unresolved = build()
    violations = check_layers(edges)

    for message in unresolved:
        print(f"WARN: {message}", file=sys.stderr)

    if violations:
        print(f"FAIL: {len(violations)} layering violation(s)\n")
        for violation in violations:
            print(f"  {violation}")
        return 1

    if not args.check:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        (OUT_DIR / "file-graph.md").write_text(render_mermaid(edges, nodes))
        # The graph is also emitted as JSON, so a future tool can consume it
        # without re parsing the repository.
        (OUT_DIR / "file-graph.json").write_text(
            json.dumps(
                {"nodes": nodes, "edges": [{"s": a, "t": b, "k": k} for a, b, k in edges]},
                indent=2,
            )
        )

    print(f"OK: {len(nodes)} files, {len(edges)} edges, 0 layering violations")
    return 0


if __name__ == "__main__":
    sys.exit(main())
