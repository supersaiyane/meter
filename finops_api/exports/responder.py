"""The one export responder. FEAT-067, TASK-P8-009, P8 spec section 5.5 item 1.

A route a screen reads is marked `@exportable(ExportSpec(...))`, between its `@router.get` and
its `def`. Without `format`, or with `format=json`, the route answers as it always has. With
`format=xlsx` or `format=csv`, the envelope the route built, after the same scope dependency and
repository guard as the screen, is written as a file, recorded in `report_run` in the same
transaction, and returned in its place.

**Why a decorator rather than a line in every route.** A route can return from more than one
place, and an export added at the last `return` would answer JSON for a file from an early one.
Wrapping the whole function leaves no return the export can miss, and the route body stays
exactly what the screen reads, so the file's rows are the screen's rows by construction rather
than by a test that has to catch a drift.

**Why the signature is rebuilt.** FastAPI reads a route's parameters from its signature. The
wrapper's signature is the route's own, with every annotation resolved in the route's module,
plus one keyword parameter carrying the export dependency. The annotations are resolved first
because the route modules postpone them, and FastAPI would otherwise look the names up in this
module and find none of them.
"""

from __future__ import annotations

import functools
import inspect
import operator
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Final, Literal, get_type_hints
from urllib.parse import parse_qsl, urlencode, urlsplit
from uuid import UUID

from fastapi import Depends, HTTPException, Query, Request, Response, status
from fastapi.routing import APIRoute
from pydantic import BaseModel
from sqlalchemy.engine import Connection

from finops_api.db.repositories.reports import record_run
from finops_api.deps import get_connection, get_scope, get_settings
from finops_api.exports.cells import collector_name, columns_of, header
from finops_api.exports.writers import Sheet, Written, csv_file, xlsx
from finops_api.schemas import CoverageOut, Envelope
from finops_core.config import Settings
from finops_core.domain.tenant import Scope

ExportFormat = Literal["json", "xlsx", "csv"]

MEDIA_TYPES: Final[Mapping[str, str]] = {
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "csv": "text/csv; charset=utf-8",
}

#: The run a file was recorded as, on every file the responder answers with. The report runner
#: reads it to attach the schedule and the stored file to the row the responder just wrote, so
#: one file still has one record. FEAT-069.
RUN_HEADER: Final = "X-Meter-Run"

#: Every amount the API holds is in US dollars, so the About sheet says it once.
CURRENCY: Final = "USD, for every amount in the Data sheet"

#: The keyword the wrapper adds to a route's signature. Distinct from every route parameter,
#: which `exportable` checks rather than assumes.
EXPORT_PARAMETER: Final = "exporter"

#: How many accounts the About sheet names before it counts the rest.
NAMED_ACCOUNTS: Final = 20

#: What most cost views measure, by the FOCUS column and what it means.
EFFECTIVE_COST: Final = "Effective Cost, which is amortized"
BOTH_COSTS: Final = "Effective Cost, which is amortized, beside Billed Cost"

NOBODY: Final = (
    "An export is recorded against the person who made it, and this session names nobody."
)


@dataclass(frozen=True)
class View:
    """What a describer reads: the route's answer and the query it was asked with."""

    data: Any
    query: Mapping[str, str]


Describe = str | Callable[[View], str] | None


@dataclass(frozen=True)
class ExportSpec:
    """How one route's envelope becomes rows, and what its About sheet says about them."""

    title: str
    row_model: type[BaseModel]
    rows: Callable[[Any], Sequence[BaseModel]]
    #: The route's own name for a column, where its FOCUS name or its words would mislead: the
    #: same `name` is a service on one route and an account on another.
    headers: Mapping[str, str] | Callable[[View], Mapping[str, str]] = field(default_factory=dict)
    grouping: Describe = None
    period: Describe = None
    metric: Describe = None
    #: Anything the screen shows that the rows do not hold, said rather than dropped.
    note: Describe = None


def listed(data: Any) -> Sequence[BaseModel]:
    """The rows of a route whose data is the list itself."""
    rows: Sequence[BaseModel] = data
    return rows


def single(data: Any) -> Sequence[BaseModel]:
    """The one row of a route whose data is a single figure."""
    return (data,)


def rows_in(name: str) -> Callable[[Any], Sequence[BaseModel]]:
    """The rows of a route whose data holds them under `name`."""
    return operator.attrgetter(name)


def billing_period(view: View) -> str:
    """The period a cost route read: the one asked for, or the newest one collected."""
    asked = view.query.get("period")
    return (
        f"The billing period starting {asked}" if asked else "The newest billing period collected"
    )


