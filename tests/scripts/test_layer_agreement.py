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


def test_the_facade_sits_above_the_api() -> None:
    """Constraint 8. The MCP server calls the API, so it is in front of it."""
    layers = contract_layers()
    assert layers.index("finops_mcp") < layers.index("finops_api")
