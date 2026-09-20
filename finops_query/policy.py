"""Identifying a query across days, and across the values a variable takes.

Extracted from the prototype under the golden files. The problem this solves is
not obvious until you see it fail: a templated dashboard produces a different
query string for every value its variables take, so a panel with a `$region`
variable and four regions looks like four unrelated queries, none of which has
enough history to trend and each of which is a quarter of the real cost.

Three keys, and the difference between them is the whole module.

`normalise` is whitespace and case only. Two people writing the same query with
different indentation get the same key.

`template_key` additionally collapses every variable to a single placeholder,
so `$region` resolving to four values is one key. This is what a fingerprint is
built from, and it is why a templated panel trends as one thing.

`match_pattern` goes the other way: it turns a template into a regex that
matches its own resolved executions, so a CloudTrail event carrying
`eu-west-1` can be attributed back to a panel that stores `$region`. Without
it, measured execution counts never attach to templated panels, which are most
of the expensive ones.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

_WHITESPACE = re.compile(r"\s+")

#: Line comments in the query languages this reads: `#` for Logs Insights and
#: PromQL, `--` for SQL shaped sources, and a block comment for both. Required
#: to be at a start of line or preceded by whitespace, so a `#` inside a token
#: like a regex is left alone. ISS-142 records the residual case, a comment
#: marker inside a quoted string, which would shorten the key and never the
#: stored query or the cost.
_COMMENT = re.compile(r"(?m)(?:^|(?<=\s))(?:#|--)[^\n]*|/\*.*?\*/", re.DOTALL)

#: Grafana's three template variable syntaxes, all still in use.
_TEMPLATE_VAR = re.compile(r"(\$\{[^}]+\}|\$[A-Za-z_][A-Za-z0-9_]*|\[\[[^\]]+\]\])")

#: What a variable collapses to. U+0001, and written as an escape rather than
#: as the character itself: it cannot appear in a query, so it can never collide
#: with real text the way a word or a punctuation run could.
PLACEHOLDER = "\u0001"

#: How much of the digest a fingerprint keeps. Sixteen hex characters is 64
#: bits, which at any realistic number of queries per tenant makes a collision
#: far less likely than a mistake in the data it identifies.
FINGERPRINT_LENGTH = 16


def strip_comments(text: str | None) -> str:
    """Comments removed, so annotating a query does not make it a new one.

    A person adding `# owned by platform` above a panel query has not changed
    what it costs, and a key that moved would lose every day of history behind
    it.
    """
    return _COMMENT.sub(" ", text or "")


def normalise(text: str | None) -> str:
    """Comments, whitespace and case, so formatting does not fragment a query."""
    return _WHITESPACE.sub(" ", strip_comments(text).strip()).lower()


def has_template_vars(text: str | None) -> bool:
    return bool(_TEMPLATE_VAR.search(text or ""))


def template_key(text: str | None) -> str:
    """Normalised, with every variable collapsed to one placeholder.

    This is what makes a templated panel one query rather than one per value a
    variable happens to take.
    """
    return normalise(_TEMPLATE_VAR.sub(PLACEHOLDER, text or ""))


def query_key(engine: str, query: str | None, targets: tuple[str, ...] = ()) -> str:
    """What a query *is*, independent of where it is drawn.

    Distinct from `fingerprint`, and the difference is the point.

    `fingerprint` identifies one definition: a panel, on a dashboard, in a
    workspace. It has to, because `uq_query_definition__fingerprint` makes it
    the identity of a row, and two panels sharing one would upsert over each
    other and lose a panel.

    `query_key` identifies the query itself. Two panels running the same query
    on different dashboards share it, which is what lets a measured execution
    attach to both rather than to whichever one happened to be looked up first.
    TASK-P2-013 is what consumes it.
    """
    parts = [engine, template_key(query), "|".join(sorted(targets))]
    joined = "\u0000".join(parts).encode("utf-8")
    return hashlib.sha1(joined, usedforsecurity=False).hexdigest()[:FINGERPRINT_LENGTH]


def match_pattern(text: str | None) -> re.Pattern[str] | None:
    """A regex matching the resolved executions of a templated query.

    Variables become a non-space run, everything else is escaped, and the parts
    are joined by flexible whitespace. Returns None when there is nothing to
    match on or when the result will not compile, because a template that
    cannot produce a pattern must attribute nothing rather than match
    everything.
    """
    parts = _TEMPLATE_VAR.split(text or "")
    pieces: list[str] = []
    for index, part in enumerate(parts):
        if index % 2 == 1:
            pieces.append(r"\S+")
        else:
            pieces.append(re.escape(_WHITESPACE.sub(" ", part.strip().lower())))

    pattern = r"\s*".join(piece for piece in pieces if piece != "")
    if not pattern:
        return None
    try:
        return re.compile(pattern)
    except re.error:
        return None


def fingerprint(
    account_id: str,
    workspace_name: str,
    dashboard_uid: str,
    panel: str,
    ref_id: str,
    query: str,
) -> str:
    """A stable identifier for one query, across days and across variable values.

    The arguments are named rather than taken as a dict. In the prototype this
    read six keys out of a finding, so a caller that spelled one wrong got a
    silently different fingerprint and the query looked new. Naming them makes
    that a type error instead.

    sha1 is not a security decision here. This identifies a row, it does not
    authenticate one, and it is truncated to 64 bits anyway.
    """
    parts = [
        account_id,
        workspace_name,
        dashboard_uid,
        panel,
        ref_id,
        template_key(query),
    ]
    joined = "|".join(parts).encode("utf-8")
    return hashlib.sha1(joined, usedforsecurity=False).hexdigest()[:FINGERPRINT_LENGTH]


def fingerprint_of(finding: dict[str, Any]) -> str:
    """The prototype's dict shaped call, kept for the collector.

    Falls back from `dashboard_uid` to `dashboard`, which is what the prototype
    did: a dashboard with no uid still needs a stable key, and its title is the
    only other thing that identifies it.
    """
    return fingerprint(
        account_id=str(finding.get("account_id", "")),
        workspace_name=str(finding.get("workspace_name", "")),
        dashboard_uid=str(finding.get("dashboard_uid", "") or finding.get("dashboard", "")),
        panel=str(finding.get("panel", "")),
        ref_id=str(finding.get("ref_id", "")),
        query=str(finding.get("query", "")),
    )