class ExportDependency:
    """The dependency `exportable` adds to a route. It holds the route's spec, which is how the
    enumeration test tells an exportable route from one that forgot."""

    def __init__(self, spec: ExportSpec) -> None:
        self.spec = spec

    def __call__(
        self,
        request: Request,
        file_format: ExportFormat = Query(
            default="json",
            alias="format",
            description="json for the screen, xlsx for a workbook, csv for every row",
        ),
        connection: Connection = Depends(get_connection),
        scope: Scope = Depends(get_scope),
        settings: Settings = Depends(get_settings),
    ) -> Exporter:
        if file_format != "json" and scope.principal_id is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail=NOBODY)
        return Exporter(
            self.spec, request, file_format, connection, scope, settings.export_row_limit
        )


class Exporter:
    """One request's export: the envelope as it is, or as a file."""

    def __init__(
        self,
        spec: ExportSpec,
        request: Request,
        file_format: ExportFormat,
        connection: Connection,
        scope: Scope,
        limit: int,
    ) -> None:
        self.spec = spec
        self.request = request
        self.file_format = file_format
        self.connection = connection
        self.scope = scope
        self.limit = limit

    def respond[T](self, envelope: Envelope[T]) -> Envelope[T] | Response:
        """The envelope for a screen, or the file for an export."""
        if self.file_format == "json":
            return envelope
        view = View(envelope.data, self.query())
        sheet = self.sheet(view)
        made_at = datetime.now(UTC)
        if self.file_format == "xlsx":
            written = xlsx(
                sheet, self.about(envelope, view, made_at), _failures(envelope), self.limit
            )
        else:
            written = csv_file(sheet)
        run_id = self._record(written, made_at, envelope)
        return Response(
            content=written.body,
            media_type=MEDIA_TYPES[self.file_format],
            headers={
                "Content-Disposition": f'attachment; filename="{self.filename(made_at)}"',
                "Cache-Control": "no-store",
                RUN_HEADER: str(run_id),
            },
        )

    def sheet(self, view: View) -> Sheet:
        """The rows the screen shows, with their headings."""
        names = self.spec.headers(view) if callable(self.spec.headers) else self.spec.headers
        columns = tuple(columns_of(self.spec.row_model))
        return Sheet(
            columns=columns,
            headers=tuple(header(path, names) for path in columns),
            rows=self.spec.rows(view.data),
        )

    def about(
        self, envelope: Envelope[Any], view: View, made_at: datetime
    ) -> list[tuple[str, str]]:
        """What the file is, so it can be read without the screen it came from."""
        meta = envelope.meta
        coverage = meta.scope_coverage
        total = len(self.spec.rows(envelope.data))
        rows = str(total)
        if total > self.limit:
            rows = f"{self.limit} of {total}. The CSV of the same view holds all {total}."
        return [
            ("View", self.spec.title),
            ("Route", self.request.url.path),
            ("Filters", "; ".join(f"{key}={value}" for key, value in view.query.items()) or "None"),
            ("Grouping", _describe(self.spec.grouping, view) or "None"),
            ("Period", _describe(self.spec.period, view) or "Not a view of a period"),
            ("Currency", CURRENCY),
            ("Cost metric", _describe(self.spec.metric, view) or "Not a view of cost"),
            ("Scope", _scope_words(self.scope)),
            ("Coverage", _coverage_words(coverage)),
            ("As of", _moment(meta.as_of)),
            ("Collected at", _moment(meta.collected_at)),
            ("Rows", rows),
            (
                "Row limit",
                f"A workbook holds at most {self.limit} rows. "
                "The CSV of the same view holds every row.",
            ),
            ("Failures", f"{len(meta.failures)}, listed below" if meta.failures else "None"),
            ("Made at", _moment(made_at)),
            ("Made by", self.scope.principal_id or ""),
            ("Times", "Every time in this workbook is UTC."),
            ("Note", _describe(self.spec.note, view) or "None"),
        ]

    def query(self) -> dict[str, str]:
        """The query the view was drawn with, without the format that asked for the file."""
        found: dict[str, list[str]] = {}
        for key, value in self.request.query_params.multi_items():
            if key != "format":
                found.setdefault(key, []).append(value)
        return {key: ", ".join(values) for key, values in found.items()}

    def filename(self, made_at: datetime) -> str:
        """meter, the view, the day: a name a person can find again in their downloads."""
        slug = re.sub(r"[^a-z0-9]+", "-", self.spec.title.lower()).strip("-")
        return f"meter-{slug}-{made_at:%Y-%m-%d}.{self.file_format}"

    def _record(self, written: Written, made_at: datetime, envelope: Envelope[Any]) -> UUID:
        kept = [
            (key, value)
            for key, value in self.request.query_params.multi_items()
            if key != "format"
        ]
        return record_run(
            self.connection,
            tenant_id=self.scope.tenant_id,
            principal_id=self.scope.principal_id or "",
            view_path=self.request.url.path,
            view_query=urlencode(kept),
            scope_accounts=None
            if self.scope.is_global
            else [account.account_id for account in self.scope.accounts],
            file_format=self.file_format,
            rows=written.rows,
            size=len(written.body),
            truncated=written.truncated,
            made_at=made_at,
            as_of=envelope.meta.as_of,
            collected_at=envelope.meta.collected_at,
        )


