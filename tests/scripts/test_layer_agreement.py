"""One layer ordering, described in two places, held equal.

`pyproject.toml` states it for import-linter and `scripts/docs/build_file_graph.py`
states it again for the file graph. They disagreed: the graph put `finops_mcp`
below `finops_api`, which is backwards, so the graph check was enforcing the
opposite of the rule for that pair while import-linter enforced the rule.

Neither check noticed, because each was internally consistent. Only holding them
against each other finds it.
"""

from __future__ import annotations

import importlib.util
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def graph_layers() -> list[str]:
    spec = importlib.util.spec_from_file_location(
        "build_file_graph", ROOT / "scripts" / "docs" / "build_file_graph.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return list(module.LAYERS)


def contract_layers() -> list[str]:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    contracts = config["tool"]["importlinter"]["contracts"]
    layered = [c for c in contracts if c["type"] == "layers"]
    assert len(layered) == 1, "expected exactly one layers contract to compare against"
    return list(layered[0]["layers"])


def test_the_two_layer_orderings_are_the_same() -> None:
    assert graph_layers() == contract_layers()


def declared_packages() -> list[str]:
    """The distribution's own package list, which is the closest thing to truth."""
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return list(config["tool"]["setuptools"]["packages"])


def test_every_package_is_placed_in_the_layer_ordering() -> None:
    """A package in neither list is a package with no layer constraint at all.

    `finops_query` was in neither for two days after it was created, so it could
    have imported `finops_api` and both checks would have passed. Holding the
    two orderings equal did not catch it, because they agreed about a package
    neither of them mentioned.
    """
    missing = set(declared_packages()) - set(contract_layers())

    assert declared_packages(), "expected packages, not an empty list"
    assert missing == set(), f"these have no layer, so nothing constrains them: {sorted(missing)}"


def test_the_facade_sits_above_the_api() -> None:
    """Constraint 8. The MCP server calls the API, so it is in front of it."""
    layers = contract_layers()
    assert layers.index("finops_mcp") < layers.index("finops_api")
