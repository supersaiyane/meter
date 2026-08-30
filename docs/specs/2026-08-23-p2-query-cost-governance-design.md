# P2 Query Cost Governance: design specification

Date: 2026-08-23
Status: In review
Sub project: P2
Depends on: P0
Blocks: nothing. FEAT-019 extends it, P7 narrates it

## 1. Purpose

Stop the failure that started this project. A set of Grafana dashboards
pointed at CloudWatch Logs Insights, left on a one second auto refresh over a
seven day window, produced 100,000 USD in a week. Nothing detected it, nothing
prevented it, and nobody owned it.

P2 detects that class of problem, attributes it to a person, models what it
costs, prevents it at the source, and stops it in minutes when prevention has
been bypassed.

**It deliberately does not** analyse general cloud cost. That is P1. P2 is
about the cost of asking questions, which is a category most FinOps tools do
not cover at all.

A working prototype exists: `sample_lambda.py`, 2,740 lines, covering roughly
70 percent of the detection and modelling. It is ported rather than rewritten,
under golden file tests, and decomposed against the 800 line ceiling.

## 2. Definition of done

Four things, observable.

1. A dashboard saved with a policy violating configuration is **blocked at
   save**, not reported afterwards.
2. A runaway query pattern that reaches production is **detected and acted on
   within 15 minutes**, where acting means at minimum a page with the principal
   named.
3. Every expensive query has a **named human owner**, not just a role ARN.
4. The modelled cost has a **published accuracy percentage**, back tested
   against the actual bill.

If the first three hold and the fourth does not, P2 is a detector. All four and
it is a control.

## 3. Out of scope

- General cloud cost analysis. P1.
- QuickSight, Athena, Redshift and OpenSearch. FEAT-019, after the Grafana
  adapter is proven.
- Agent based collection for Grafana instances unreachable from the hub VPC.
  See section 12.
- Any narration or natural language explanation. P7.

## 4. Module structure

```
finops_core/ports/query_surface.py     the port. No Grafana in the name
finops_providers/grafana/
    surface.py          GrafanaQuerySurface, implements QuerySurface
    connections/
        amg.py          discovery via grafana:ListWorkspaces, temp token
        selfhosted.py   inventory driven, credential from Secrets Manager
        cloud.py        API key per stack, outbound to grafana.net
    client.py           the Grafana HTTP API. One implementation, three callers
    classify.py         query engine classification
finops_ingest/collectors/
    query_audit.py      the 6 hourly survey
    query_measured.py   CloudTrail and DescribeQueries overlay
finops_query/                           the domain of this sub project
    cost_model.py       modelled cost per query
    calibration.py      back test against CUR usage types
    ownership.py        folder, editor and principal resolution
    policy.py           what counts as a violation
    control.py          alert, throttle and deny
    remediation.py      workspace floor, panel rewrite, undo
```

`finops_query` sits at the same layer as `finops_ingest`. It imports
`finops_core` and nothing above it. The import linter contract is extended in
the first task.

The port is called `QuerySurface`, not `GrafanaSource`. Naming it after the
first implementation is how an abstraction ends up shaped like one vendor.

### 4.1 One port, three connection strategies

The three Grafana variants share about 90 percent of their logic, because it is
the same HTTP API. They differ in **how you find them** and **how you
authenticate**. So the strategy sits below the adapter, not beside it.

| Strategy | Discovery | Authentication |
| --- | --- | --- |
| `AmgConnection` | `grafana:ListWorkspaces` per account per region | Temporary service account token, minted and revoked per run |
| `SelfHostedConnection` | **None. There is no API.** Reads the `grafana_instance` table | Service account token, referenced in Secrets Manager |
| `CloudConnection` | Reads `grafana_instance`, one row per Grafana Cloud stack | API key, referenced in Secrets Manager |

FEAT-019 later adds `QuickSightQuerySurface` as a sibling of
`GrafanaQuerySurface`, not as a fourth connection strategy.

## 5. Data model

Extends `docs/07-DATA-MODEL.md`, same conventions and the same six principles.

