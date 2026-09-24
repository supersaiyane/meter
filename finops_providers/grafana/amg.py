"""Amazon Managed Grafana as a `QuerySurface`.

Three things here are load bearing and none of them is the HTTP call.

**A region that could not be listed becomes a visible instance.** If
`ListWorkspaces` fails for one account and region, this returns a synthetic
instance marked unreachable rather than quietly returning a shorter list. A
silently smaller estate is the failure this whole product exists to prevent, and
it is worse here than elsewhere because nothing downstream can tell that a
region was ever meant to be there.

**A token is revoked in a `finally`.** The prototype minted service accounts and
a run that died half way left a credential in somebody's Grafana. Minting is a
loan, not an allocation.

**Nothing here writes.** Architectural constraint 6 makes v1 read only, so
`apply_control` answers `applied` false naming the reason. That is the normal
answer the port documents for a surface that cannot do what was asked, and it is
not an error.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from finops_core.domain.query import (
    ControlOutcome,
    ControlRequest,
    QueryDefinition,
    QueryOrigin,
    SurfaceInstance,
    SurfaceKind,
)
from finops_core.errors import AccessDenied, CollectionError, SchemaDrift
from finops_core.ports.query import QueryParser
from finops_providers.aws.client import translate as translate_aws
from finops_providers.grafana.client import GrafanaClient, Workspace

COLLECTOR = "query_audit"

#: The role a minted service account is given. Viewer, because this adapter
#: reads. A token that can edit is a token that can be abused if it leaks, and
#: it would also make constraint 6 depend on our own restraint.
SERVICE_ACCOUNT_ROLE = "VIEWER"


@dataclass(frozen=True)
class Scope:
    """One account and region pair to look for workspaces in."""

    account_id: str
    region: str

    @property
    def key(self) -> str:
        return f"aws:{self.account_id}:{self.region}"


ClientFactory = Callable[[str, Scope], Any]
TransportFactory = Callable[[Workspace, str], Any] | None


def _interval_of(rule: Mapping[str, Any], parser: QueryParser) -> int:
    """An alert rule's evaluation interval, in seconds.

    `intervalSeconds` is already a number. `refresh_seconds` parses Grafana's
    duration strings like `10s`, and handing it an integer returns zero, which
    would report an alert that runs every minute as one that never runs. An
    alert is usually the largest term in a cost figure, so that error is not a
    rounding one.
    """
    seconds = rule.get("intervalSeconds")
    if isinstance(seconds, int | float):
        return int(seconds)
    return parser.refresh_seconds(rule.get("interval"))


class AmgQuerySurface:
    """`QuerySurface` over Amazon Managed Grafana, read only."""

    def __init__(
        self,
        *,
        scopes: Sequence[Scope],
        client_factory: ClientFactory,
        parser: QueryParser,
        now: Callable[[], datetime],
        http_timeout_seconds: float,
        token_ttl_seconds: int,
        secret_names: Mapping[str, str] | None = None,
        transport_factory: TransportFactory = None,
    ) -> None:
        self._scopes = tuple(scopes)
        self._client = client_factory
        # Supplied by the collector. The adapter fetches, this interprets, and
        # the import contract keeps those two facts apart.
        self._parser = parser
        self._now = now
        self._timeout = http_timeout_seconds
        self._token_ttl = token_ttl_seconds
        # A workspace id to a Secrets Manager secret name. Configured when a
        # workspace will not accept a minted service account, which is the case
        # for a workspace whose authentication is managed elsewhere.
        self._secret_names = dict(secret_names or {})
        self._transport_factory = transport_factory
        self._scope_of: dict[str, Scope] = {}
        self._endpoint_of: dict[str, str] = {}

    # -- discovery ---------------------------------------------------------

    def discover(self) -> Iterable[SurfaceInstance]:
        found: list[SurfaceInstance] = []
        failures: list[CollectionError] = []

        for scope in self._scopes:
            try:
                found.extend(self._workspaces_in(scope))
            except CollectionError as failure:
                failures.append(failure)
                # Named, not dropped. Downstream can then report a gap rather
                # than a smaller estate.
                found.append(
                    SurfaceInstance(
                        surface_id=scope.key,
                        name=f"{scope.account_id} in {scope.region}",
                        kind=SurfaceKind.MANAGED_GRAFANA,
                        location=scope.region,
                        reachable=False,
                        unreachable_cause=type(failure).__name__,
                    )
                )

        if failures and len(failures) == len(self._scopes):
            # Nothing at all could be enumerated, which the port distinguishes
            # from one instance being unreadable.
            raise failures[0]
        return tuple(found)

    def _workspaces_in(self, scope: Scope) -> Iterator[SurfaceInstance]:
        client = self._client("grafana", scope)
        token: str | None = None
        while True:
            try:
                page = (
                    client.list_workspaces(nextToken=token) if token else client.list_workspaces()
                )
            except (ClientError, BotoCoreError) as failure:
                raise translate_aws(failure, scope_key=scope.key, collector=COLLECTOR) from failure

            for raw in page.get("workspaces", ()):
                yield self._instance_from(raw, scope)

            token = page.get("nextToken")
            if not token:
                return

    def _instance_from(self, raw: Mapping[str, Any], scope: Scope) -> SurfaceInstance:
        workspace_id = raw.get("id")
        endpoint = raw.get("endpoint")
        if not workspace_id or not endpoint:
            raise SchemaDrift(
                scope_key=scope.key,
                collector=COLLECTOR,
                detail="a workspace arrived with no id or no endpoint",
            )
        self._scope_of[str(workspace_id)] = scope
        self._endpoint_of[str(workspace_id)] = str(endpoint)
        status = str(raw.get("status", "UNKNOWN"))
        # A workspace that is not ACTIVE is reachable in the API sense and not
        # readable in the useful sense, so it is listed and marked.
        return SurfaceInstance(
            surface_id=str(workspace_id),
            name=str(raw.get("name", workspace_id)),
            kind=SurfaceKind.MANAGED_GRAFANA,
            location=str(endpoint),
            reachable=status == "ACTIVE",
            unreachable_cause=None if status == "ACTIVE" else "NotOptedIn",
        )

    # -- the token loan ----------------------------------------------------

    @contextmanager
    def _token_for(self, instance: SurfaceInstance) -> Iterator[str]:
        """Mint a token, or read a configured one, and always give it back."""
        secret = self._secret_names.get(instance.surface_id)
        if secret is not None:
            yield self._secret_token(instance, secret)
            return

        scope = self._scope_of.get(instance.surface_id)
        if scope is None:
            raise AccessDenied(
                scope_key=instance.scope_key,
                collector=COLLECTOR,
                detail="this instance was not discovered by this surface",
            )
        client = self._client("grafana", scope)
        account_id: str | None = None
        token_id: str | None = None
        try:
            account_id = self._create_service_account(client, instance)
            token, token_id = self._create_token(client, instance, account_id)
            yield token
        except (ClientError, BotoCoreError) as failure:
            raise translate_aws(
                failure, scope_key=instance.scope_key, collector=COLLECTOR
            ) from failure
        finally:
            # In a finally, and each step guarded, because a failure revoking
            # the token must not stop us deleting the account that holds it.
            self._revoke(client, instance, account_id, token_id)

    def _create_service_account(self, client: Any, instance: SurfaceInstance) -> str:
        created = client.create_workspace_service_account(
            workspaceId=instance.surface_id,
            grafanaRole=SERVICE_ACCOUNT_ROLE,
            name=f"meter-audit-{int(self._now().timestamp())}",
        )
        return str(created["id"])

    def _create_token(
        self, client: Any, instance: SurfaceInstance, account_id: str
    ) -> tuple[str, str]:
        created = client.create_workspace_service_account_token(
            workspaceId=instance.surface_id,
            serviceAccountId=account_id,
            name=f"meter-audit-{int(self._now().timestamp())}",
            secondsToLive=self._token_ttl,
        )
        token = created["serviceAccountToken"]
        return str(token["key"]), str(token["id"])

    def _revoke(
        self,
        client: Any,
        instance: SurfaceInstance,
        account_id: str | None,
        token_id: str | None,
    ) -> None:
        # Suppressed on purpose, and only here. Deleting the account below
        # removes the token with it, and raising from cleanup would replace a
        # real failure with a tidying one.
        if account_id is not None and token_id is not None:
            with suppress(ClientError, BotoCoreError):
                client.delete_workspace_service_account_token(
                    workspaceId=instance.surface_id,
                    serviceAccountId=account_id,
                    tokenId=token_id,
                )
        if account_id is not None:
            with suppress(ClientError, BotoCoreError):
                client.delete_workspace_service_account(
                    workspaceId=instance.surface_id, serviceAccountId=account_id
                )

    def _secret_token(self, instance: SurfaceInstance, secret: str) -> str:
        scope = self._scope_of.get(instance.surface_id) or self._scopes[0]
        client = self._client("secretsmanager", scope)
        try:
            response = client.get_secret_value(SecretId=secret)
        except (ClientError, BotoCoreError) as failure:
            raise translate_aws(
                failure, scope_key=instance.scope_key, collector=COLLECTOR
            ) from failure
        return str(response["SecretString"])

    # -- reading -----------------------------------------------------------

    def list_queries(self, instance: SurfaceInstance) -> Iterable[QueryDefinition]:
        if not instance.reachable:
            raise AccessDenied(
                scope_key=instance.scope_key,
                collector=COLLECTOR,
                detail=f"discovered unreachable: {instance.unreachable_cause}",
            )
        workspace = Workspace(
            id=instance.surface_id,
            name=instance.name,
            endpoint=self._endpoint_of.get(instance.surface_id, instance.location),
        )
        collected_at = self._now()
        with self._token_for(instance) as token:
            client = (
                self._transport_factory(workspace, token)
                if self._transport_factory is not None
                else GrafanaClient(workspace, token, self._timeout)
            )
            try:
                return tuple(self._definitions(client, instance, collected_at))
            finally:
                client.close()

    def _definitions(
        self, client: Any, instance: SurfaceInstance, collected_at: datetime
    ) -> Iterator[QueryDefinition]:
        scope = self._scope_of.get(instance.surface_id)
        region = scope.region if scope else None
        account_id = scope.account_id if scope else ""
        for summary in client.search_dashboards():
            uid = str(summary.get("uid", ""))
            if not uid:
                continue
            body = client.dashboard(uid)
            dashboard = body.get("dashboard", body)
            title = str(dashboard.get("title", uid))
            refresh = self._parser.refresh_seconds(dashboard.get("refresh"))
            window = self._parser.relative_range_seconds((dashboard.get("time") or {}).get("from"))
            for panel in self._parser.iter_panels(dashboard.get("panels")):
                yield from self._from_panel(
                    panel, instance, uid, title, refresh, window, region, account_id, collected_at
                )
        for rule in client.alert_rules():
            yield from self._from_alert(rule, instance, region, account_id, collected_at)

    def _from_panel(
        self,
        panel: Mapping[str, Any],
        instance: SurfaceInstance,
        uid: str,
        title: str,
        refresh: int,
        window: int | None,
        region: str | None,
        account_id: str,
        collected_at: datetime,
    ) -> Iterator[QueryDefinition]:
        element = str(panel.get("title", ""))
        for target in panel.get("targets") or ():
            found = self._parser.classify(target, panel.get("datasource"))
            if found.engine == "unknown":
                continue
            ref_id = str(target.get("refId", ""))
            yield QueryDefinition(
                as_of=collected_at,
                collected_at=collected_at,
                surface_id=instance.surface_id,
                fingerprint=self._parser.fingerprint(
                    account_id=account_id,
                    workspace_name=instance.name,
                    dashboard_uid=uid,
                    panel=element,
                    ref_id=ref_id,
                    query=found.query,
                ),
                origin=QueryOrigin.PANEL,
                engine=found.engine,
                query=found.query,
                container=title,
                container_id=uid,
                element=element,
                ref_id=ref_id,
                refresh_seconds=refresh,
                window_seconds=window,
                targets=found.log_groups,
                region=found.region or region,
            )

    def _from_alert(
        self,
        rule: Mapping[str, Any],
        instance: SurfaceInstance,
        region: str | None,
        account_id: str,
        collected_at: datetime,
    ) -> Iterator[QueryDefinition]:
        title = str(rule.get("title", ""))
        interval = _interval_of(rule, self._parser)
        for item in rule.get("data") or ():
            model = item.get("model") or {}
            found = self._parser.classify(model, model.get("datasource"))
            if found.engine == "unknown":
                continue
            ref_id = str(item.get("refId", ""))
            yield QueryDefinition(
                as_of=collected_at,
                collected_at=collected_at,
                surface_id=instance.surface_id,
                fingerprint=self._parser.fingerprint(
                    account_id=account_id,
                    workspace_name=instance.name,
                    dashboard_uid=str(rule.get("uid", "")),
                    panel=title,
                    ref_id=ref_id,
                    query=found.query,
                ),
                # An alert runs on its interval whether anybody is watching or
                # not, which is usually two orders of magnitude more runs.
                origin=QueryOrigin.ALERT,
                engine=found.engine,
                query=found.query,
                container=str(rule.get("ruleGroup", "")),
                container_id=str(rule.get("uid", "")),
                element=title,
                ref_id=ref_id,
                refresh_seconds=interval,
                window_seconds=self._parser.relative_range_seconds(model.get("timeRange")),
                targets=found.log_groups,
                region=found.region or region,
            )

    # -- writing, which v1 does not do -------------------------------------

    def apply_control(self, instance: SurfaceInstance, request: ControlRequest) -> ControlOutcome:
        """Always `applied` false. Architectural constraint 6 makes v1 read only.

        A normal answer rather than an error, so a caller tries a different
        control instead of abandoning the run. TASK-P2-017 and TASK-P2-019 are
        where a write arrives, behind the write level flag.
        """
        return ControlOutcome(
            surface_id=instance.surface_id,
            fingerprint=request.fingerprint,
            requested=request.action,
            applied=False,
            detail="v1 is read only, per architectural constraint 6",
        )
