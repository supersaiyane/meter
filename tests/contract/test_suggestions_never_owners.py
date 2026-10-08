"""No owner source, and no write but a person's, sets `recommendation.owner`. TASK-P11-005.

P11 spec section 5.1 and ISS-021: a suggestion says whom to ask, and an owner is a person's
decision. Held over the source text, every SQL statement production code holds that writes the
recommendation table: an insert writes its owner as NULL and never sets it on conflict, and the one
update that sets it is the lifecycle move, which writes the owner the person named. The modules
that read owners write nothing to the recommendation table at all.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRODUCTION = (
    "finops_api",
    "finops_core",
    "finops_fakes",
    "finops_ingest",
    "finops_mcp",
    "finops_providers",
    "finops_query",
    "finops_relay",
    "scripts",
)
#: Where owners are read from, P11. None of them may write a recommendation.
SOURCES = (
    "finops_core/domain/ownership.py",
    "finops_core/ports/ownership.py",
    "finops_fakes/ownership.py",
    "finops_ingest/collectors/ownership.py",
    "finops_providers/aws/appregistry.py",
    "finops_providers/aws/cloudtrail_creators.py",
)
#: The one statement allowed to set an owner, and what it sets it to: the caller's.
MOVE = ("finops_api/lifecycle.py", "owner = COALESCE(:owner, owner)")
#: Fixture data, not an owner source: the demo plants finished work as a person left it, DONE and
#: owned by whoever accepted it, so its history has verified savings to show.
PLANTED = "scripts/demo/seed_demo.py"

WRITES = re.compile(r"\b(INSERT INTO|UPDATE) recommendation(?!\w)", re.IGNORECASE)
SETS_OWNER = re.compile(r"\bowner\s*=", re.IGNORECASE)
CORE_WRITES = re.compile(
    r"(insert|update)\(\s*models\.recommendation\b|models\.recommendation\.(insert|update)\("
)


def statements() -> list[tuple[str, str, str]]:
    """Every SQL literal in production code that writes the recommendation table."""
    found = []
    for package in PRODUCTION:
        for path in sorted((ROOT / package).rglob("*.py")):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    for match in WRITES.finditer(node.value):
                        where = str(path.relative_to(ROOT))
                        found.append(
                            (where, match.group(1).split()[0].upper(), node.value[match.start() :])
                        )
    return found


def _values(sql: str) -> list[str]:
    """The top level items of the first parenthesised list after VALUES."""
    start = sql.upper().index("VALUES") + len("VALUES")
    opened = sql.index("(", start)
    depth, item = 0, ""
    items: list[str] = []
    for char in sql[opened + 1 :]:
        if char == "(":
            depth += 1
        elif char == ")" and depth == 0:
            return [*items, item.strip()]
        elif char == ")":
            depth -= 1
        if char == "," and depth == 0:
            items.append(item.strip())
            item = ""
        else:
            item += char
    raise AssertionError(f"no closing parenthesis after VALUES in {sql[:80]!r}")


def test_the_scan_finds_the_writes_it_is_meant_to_hold() -> None:
    kinds = {(where, kind) for where, kind, _ in statements()}
    assert ("finops_api/lifecycle.py", "UPDATE") in kinds
    assert ("finops_ingest/collectors/recommendations.py", "INSERT") in kinds


def test_every_insert_writes_no_owner_and_never_sets_one_on_conflict() -> None:
    for where, kind, sql in statements():
        if kind != "INSERT":
            continue
        columns = [one.strip() for one in sql[sql.index("(") + 1 : sql.index(")")].split(",")]
        if "owner" in columns:
            values = _values(sql)
            if where == PLANTED:
                assert values[columns.index("lifecycle")] == "'DONE'", where
            else:
                assert values[columns.index("owner")].upper() == "NULL", where
        conflict = sql.upper().split("ON CONFLICT", 1)
        assert len(conflict) == 1 or not SETS_OWNER.search(conflict[1]), where


def test_the_only_update_setting_an_owner_writes_the_one_the_person_named() -> None:
    setting = [(where, sql) for where, kind, sql in statements() if SETS_OWNER.search(sql)]
    assert [where for where, _ in setting] == [MOVE[0]]
    assert MOVE[1] in setting[0][1]


def test_no_production_code_writes_a_recommendation_through_the_table_object() -> None:
    for package in PRODUCTION:
        for path in sorted((ROOT / package).rglob("*.py")):
            assert not CORE_WRITES.search(path.read_text()), path


def test_no_owner_source_writes_a_recommendation() -> None:
    for name in SOURCES:
        source = (ROOT / name).read_text()
        assert not WRITES.search(source), name
        assert "models.recommendation" not in source, name