```sql
CREATE TABLE grafana_instance (
    instance_id     UUID PRIMARY KEY,
    tenant_id       UUID        NOT NULL REFERENCES tenant(tenant_id),
    kind            TEXT        NOT NULL,   -- AMG | SELF_HOSTED | CLOUD
    name            TEXT        NOT NULL,
    endpoint        TEXT        NOT NULL,
    account_id      TEXT,                   -- AMG only
    region_id       TEXT,                   -- AMG only
    credential_ref  TEXT,                   -- Secrets Manager name, never a value
    reachable       BOOLEAN     NOT NULL DEFAULT true,
    unreachable_reason TEXT,
    as_of           TIMESTAMPTZ NOT NULL,
    collected_at    TIMESTAMPTZ NOT NULL,
    CONSTRAINT uq_grafana_instance__tenant_endpoint UNIQUE (tenant_id, endpoint),
    CONSTRAINT ck_grafana_instance__kind_valid
        CHECK (kind IN ('AMG', 'SELF_HOSTED', 'CLOUD')),
    -- AMG rows are discovered and must carry their location. The others are
    -- entered by a person and must not pretend to have one.
    CONSTRAINT ck_grafana_instance__amg_located
        CHECK ((kind = 'AMG') = (account_id IS NOT NULL AND region_id IS NOT NULL)),
    -- Added at TASK-P2-009. The same invariant SurfaceInstance enforces in the
    -- domain: an unexplained absence is what makes an estate look smaller than
    -- it is, and the domain being careful is not a reason for the table not to
    -- be.
    CONSTRAINT ck_grafana_instance__unreachable_has_reason
        CHECK (reachable OR unreachable_reason IS NOT NULL)
);

CREATE TABLE query_definition (
    query_id        UUID PRIMARY KEY,
    tenant_id       UUID        NOT NULL REFERENCES tenant(tenant_id),
    instance_id     UUID        NOT NULL REFERENCES grafana_instance(instance_id),
    origin          TEXT        NOT NULL,   -- PANEL | ALERT_RULE
    dashboard_uid   TEXT,
    dashboard_title TEXT,
    folder_uid      TEXT,
    panel_id        TEXT,
    ref_id          TEXT,
    engine          TEXT        NOT NULL,
    query_text      TEXT        NOT NULL,
    fingerprint     TEXT        NOT NULL,   -- normalised, template vars removed
    target          JSONB       NOT NULL,   -- log groups, namespace, datasource
    refresh_seconds INTEGER,                -- null for an alert rule
    range_seconds   INTEGER     NOT NULL,
    last_editor     TEXT,
    as_of           TIMESTAMPTZ NOT NULL,
    collected_at    TIMESTAMPTZ NOT NULL,
    CONSTRAINT uq_query_definition__fingerprint
        UNIQUE (tenant_id, instance_id, fingerprint),
    CONSTRAINT ck_query_definition__origin_valid
        CHECK (origin IN ('PANEL', 'ALERT_RULE')),
    CONSTRAINT ck_query_definition__engine_valid
        CHECK (engine IN ('LOGS_INSIGHTS', 'METRIC_SEARCH', 'METRIC_INSIGHTS',
                          'PROMQL', 'OTHER')),
    -- A panel has a refresh interval. An alert rule runs on its own schedule
    -- and must not borrow one.
    CONSTRAINT ck_query_definition__panel_has_refresh
        CHECK ((origin = 'ALERT_RULE') OR (refresh_seconds IS NOT NULL))
);

CREATE TABLE query_finding (
    finding_id      UUID PRIMARY KEY,
    tenant_id       UUID        NOT NULL REFERENCES tenant(tenant_id),
    query_id        UUID        NOT NULL REFERENCES query_definition(query_id),
    run_date        DATE        NOT NULL,
    runs_per_day    NUMERIC(12,2) NOT NULL,
    scan_bytes_per_run BIGINT,
    metrics_per_call INTEGER,
    cost_month_usd  NUMERIC(20,10) NOT NULL,
    provenance      TEXT        NOT NULL,   -- measured | modelled
    measured_runs   INTEGER,
    severity        TEXT        NOT NULL,   -- derived, ADR-0016
    owner_email     TEXT,
    owner_source    TEXT,                   -- FOLDER_MAP | LAST_EDITOR | CLOUDTRAIL
    why             TEXT        NOT NULL,   -- what drives the cost, in words
    as_of           TIMESTAMPTZ NOT NULL,
    collected_at    TIMESTAMPTZ NOT NULL,
    CONSTRAINT uq_query_finding__query_day UNIQUE (tenant_id, query_id, run_date),
    CONSTRAINT ck_query_finding__provenance_valid
        CHECK (provenance IN ('measured', 'modelled')),
    -- A measured row must say how many runs it measured. A modelled row must
    -- not claim to have measured any.
    CONSTRAINT ck_query_finding__measured_has_runs
        CHECK ((provenance = 'modelled' AND measured_runs IS NULL)
               OR (provenance = 'measured' AND measured_runs IS NOT NULL))
);
CREATE INDEX ix_query_finding__cost ON query_finding (tenant_id, run_date, cost_month_usd DESC);

CREATE TABLE folder_team_map (
    tenant_id       UUID NOT NULL REFERENCES tenant(tenant_id),
    instance_id     UUID NOT NULL REFERENCES grafana_instance(instance_id),
    folder_uid      TEXT NOT NULL,
    owner_email     TEXT NOT NULL,
    team            TEXT,
    updated_by      TEXT NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, instance_id, folder_uid)
);

CREATE TABLE enforcement_action (
    action_id       UUID PRIMARY KEY,
    tenant_id       UUID        NOT NULL REFERENCES tenant(tenant_id),
    level           TEXT        NOT NULL,   -- ALERT | THROTTLE | DENY
    principal_arn   TEXT        NOT NULL,
    trigger_reason  TEXT        NOT NULL,
    observed_rate   NUMERIC(12,2) NOT NULL,
    threshold       NUMERIC(12,2) NOT NULL,
    applied_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at      TIMESTAMPTZ,            -- required for THROTTLE and DENY
    removed_at      TIMESTAMPTZ,
    removed_by      TEXT,
    CONSTRAINT ck_enforcement_action__level_valid
        CHECK (level IN ('ALERT', 'THROTTLE', 'DENY')),
    -- The rule that stops a deny becoming permanent. A DENY with no expiry
    -- cannot be written at all.
    CONSTRAINT ck_enforcement_action__restrictive_expires
        CHECK (level = 'ALERT' OR expires_at IS NOT NULL)
);
CREATE INDEX ix_enforcement_action__active
    ON enforcement_action (tenant_id, expires_at) WHERE removed_at IS NULL;

CREATE TABLE remediation_change (
    change_id       UUID PRIMARY KEY,
    tenant_id       UUID        NOT NULL REFERENCES tenant(tenant_id),
    query_id        UUID        REFERENCES query_definition(query_id),
    instance_id     UUID        NOT NULL REFERENCES grafana_instance(instance_id),
    kind            TEXT        NOT NULL,   -- WORKSPACE_FLOOR | PANEL_REWRITE
    before          JSONB       NOT NULL,   -- the undo
    after           JSONB       NOT NULL,
    applied_by      TEXT        NOT NULL,
    applied_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    reverted_at     TIMESTAMPTZ,
    reverted_by     TEXT,
    CONSTRAINT ck_remediation_change__kind_valid
        CHECK (kind IN ('WORKSPACE_FLOOR', 'PANEL_REWRITE'))
);
```

