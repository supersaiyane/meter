"""The ports are the whole reason a second cloud is a connector and not a rewrite.

Constraint 1 in CLAUDE.md: `finops_core` imports no cloud SDK. `lint-imports`
proves it for the package as a whole on every build, and the scan here proves
it again from the source, because the two checks fail for different reasons and
the one that survives a configuration change is the one that saves the rule.

The failure documentation test is the load bearing one. A port method that does
not say which of the six causes it raises leaves the caller to guess, and a
caller that guesses writes `except Exception` and collapses the taxonomy that
TASK-P0-005 exists to keep open.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from typing import Protocol, get_type_hints

import pytest

from finops_core import errors, ports

ROOT = Path(__file__).resolve().parent.parent.parent
CORE = ROOT / "finops_core"

EXPECTED_PORTS = {
    "AccountDiscovery",
    "CredentialBroker",
    "CostExport",
    # P6, TASK-P6-004. A cluster and a reservation are read from different places
    # and fail independently, so both live behind one port with two methods rather
    # than two ports: a caller that can read one can always read the other.
    "ContainerSource",
    "MetricSource",
    "ResourceInventory",
    "QuotaSource",
    "IdentityProvider",
    "EntitlementResolver",
    "QuerySurface",
    # P2, TASK-P2-017. One instance wide setting, kept off `QuerySurface`
    # because that port is about the queries an instance holds and a surface
    # may support one without the other.
    "RefreshFloor",
    # P2, TASK-P2-019. The largest write, and its own port for the same reason:
    # a surface may let Meter read queries and never let it replace one.
    "PanelRewrite",
}

FORBIDDEN_IMPORTS = {"boto3", "botocore", "fastapi", "sqlalchemy", "httpx", "requests"}

ERROR_NAMES = {t.__name__ for t in errors.CollectionError.__subclasses__()}


def port_types() -> list[type]:
    return [getattr(ports, name) for name in sorted(EXPECTED_PORTS)]


def port_methods(port: type) -> list[tuple[str, object]]:
    return [
        (name, member)
        for name, member in vars(port).items()
        if not name.startswith("_") and callable(member)
    ]


# --- shape -------------------------------------------------------------------


def test_there_are_exactly_twelve_ports() -> None:
    """The provider ports, plus the three P2 surface ports.

    `__all__` also carries the two grouping tuples, so the comparison is against
    the protocols rather than against every name the package exports. Adding a
    port means adding it to `EXPECTED_PORTS` here, which is the point: a port
    that appears without anybody deciding to add it is a port nobody reviewed.
    """
    exported = {name for name in ports.__all__ if not name.isupper() and "_" not in name}

    assert exported == EXPECTED_PORTS


def test_the_two_groups_together_are_every_port() -> None:
    """The groups exist so a test can ask for provider ports without filtering
    by hand, and a port left out of both would be invisible to every caller
    that uses them."""
    grouped = {port.__name__ for port in (*ports.PROVIDER_PORTS, *ports.SURFACE_PORTS)}

    assert grouped == EXPECTED_PORTS
    assert len(ports.PROVIDER_PORTS) == 9
    assert len(ports.SURFACE_PORTS) == 3


def test_all_ports_are_protocols() -> None:
    for port in port_types():
        assert getattr(port, "_is_protocol", False), port.__name__
        assert getattr(port, "_is_runtime_protocol", False), port.__name__
        # Protocol really is in the mro of a Protocol subclass at runtime, but
        # it is a typing special form and the type system does not model it as
        # a class, so the containment check cannot be expressed.
        assert Protocol in port.__mro__ or issubclass(port, Protocol)  # type: ignore[comparison-overlap, arg-type]  # type: ignore[arg-type]


def test_every_port_declares_at_least_one_method() -> None:
    for port in port_types():
        assert port_methods(port), port.__name__


def test_no_port_method_is_implemented() -> None:
    """A port with a body is an implementation, and implementations belong to adapters."""
    for port in port_types():
        for name, method in port_methods(port):
            source = inspect.getsource(method)  # type: ignore[arg-type]
            body = source.split(":", 1)[1]
            assert "..." in body or "raise NotImplementedError" in body, f"{port.__name__}.{name}"


# --- the failure contract ----------------------------------------------------


def test_every_port_method_documents_which_errors_it_raises() -> None:
    for port in port_types():
        for name, method in port_methods(port):
            doc = inspect.getdoc(method) or ""
            named = {cause for cause in ERROR_NAMES if cause in doc}
            assert named, f"{port.__name__}.{name} names none of the six causes"


def test_the_documented_causes_are_real_ones() -> None:
    """A docstring naming an error that does not exist teaches the wrong handler."""
    for port in port_types():
        for name, method in port_methods(port):
            doc = inspect.getdoc(method) or ""
            for line in doc.splitlines():
                if line.strip().startswith("Raises"):
                    continue
            assert "CollectorError" not in doc, f"{port.__name__}.{name}"


# --- provider neutrality -----------------------------------------------------


def test_core_imports_no_cloud_sdk() -> None:
    offenders: list[str] = []
    for path in sorted(CORE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [(node.module or "").split(".")[0]]
            else:
                continue
            for name in names:
                if name in FORBIDDEN_IMPORTS:
                    offenders.append(f"{path.relative_to(ROOT)} imports {name}")
    assert offenders == []


def test_no_port_signature_mentions_an_arn_or_a_provider_type() -> None:
    """If AccountDiscovery returns something with an ARN in it, the abstraction failed."""
    for port in port_types():
        for name, method in port_methods(port):
            rendered = str(inspect.signature(method))  # type: ignore[arg-type]
            lowered = rendered.lower()
            assert "arn" not in lowered, f"{port.__name__}.{name}"
            assert "boto" not in lowered, f"{port.__name__}.{name}"


def test_port_annotations_resolve_to_real_types() -> None:
    """An unresolvable annotation means an adapter cannot be checked against the port."""
    for port in port_types():
        for name, method in port_methods(port):
            try:
                get_type_hints(method)
            except Exception as failure:  # pragma: no cover - the assert reports it
                pytest.fail(f"{port.__name__}.{name}: {failure}")


# --- the four P0 does not implement ------------------------------------------


def test_the_ports_p0_does_not_implement_are_defined_anyway() -> None:
    """Cheap now, expensive to retrofit once three consumers exist."""
    for name in ("CostExport", "MetricSource", "ResourceInventory", "QuotaSource"):
        assert hasattr(ports, name)
