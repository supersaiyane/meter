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
  /**
   * What is being counted, plural. The route knows and the shell was guessing:
   * every screen said `accounts` and the query screens count workspaces.
   */
  readonly unit: string;
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
  /** Null when the pair has never once succeeded. There is no last good moment. */
  readonly as_of: string | null;
  readonly cadence_seconds: number | null;
  /** Null for the same reason. A zero would read as collected this instant. */
  readonly age_seconds: number | null;
  /** `current`, `stale` or `never_collected`. Never having worked is not stale. */
  readonly state: string;
  /** The typed cause of the last attempt, when it failed. */
  readonly cause: string | null;
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

/**
 * What one query cost on one day. ISS-172.
 *
 * Provenance is on the point, not the series: a run that saw evidence and one
 * that did not produce different grades of number, and a line drawn through
 * both without saying so claims a confidence only part of it has.
 */
export interface ApiCostPoint {
  readonly run_date: string;
  readonly cost_month_usd: string;
  readonly provenance: string;
}

export interface ApiQueryFinding {
  readonly finding_id: string;
  readonly dashboard_uid: string | null;
  readonly dashboard_title: string | null;
  readonly panel_title: string | null;
  readonly folder_uid: string | null;
  readonly engine: string;
  readonly origin: string;
  readonly refresh_seconds: number | null;
  readonly window_seconds: number;
  /** A decimal string, never a float. Compared as a number only to sort. */
  readonly runs_per_day: string;
  readonly scan_bytes_per_run: number | null;
  readonly monthly_cost: string;
  /** measured or modelled. Never absent. */
  readonly provenance: string;
  /** Null on a modelled row, a count on a measured one. Never both ways. */
  readonly measured_runs: number | null;
  /** CRITICAL, HIGH, MEDIUM or LOW. A word, not a number, and from the money. */
  readonly severity: string;
  /** Which group this row is filed under, so one finding names its systemic cause. */
  readonly cause: string;
  /**
   * Null when nothing could attribute the query. The API does not send the
   * word "unattributed": an absence is an absence, and what it reads as is
   * this application's decision.
   */
  readonly owner: string | null;
  readonly owner_source: string | null;
  /** Prose explaining what drives the cost. Ported from the prototype. */
  readonly why: string;
  readonly as_of: string;
  readonly collected_at: string;
  /** Cost per audited day, oldest first, at most thirty days.
   *
   *  Optional because it genuinely is. An API that predates ISS-172 does not
   *  send it, and constraint 12 says an old API and a new interface coexist
   *  during a rolling deploy, so the screen has to read an absence rather than
   *  assume the field. One point is not a trend and is not drawn as one. */
  readonly history?: readonly ApiCostPoint[];
}

export interface ApiRemediation {
  readonly finding_id: string;
  readonly applied: boolean;
  /** True when the write did not take and was put back. The estate is unchanged. */
  readonly reverted: boolean;
  /** Why, when it did not apply. A refusal is a normal answer and carries a reason. */
  readonly detail: string;
  readonly change_id: string | null;
}

export interface ApiQueryGroup {
  readonly cause: string;
  /** A sentence a reader acts on. The code is what groups; this is what is read. */
  readonly label: string;
  readonly findings: number;
  readonly monthly_cost: string;
  /** From the summed money, so a group of LOW rows totalling a CRITICAL figure says so. */
  readonly severity: string;
  readonly as_of: string;
  readonly collected_at: string;
}

export interface ApiQueryFindingDetail extends ApiQueryFinding {
  /** The query as written. Shown whole, never summarised. */
  readonly query_text: string;
  /** What it runs against: log groups, a namespace. */
  readonly targets: readonly string[];
  readonly region: string | null;
  readonly last_editor: string | null;
  /** The published price, so the arithmetic has no constant hidden in the UI. */
  readonly rate_usd_per_gib: string;
  /** FEAT-018. Null until a calibration is published, and then never invented. */
  readonly accuracy_percent: number | null;
  /** The change still applied, if any. Null means there is nothing to undo. */
  readonly applied_change_id: string | null;
}

/**
 * One Logs Insights query that ran and belongs to no panel and no alert rule.
 *
 * There is no provenance field, and its absence is the claim. An ad hoc query
 * exists only in the evidence, so there is nothing to model it from and every
 * figure here is measured.
 */
export interface ApiAdhocQuery {
  readonly adhoc_id: string;
  readonly account_id: string;
  readonly region_id: string;
  /** As it ran, whole. A person has to recognise their own query in it. */
  readonly query_text: string;
  readonly runs: number;
  readonly scan_bytes: number;
  readonly cost_usd: string;
  /** Null when CloudTrail did not name the caller. Reported, never dropped. */
  readonly principal: string | null;
  readonly as_of: string;
  readonly collected_at: string;
}

export interface ApiSurfaceInstance {
  readonly instance_id: string;
  readonly name: string;
  /** AMG, SELF_HOSTED or CLOUD. A closed set, checked in the database. */
  readonly kind: string;
  readonly endpoint: string;
  /** Both null for an instance that belongs to no cloud account. */
  readonly account_id: string | null;
  readonly region_id: string | null;
  readonly reachable: boolean;
  /** One of the typed causes, by name. Required when reachable is false. */
  readonly unreachable_reason: string | null;
  /** Null means the instance enforces no floor at all, which is not zero. */
  readonly refresh_floor_seconds: number | null;
  /**
   * Null when the instance could not be read. Null is not zero: an instance
   * Meter cannot reach has an unknown number of queries, and rendering that as
   * zero is what makes an estate look smaller than it is. A workspace that was
   * read and holds nothing is a zero, and the two must not look alike.
   */
  readonly query_count: number | null;
  readonly as_of: string;
  readonly collected_at: string;
}

export interface ApiEnforcementAction {
  readonly action_id: string;
  /** ALERT, THROTTLE or DENY. */
  readonly action: string;
  readonly principal: string;
  readonly applied_at: string;
  /** Required for THROTTLE and DENY, null for ALERT. */
  readonly expires_at: string | null;
  readonly reason_finding_id: string;
  /**
   * Decided by the API, per architectural constraint 8. The frontend renders
   * what it is told: a second implementation of an authorization rule is how an
   * authorization bug is created.
   */
  readonly revocable: boolean;
}

/**
 * What a billing period cost, and whether that period is finished.
 *
 * `is_open` arrives from the API rather than being worked out here from a
 * date. The side that read the export knows where today sits relative to the
 * period's exclusive end, and a second copy of that calendar rule is one that
 * is eventually wrong in one of the two places.
 */
export interface ApiCostTotal {
  readonly period: string;
  readonly is_open: boolean;
  /** Amortized cost. The primary measure everywhere, per the roadmap. */
  readonly effective_cost: string;
  /** What the invoice says. Shown only where that is the question. */
  readonly billed_cost: string;
  readonly line_items: number;
}

export interface ApiCostSummary {
  readonly current: ApiCostTotal;
  /**
   * Null when no earlier period was collected. Not a period that cost nothing:
   * one is an absence and the other is a claim, and they must not render alike.
   */
  readonly previous: ApiCostTotal | null;
  /** Null for the same reason. Never render this as zero. */
  readonly change: string | null;
}

export interface ApiCostSlice {
  /**
   * `unallocated` where the row carries no value for the grouping. It is never
   * dropped and never folded into a total, because a view that quietly loses
   * what it cannot attribute reports a smaller estate than exists.
   */
  readonly name: string;
  readonly effective_cost: string;
  readonly billed_cost: string;
  readonly line_items: number;
}

export interface ApiCostDay {
  readonly day: string;
  readonly effective_cost: string;
}
