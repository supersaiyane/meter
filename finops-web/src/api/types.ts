/**
 * The wire shapes, mirroring `finops_api/schemas.py`.
 *
 * Written out rather than inferred from a response, because a type inferred
 * from whatever arrived is a type that agrees with a broken response. These are
 * a claim about what the API promises, and a response that does not match it is
 * a failure worth surfacing rather than a shape to adapt to.
 *
 * Timestamps arrive as strings and stay strings until something needs a Date.
 * Parsing at the boundary and passing Dates around invites a component to do
 * arithmetic on a value it did not check.
 */

export interface ApiCoverage {
  readonly visible: number;
  readonly total: number;
  readonly is_partial: boolean;
}

export interface ApiFailure {
  readonly scope_key: string;
  readonly collector: string;
  /** One of the six causes. Never a free text message. */
  readonly cause: string;
  readonly remediation: string;
  readonly occurrences: number;
  readonly last_seen_at: string;
}

export interface ApiMeta {
  /** When the data was true at the source. Null when nothing has been collected. */
  readonly as_of: string | null;
  /** When Meter fetched it. Constraint 10: two timestamps, never one. */
  readonly collected_at: string | null;
  readonly scope_coverage: ApiCoverage;
  readonly degraded: boolean;
  readonly failures: readonly ApiFailure[];
}

export interface ApiEnvelope<T> {
  readonly data: T;
  readonly meta: ApiMeta;
}

export interface Me {
  readonly principal_id: string;
  readonly display_name: string;
  readonly tenant_id: string;
  readonly tiers: readonly string[];
  readonly is_global: boolean;
  readonly accounts_in_scope: number;
}

export interface Account {
  readonly provider: string;
  readonly account_id: string;
  readonly name: string;
  readonly status: string;
  readonly role_health: string;
  readonly role_health_checked_at: string | null;
  readonly role_health_error: string | null;
  readonly as_of: string;
  readonly collected_at: string;
}

export interface Run {
  readonly run_id: string;
  readonly collector: string;
  readonly scope_key: string;
  readonly status: string;
  readonly started_at: string;
  readonly finished_at: string | null;
  readonly items_written: number;
  /** One of the six causes, or null. Never a free text exception message. */
  readonly error_type: string | null;
  readonly error_detail: string | null;
}

export interface Freshness {
  readonly collector: string;
  readonly scope_key: string;
  readonly as_of: string;
  readonly cadence_seconds: number | null;
  readonly age_seconds: number;
  readonly is_stale: boolean;
}

export interface PlatformCost {
  readonly day: string;
  readonly module: string;
  readonly service: string;
  readonly amortized_cost: string;
  readonly as_of: string;
  readonly collected_at: string;
}

export interface ApiQueryFinding {
  readonly finding_id: string;
  readonly dashboard_uid: string;
  readonly dashboard_title: string;
  readonly panel_title: string;
  readonly refresh_seconds: number | null;
  readonly window_seconds: number | null;
  readonly runs_per_day: number;
  readonly bytes_scanned_per_run: number;
  /** A decimal string, never a float. Compared as a number only to sort. */
  readonly monthly_cost: string;
  /** measured, modelled or forecast. Never absent. */
  readonly provenance: string;
  /** 1 informational to 5 critical, derived from dollars per ADR-0016. */
  readonly severity: number;
  /** The literal string `unattributed` when no owner was resolved. */
  readonly owner: string;
  /** Prose explaining what drives the cost. Ported from the prototype. */
  readonly why: string;
}

export interface ApiQueryFindingDetail {
  readonly finding_id: string;
  readonly dashboard_title: string;
  readonly panel_title: string;
  /** The query as written. Shown whole, never summarised. */
  readonly query_text: string;
  /** What it runs against: a log group, a namespace. */
  readonly target: string;
  readonly engine: string;
  readonly refresh_seconds: number | null;
  readonly window_seconds: number;
  readonly runs_per_day: number;
  readonly bytes_scanned_per_run: number;
  /** The published price, so the arithmetic has no constant hidden in the UI. */
  readonly rate_usd_per_gib: string;
  readonly monthly_cost: string;
  readonly provenance: string;
  /** FEAT-018. Null until a calibration is published, and then never invented. */
  readonly accuracy_percent: number | null;
  /** FEAT-013 evidence. Null until the measured overlay exists. */
  readonly measured_runs_per_day: number | null;
  readonly measured_bytes_scanned_per_run: number | null;
}

export interface ApiSurfaceInstance {
  readonly surface_id: string;
  readonly name: string;
  /** managed_grafana, self_hosted_grafana or grafana_cloud. A closed set. */
  readonly kind: string;
  readonly location: string;
  readonly reachable: boolean;
  /** One of the six causes, by name. Required when reachable is false. */
  readonly unreachable_cause: string | null;
  /**
   * Null when the instance could not be read. Null is not zero: an instance
   * Meter cannot reach has an unknown number of queries, and rendering that as
   * zero is what makes an estate look smaller than it is.
   */
  readonly query_count: number | null;
}
