"""The `QueryParser` port, implemented over this package's own functions.

A thin binding and nothing more. It exists because `finops_providers` may not
import `finops_query`, the layer order in `pyproject.toml` putting the analysis
above the adapter that fetched what it analyses. The adapter names the port, a
collector passes this in, and the import direction stays pointing down.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from finops_query.classify import (
    Classification,
    classify,
    iter_panels,
    refresh_seconds,
    relative_range_seconds,
)
from finops_query.ownership import principal_from
from finops_query.policy import fingerprint, normalise


class GrafanaQueryParser:
    """`QueryParser` for Grafana shaped JSON."""

    def classify(self, target: Mapping[str, Any], panel_datasource: Any = None) -> Classification:
        return classify(dict(target), panel_datasource)

    def iter_panels(self, panels: Any) -> Iterable[Mapping[str, Any]]:
        found: Iterable[Mapping[str, Any]] = iter_panels(panels)
        return found

    def principal_from(self, event_detail: Mapping[str, Any]) -> str | None:
        return principal_from(dict(event_detail))

    def normalise(self, text: str | None) -> str:
        return normalise(text)

    def refresh_seconds(self, raw: Any) -> int:
        return refresh_seconds(raw)

    def relative_range_seconds(self, raw: Any) -> int | None:
        return relative_range_seconds(raw)

    def fingerprint(
        self,
        *,
        account_id: str,
        workspace_name: str,
        dashboard_uid: str,
        panel: str,
        ref_id: str,
        query: str,
    ) -> str:
        return fingerprint(
            account_id=account_id,
            workspace_name=workspace_name,
            dashboard_uid=dashboard_uid,
            panel=panel,
            ref_id=ref_id,
            query=query,
        )