`before` is `NOT NULL` on every remediation change. A change Meter cannot undo
is a change Meter does not make.

`query_snapshot`, the daily history the prototype keeps as S3 files, is not a
separate table. `query_finding` is keyed on `run_date` and is the history, which
closes ISS-023.

## 6. Error taxonomy

The six types from P0 section 6, unchanged, plus the mappings specific to this
surface. No new types, because the taxonomy staying closed is what stops every
future failure becoming generic.

| Situation | Type | Rendered as |
| --- | --- | --- |
| Grafana token rejected | `AccessDenied` | Instance unhealthy, with the remediation |
| Self hosted instance not reachable from the hub VPC | `Unreachable` | **Instance listed, marked unreachable, excluded from totals with a visible note** |
| Grafana Cloud API rate limit | `Throttled` | Degraded, retried with backoff |
| Workspace exists with no dashboards | `NoData` | Zero, and this is the only case where zero is correct |
| Grafana API returns a dashboard shape we do not recognise | `SchemaDrift` | Failed, and an issue raised automatically |
| CloudWatch Logs Insights not enabled in a region | `NotOptedIn` | Not applicable |

The `Unreachable` row is the important one. An instance Meter cannot reach must
appear in the list marked as unreachable, and its queries must be excluded from
every total **with the exclusion stated**. Silently omitting it produces a
confident organization total that is wrong by an unknown amount.

## 7. Flow

Two flows at two cadences, and they are separate features because they answer
separate questions. ADR-0012.