def exportable[**P, T](
    spec: ExportSpec,
) -> Callable[[Callable[P, Envelope[T]]], Callable[P, Envelope[T] | Response]]:
    """Mark a route a screen reads as one that also answers as a workbook or a CSV."""

    def decorate(route: Callable[P, Envelope[T]]) -> Callable[P, Envelope[T] | Response]:
        if inspect.iscoroutinefunction(route):
            raise TypeError(f"{route.__name__} is async, and exportable wraps a plain function")
        signature = inspect.signature(route)
        if EXPORT_PARAMETER in signature.parameters:
            raise TypeError(f"{route.__name__} already has a parameter named {EXPORT_PARAMETER}")
        hints = get_type_hints(route, include_extras=True)
        parameters = [
            parameter.replace(annotation=hints.get(name, parameter.annotation))
            for name, parameter in signature.parameters.items()
        ]
        parameters.append(
            inspect.Parameter(
                EXPORT_PARAMETER,
                inspect.Parameter.KEYWORD_ONLY,
                default=Depends(ExportDependency(spec)),
                annotation=Exporter,
            )
        )

        @functools.wraps(route)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> Envelope[T] | Response:
            exporter = kwargs.pop(EXPORT_PARAMETER, None)
            envelope = route(*args, **kwargs)
            if isinstance(exporter, Exporter):
                return exporter.respond(envelope)
            return envelope

        wrapper.__signature__ = signature.replace(  # type: ignore[attr-defined]
            parameters=parameters,
            return_annotation=hints.get("return", signature.return_annotation),
        )
        return wrapper

    return decorate


def _describe(describe: Describe, view: View) -> str | None:
    if describe is None or isinstance(describe, str):
        return describe
    return describe(view)


def _coverage_words(coverage: CoverageOut) -> str:
    counted = f"{coverage.visible} of {coverage.total} {coverage.unit}"
    if coverage.chosen is not None:
        # FEAT-075: a choice is stated, not reported as part of the estate.
        return f"{counted}, counted against the account chosen"
    return counted + (", so this is part of the estate" if coverage.is_partial else "")


def _scope_words(scope: Scope) -> str:
    if scope.chosen is not None:
        return f"One account, chosen: {scope.chosen.account_id}"
    if scope.is_global:
        return "Every account in the organisation"
    names = sorted(account.account_id for account in scope.accounts)
    if not names:
        return "No accounts"
    shown = ", ".join(names[:NAMED_ACCOUNTS])
    more = f", and {len(names) - NAMED_ACCOUNTS} more" if len(names) > NAMED_ACCOUNTS else ""
    noun = "account" if len(names) == 1 else "accounts"
    return f"{len(names)} {noun}: {shown}{more}"


def _moment(value: datetime | None) -> str:
    if value is None:
        return "Not collected"
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")


def _failures(envelope: Envelope[Any]) -> list[tuple[str, str, str, str]]:
    """Every typed failure in the view, a row each, so a failed account is never a zero."""
    return [
        (collector_name(failure.collector), failure.cause, failure.scope_key, failure.remediation)
        for failure in envelope.meta.failures
    ]


def exported_path(path: str) -> str | None:
    """`path` as a schedule keeps it, when it names a route that answers as a file. FEAT-069.

    The path part must be one GET route carrying this module's dependency, and the query keeps
    every parameter but `format`, which each run sets. None for anything else, including a path
    with a host in it, so a schedule can only ever render one of this API's own routes.
    """
    split = urlsplit(path)
    if split.scheme or split.netloc or not split.path.startswith("/"):
        return None
    if not any(route.path_regex.match(split.path) for route in _exporting_routes()):
        return None
    kept = [
        (key, value)
        for key, value in parse_qsl(split.query, keep_blank_values=True)
        if key != "format"
    ]
    return split.path if not kept else f"{split.path}?{urlencode(kept)}"


@functools.cache
def _exporting_routes() -> tuple[APIRoute, ...]:
    """Every GET route that answers as a file, found as the export enumeration test finds them.

    Imported here rather than at the top because the route modules import this one.
    """
    import importlib
    import pkgutil

    import finops_api.routes as routes

    found: list[APIRoute] = []
    for module in pkgutil.iter_modules(routes.__path__):
        loaded = importlib.import_module(f"{routes.__name__}.{module.name}")
        router = getattr(loaded, "router", None)
        if router is None:
            continue
        found.extend(
            route
            for route in router.routes
            if isinstance(route, APIRoute)
            and "GET" in (route.methods or set())
            and any(isinstance(d.call, ExportDependency) for d in route.dependant.dependencies)
        )
    return tuple(found)