### 7.1 The audit, every 6 hours

```
EventBridge Scheduler, 6 hourly
  -> dispatcher enumerates (tenant, instance, collector)
  -> worker per instance
       resolve connection strategy by instance.kind
       authenticate
       list dashboards, panels, alert rules
       classify engine, extract target, fingerprint
       upsert query_definition
       model cost from refresh x window x log group ingest rate
       overlay measured signal from CloudTrail and DescribeQueries
       resolve owner: folder map, then last editor, then CloudTrail principal
       derive severity from cost_month_usd, ADR-0016
       upsert query_finding for today
```

Six hours is right for a survey. It is wrong for a control, which is why the
control is a separate flow.

### 7.2 The control, event driven

```
CloudTrail StartQuery -> EventBridge rule -> control lambda
    count per principal per rolling hour
    if rate > threshold:
        always: write enforcement_action(ALERT), page, raise a ticket
        if level >= THROTTLE and grace elapsed: apply rate limit
        if level == DENY and grace elapsed: apply Budgets Action deny policy
    never act on a principal in the never-deny list
```

At the burn rate that started this project, a six hour survey would still allow
roughly 25,000 USD between sweeps. The control runs in seconds.

### 7.3 Prevention, at save time

Two mechanisms, and the first is worth more than everything else in this
document combined.

1. **Workspace `min_refresh_interval`.** One setting. Grafana enforces it
   itself, on every save, forever, with no code from us. Set it to 1 minute and
   most of the exposure is gone.
2. **A CI policy gate** for dashboards managed as code, rejecting a Logs
   Insights panel that combines a sub minute refresh with a window longer than
   24 hours.

## 8. Interface

### 8.1 Configuration, per tenant

Feature flags, ADR-0017. All default to the safe value.

| Flag | Default | Effect |
| --- | --- | --- |
| `query_governance` | true | Master switch for P2 |
| `query_control_level` | `alert` | `alert`, `throttle` or `deny` |
| `query_write_level` | `none` | `none`, `workspace_floor` or `full` |
| `query_surface_selfhosted` | false | Scan self hosted instances |
| `query_surface_cloud` | false | Scan Grafana Cloud stacks |

Thresholds, environment configured, not flags:

`METER_QUERY_CONTROL_RATE_PER_HOUR`, `METER_QUERY_CONTROL_GRACE_MINUTES`,
`METER_QUERY_DENY_TTL_MINUTES` (default 60),
`METER_QUERY_NEVER_DENY_ARNS`, `METER_QUERY_VIEWING_HOURS_PER_DAY`.

### 8.2 Routes

| Method and path | Purpose |
| --- | --- |
| `GET /api/v1/query/findings` | Ranked by cost, filterable by owner, engine, provenance |
| `GET /api/v1/query/findings/{id}` | One finding, its working, and its evidence |
| `GET /api/v1/query/instances` | Every Grafana instance and its reachability |
| `GET /api/v1/query/enforcement` | Active and historical enforcement actions |
| `POST /api/v1/query/enforcement/{id}/revoke` | Break glass. Remove a deny immediately |
| `GET /api/v1/query/accuracy` | The published calibration figure, FEAT-018 |
| `POST /api/v1/query/remediate/{id}` | Apply a remediation, subject to the write level |
| `POST /api/v1/query/remediate/{id}/undo` | Revert it |

MCP tools, per ADR-0009: `list_expensive_queries`, `get_dashboard_cost`,
`get_query_accuracy`.

## 9. User interface

Four screens.

1. **Findings.** Ranked by monthly cost. Columns: severity, dashboard, panel,
   refresh, window, runs per day, scan per run, cost, provenance, owner, why.
   The `why` column is prose explaining what drives the cost, ported from the
   prototype, and it is what makes a finding actionable rather than a number.
2. **Finding detail.** The full working: the query, the target, the formula,
   the data window, and the measured evidence where it exists. Publishing the
   arithmetic is what makes a modelled number arguable rather than magic.
3. **Instances.** Every Grafana instance, its kind, its reachability, and the
   count of queries found. **Unreachable instances appear here**, which is the
   screen that stops silent under counting.
4. **Enforcement.** What the control did, to whom, when it expires, and a
   revoke button. This screen is the reason `deny` is safe to enable.

Every screen carries the standard `meta` envelope: `as_of`, `collected_at`,
`scope_coverage`, `degraded`.

## 10. Infrastructure

| Component | Where |
| --- | --- |
| Audit collector | Existing Fargate worker, new collector |
| Control function | A Lambda, not Fargate. It must respond in seconds and sits idle between events |
| EventBridge rule | On CloudTrail `StartQuery` in every in scope account and region |
| Budgets Action | Per tenant, created only when `query_control_level` is `deny` |
| Secrets | One per self hosted instance and per Cloud stack |
| Network | Self hosted instances must be reachable from the hub VPC |

The member role gains: `grafana:ListWorkspaces`, `grafana:DescribeWorkspace`,
`grafana:CreateWorkspaceServiceAccount*`, `logs:DescribeQueries`,
`logs:DescribeLogGroups`, `cloudtrail:LookupEvents`. Write actions are added
only when a write level above `none` is enabled, and they are a separate
StackSet update so the read only posture remains the default.

## 11. Testing

| Layer | Approach |
| --- | --- |
| Cost model | **Golden file tests, ported first.** The prototype's model is the specification, and a port that changes a number silently is a regression nobody would notice |
| Classification | Fixture dashboards per engine, including malformed and template heavy panels |
| Connection strategies | Contract test parameterised over all three, against a fake Grafana |
| Control | Event fixtures at, below and above threshold |
| Remediation | Apply, verify, undo, verify the original is restored byte for byte |

Five tests that encode the rules this design exists to protect:

1. An unreachable instance appears in the list and its queries are **excluded
   from every total, with the exclusion stated**.
2. A `DENY` action **cannot be written without an expiry**. The database
   rejects it.
3. A principal on the never-deny list is **never** denied, at any rate.
4. A `PANEL_REWRITE` undo restores the original panel exactly.
5. A `modelled` finding cannot carry a measured run count, and a `measured` one
   cannot omit it.

## 12. Risks

| Risk | Impact | Mitigation | Tracker |
| --- | --- | --- | --- |
| Self hosted Grafana unreachable from the hub VPC | Partial coverage, silently if handled badly | Instance marked unreachable and excluded with a stated note. Agent based collection is a later sub project | ISS-090 |
| A Grafana Cloud API key now lives in Meter | New credential, new blast radius | Secrets Manager, rotation runbook, and a new row in threat model boundary 5 | ISS-091 |
| `deny` cuts off an engineer mid incident | A self inflicted second incident | Auto expiry at 60 minutes, a never-deny list, a revoke route, and a screen showing every active action | ISS-092 |
| Modelled cost is wrong before calibration | The product's core credibility | Visible caveat on every modelled figure until FEAT-018 publishes an accuracy number | ISS-093 |
| The prototype is 2,740 lines in one file | Unreviewable, untestable | Decomposed in the first task, cost model ported under golden file tests | ISS-026 |
| Grafana changes its dashboard JSON shape | Silent under reporting | `SchemaDrift` is loud by design, and an unrecognised panel raises rather than being skipped | ISS-094 |

## 13. Open questions

| Question | Blocks | Tracker |
| --- | --- | --- |
| Who owns the never-deny list, and what is on it | Enabling `deny` | ISS-095 |
| Are dashboards managed as code anywhere today | The value of the CI policy gate, FEAT-014 | ISS-096 |

Neither blocks starting. OPEN-04 is answered: all three surfaces are in scope.

## 14. Features delivered

| Feature | |
| --- | --- |
| FEAT-011 | Grafana workspace, dashboard and alert rule scanner |
| FEAT-012 | Query cost model |
| FEAT-013 | Measured overlay |
| FEAT-014 | Preventive controls |
| FEAT-015 | Kill switch |
| FEAT-016 | Owner attribution |
| FEAT-017 | Auto remediation |
| FEAT-018 | Cost model calibration |

FEAT-019, multi platform, is explicitly **not** delivered here. It becomes
reachable because the port is named `QuerySurface` rather than after Grafana.

## 15. Exit criteria

The seven universal criteria in `docs/01-ROADMAP.md`, plus:

**A policy violating dashboard is blocked at save, and a runaway query is
detected and acted on within 15 minutes.**

Plus one specific to this sub project, because P2 is the first thing in Meter
that acts rather than reports:

**A separate threat model pass covering the write paths and the deny path**,
appended to `docs/08-THREAT-MODEL.md`. P2 does not inherit P0's, because P0 had
no write path at all.
