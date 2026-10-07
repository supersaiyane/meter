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
   * The account the reader chose, FEAT-075, when the view is narrowed to one. Coverage is then
   * counted against it. Absent from an envelope a stub or an older API wrote, and null otherwise.
   */
  readonly chosen?: string | null;
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

/**
 * What every query audited on one day cost each month, summed: the trend on Query cost. Every
 * query audited that day, so a dashboard deleted after a fix leaves its earlier days behind.
 */
export interface ApiQueryCostDay {
  readonly run_date: string;
  readonly cost_month_usd: string;
  readonly queries: number;
  /** Measured only when every query that day was measured. */
  readonly provenance: string;
  readonly as_of: string;
  readonly collected_at: string;
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

/**
 * One account, service and tag value in one billing period, `GET /cost/showback`. FEAT-045.
 *
 * The period, both timestamps and the coverage are on every row, because a showback file is
 * mailed on and pasted into a deck, and a row pasted out of it has to carry what it meant.
 */
export interface ApiShowbackRow {
  readonly billing_period: string;
  readonly account_id: string;
  readonly service_name: string;
  /** The value of the chosen tag key, `unallocated` where a charge carries none. */
  readonly tag_value: string;
  readonly effective_cost: string;
  readonly billed_cost: string;
  readonly line_items: number;
  readonly as_of: string;
  readonly collected_at: string;
  readonly accounts_in_file: number;
  readonly accounts_in_organization: number;
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

/** One day that did not look like the days before it. FEAT-023. */
export interface ApiCommitmentUse {
  readonly commitment_id: string;
  readonly commitment_type: string;
  /** QUEUED, ACTIVE or EXPIRED. An expired commitment is reported, not dropped. */
  readonly status: string;
  readonly term_start: string;
  readonly term_end: string;
  readonly committed: string;
  readonly used: string;
  /** Money already spent that bought nothing. */
  readonly wasted: string;
  /**
   * Null where nothing was committed in the window, which is a commitment that
   * has not started. Zero would say the whole commitment was wasted, so the
   * screen renders the two differently.
   *
   * There is deliberately no coverage field here. A dollar of covered spend
   * cannot be attributed to one of several overlapping plans, so a coverage
   * figure on a commitment would be a number nobody measured.
   */
  readonly utilization: string | null;
}

export interface ApiCommitmentCoverage {
  readonly commitment_type: string;
  readonly dimension: string;
  readonly dimension_value: string;
  readonly eligible_spend: string;
  readonly covered_spend: string;
  /**
   * Null where nothing was eligible. Zero says the estate is uncovered and
   * somebody should buy; null says there was nothing there to buy for.
   */
  readonly coverage: string | null;
}

/**
 * FEAT-055. A coverage gap as something somebody owns.
 *
 * `usage_floor_percent` is the number that decides whether buying the commitment was a mistake.
 * A commitment obligates its whole term whether or not the usage continues, so it beats on
 * demand only while usage stays above that fraction of today's. A screen showing the saving
 * without the floor would be recommending a multi year obligation while withholding the risk.
 */
export interface ApiCommitmentAction {
  readonly commitment_type: string;
  /** SERVICE or REGION. Never an account: coverage cannot be apportioned to one. */
  readonly dimension: string;
  readonly dimension_value: string;
  readonly window_start: string;
  readonly window_end: string;
  /** Measured, from the bill, beside the modelled figures below it. */
  readonly eligible_spend: string;
  readonly covered_spend: string;
  /** Modelled from a configured discount rather than from a quote. */
  readonly estimated_monthly_saving: string;
  readonly usage_floor_percent: string;
  readonly term_months: number;
  readonly confidence: string;
  readonly severity: string;
  readonly lifecycle: string;
  readonly owner: string | null;
  readonly rationale: string;
}

/**
 * One kind of commitment on one day, TASK-P8-013. Per kind and never per plan, because the
 * provider reports a day's Savings Plans use only as one total. A fraction is null on a day
 * with nothing to divide by, which says something different from zero.
 */
export interface ApiCommitmentDay {
  readonly commitment_type: string;
  readonly day: string;
  readonly committed: string;
  readonly used: string;
  readonly utilization: string | null;
  readonly eligible_spend: string;
  readonly covered_spend: string;
  readonly coverage: string | null;
  readonly as_of: string;
  readonly collected_at: string;
}

export interface ApiCommitments {
  readonly window_start: string;
  readonly window_end: string;
  readonly commitments: readonly ApiCommitmentUse[];
  readonly coverage: readonly ApiCommitmentCoverage[];
  /** The coverage above as things somebody owns, worst money first. */
  readonly actions: readonly ApiCommitmentAction[];
  readonly wasted_total: string;
}

/**
 * FEAT-060. What somebody said this should cost, and whether it is on course.
 *
 * `status` is computed by the server, never by the screen, so the interface and the API cannot
 * disagree about whether something is over. UNKNOWN is not a fourth colour on a traffic light:
 * it is the answer when the period has not started, when no spend was collected, or when the
 * budget's scope is one this product cannot reproduce, and it exists so none of those renders
 * as green.
 */
export interface ApiBudget {
  readonly budget_id: string;
  readonly name: string;
  /** ACCOUNT, SERVICE, ALL or UNSUPPORTED. */
  readonly scope: string;
  readonly scope_value: string;
  readonly limit: string;
  readonly currency: string;
  readonly period_start: string;
  readonly period_end: string;
  /** Measured, from the bill. Null is not zero, in either of the two ways it can be null. */
  readonly actual: string | null;
  readonly status: string;
  /** How far through the period today is, nought to one. The denominator of the pace rule. */
  readonly elapsed: string;
  readonly used: string | null;
}

export interface ApiBudgets {
  readonly period: string;
  readonly budgets: readonly ApiBudget[];
  /** Read, kept, and never matched to a number. Non zero has to be said out loud. */
  readonly unsupported: number;
}

export interface ApiCostAnomaly {
  readonly account_id: string;
  readonly service_name: string;
  readonly day: string;
  readonly observed: string;
  readonly baseline: string;
  readonly delta: string;
  /**
   * Null when the baseline had not moved. Every departure from an unmoving
   * baseline is infinitely many deviations, so this says nothing rather than
   * something false.
   */
  readonly deviations: string | null;
  readonly severity: string;
  /** The working, so a reader can disagree with the verdict. */
  readonly why: string;
}

export interface ApiCostAnomalies {
  readonly anomalies: readonly ApiCostAnomaly[];
  /**
   * An empty list means two opposite things. An estate with enough history and
   * nothing wrong is behaving. An estate with four days of history has not been
   * judged at all, and rendering both as "no anomalies" tells the second one a
   * reassuring lie.
   */
  readonly days_collected: number;
  readonly days_needed: number;
}

/* ---------------------------------------------------------------- P3, waste */

/**
 * One resource a sizing rule examined and declined to recommend. FEAT-062, ADR-0027.
 *
 * There is deliberately no saving and no severity here. A refusal has no money, ADR-0016 ranks
 * every finding by money, and a zero would read as the least valuable action rather than as the
 * absence of one.
 */
export interface ApiRefusal {
  readonly resource_id: string;
  readonly account_id: string;
  readonly region_id: string;
  /** Which rule declined, so a reader knows what question was asked. */
  readonly waste_class: string;
  /** The sentence that decided it, whole. A shortened reason is one nobody can argue with. */
  readonly reason: string;
  /**
   * What the judgement rests on. A refusal after four days is worth questioning and one after
   * ninety is worth relying on, and a reader cannot tell them apart without this.
   */
  readonly observation_days: number;
}

export interface ApiRefusals {
  readonly refusals: readonly ApiRefusal[];
  /** Distinct resources, not rows: one resource declined by two rules was looked at once. */
  readonly examined: number;
}

export interface ApiRecommendation {
  readonly recommendation_id: string;
  readonly account_id: string;
  readonly source: string;
  readonly waste_class: string;
  readonly resource_id: string;
  readonly region_id: string;
  /** Modelled, not measured. The screen labels it so. */
  readonly estimated_monthly_saving: string;
  readonly severity: string;
  /**
   * From the observation window, and deliberately not derived from the money.
   * A ten thousand dollar finding on three weeks of data is CRITICAL and LOW,
   * and a single blended score could not say so.
   */
  readonly confidence: string;
  readonly observation_days: number;
  readonly lifecycle: string;
  /** Null where nobody owns it, which ISS-021 says is how a finding dies. */
  readonly owner: string | null;
  readonly ticket_reference: string | null;
  readonly rationale: string;
  /**
   * FEAT-052. What applying this costs if it is wrong, from `finops_query.actions`.
   *
   * Four fields rather than one label, and none of them is confidence. A high confidence
   * resize still restarts the workload; a low confidence snapshot deletion is still
   * permanent. `is_no_regret` is computed on the server so a client cannot disagree with it.
   */
  readonly reversible: boolean;
  readonly disturbs_running_work: boolean;
  readonly is_no_regret: boolean;
  /** The sentence. A flag with no sentence behind it is one a reader cannot argue with. */
  readonly risk_why: string;
}

export interface ApiRecommendations {
  readonly recommendations: readonly ApiRecommendation[];
  /** How many carry no owner. Surfaced rather than left for somebody to count. */
  readonly unowned: number;
}

export interface ApiRecommendationEvent {
  readonly from_lifecycle: string | null;
  readonly to_lifecycle: string;
  readonly actor: string;
  readonly reason: string | null;
  readonly occurred_at: string;
}

export interface ApiRecommendationDetail {
  readonly recommendation: ApiRecommendation;
  readonly history: readonly ApiRecommendationEvent[];
}

export interface ApiRealizedSaving {
  readonly recommendation_id: string;
  readonly cost_before: string;
  readonly cost_after: string;
  /**
   * Null where the billing rows published no usage quantity. Unobserved, not
   * zero: a zero would say the workload went away.
   */
  readonly usage_before: string | null;
  readonly usage_after: string | null;
  readonly verdict: string;
  readonly why: string;
  readonly window_before_start: string;
  readonly window_after_end: string;
}

export interface ApiVerdictTotal {
  readonly count: number;
  readonly realized_monthly: string;
}

export interface ApiRealizedSavings {
  readonly savings: readonly ApiRealizedSaving[];
  /**
   * Grouped by verdict rather than totalled. A single realized total would be
   * added to the estimated total by the first person who saw them side by side.
   */
  readonly by_verdict: Readonly<Record<string, ApiVerdictTotal>>;
}

export interface ApiScoreComponent {
  readonly name: string;
  /** Null where this part could not be computed. Excluded, not nought. */
  readonly points: string | null;
  readonly weight: number;
  readonly why: string;
  readonly findings: readonly string[];
}

export interface ApiScore {
  readonly account_id: string;
  readonly total: number;
  /** What the total is out of, because a component may be excluded. */
  readonly available_weight: number;
  readonly why: string;
  readonly components: readonly ApiScoreComponent[];
  readonly as_of: string;
}

export interface ApiScores {
  readonly scores: readonly ApiScore[];
  /** Accounts nobody could assess. Different from accounts scoring badly. */
  readonly unscored: readonly string[];
}
/**
 * P4. The graph, and how much of it is real.
 *
 * `coverage` is on `ApiSubgraph` rather than fetched separately, which is the whole
 * point of the P4 specification's section 6 reaching this file: a screen cannot draw
 * the map without having been handed the list of slices the map is missing. A map that
 * renders without it draws an unreadable region as sparse, and sparse is
 * indistinguishable from well connected on a diagram.
 */
export interface ApiTopologyNode {
  readonly node_id: string;
  /** The ARN. A reader has to be able to find the thing in their own console. */
  readonly provider_id: string;
  readonly account_id: string;
  /** One of fourteen kinds, and OTHER for a type the adapter cannot name. */
  readonly node_kind: string;
  /** The provider's own word for it, because ten of the estate's types are OTHER. */
  readonly resource_type: string;
  /** Null means global rather than regional. Never a region nobody could read. */
  readonly region_id: string | null;
  /** Null means regional rather than zonal. Never an unknown zone. */
  readonly availability_zone: string | null;
  readonly name: string | null;
  readonly as_of: string;
  readonly collected_at: string;
}

export interface ApiTopologyEdge {
  readonly from_node_id: string;
  readonly to_node_id: string;
  readonly edge_kind: string;
  readonly is_cross_account: boolean;
  /** The API that supplied it, so a missing edge and a refused call read differently. */
  readonly source: string;
  /** True where the far end is not in this payload. Drawn as a boundary, not a line. */
  readonly leaves_the_graph: boolean;
}

export interface ApiSliceCoverage {
  readonly account_id: string;
  /** Null is the account's global slice, where the IAM roles live. */
  readonly region_id: string | null;
  /** COMPLETE, PARTIAL or UNREAD. Unread is not a synonym for partial. */
  readonly state: string;
  /** One of seven causes, null only when COMPLETE. Never free text. */
  readonly cause: string | null;
  readonly node_count: number;
  readonly edge_count: number;
  readonly as_of: string;
  readonly collected_at: string;
}

export interface ApiSubgraph {
  readonly root_id: string;
  readonly nodes: readonly ApiTopologyNode[];
  readonly edges: readonly ApiTopologyEdge[];
  /** Not optional and not a second request. See the comment above. */
  readonly coverage: readonly ApiSliceCoverage[];
  readonly depth_reached: number;
  readonly max_depth: number;
  /** Nodes inside the depth bound that did not fit. Non zero has to be said out loud. */
  readonly omitted_nodes: number;
  /** False only when the walk hit the ceiling, so the number above is a floor. */
  readonly omitted_is_exact: boolean;
  readonly max_nodes: number;
}

export interface ApiGraphCoverage {
  readonly incomplete: readonly ApiSliceCoverage[];
}

/**
 * FEAT-044. What a change to one resource can reach, or why we will not say.
 *
 * Both halves arrive on one payload and exactly one is populated. A refusal is an answer, not an
 * error: the graph having a hole in it is a fact about the estate rather than a fault in the
 * request, so a status code would make the screen render a failure and send a reader looking for
 * a broken service instead of for a permission.
 */
export interface ApiBlastPart {
  readonly name: string;
  readonly count: number;
  readonly why: string;
}

export interface ApiBlastRadius {
  /** CONTAINED, WIDE or CROSS_ACCOUNT. Null when refused. */
  readonly band: string | null;
  readonly parts: readonly ApiBlastPart[];
  readonly reach: number | null;
  readonly accounts: number | null;
  readonly boundary_edges: number | null;
  /** True where the walk reached its depth bound, so the reach is a floor for that reason too. */
  readonly depth_bound_reached: boolean;
  /** Always true. An infrastructure graph cannot see an application level dependency. */
  readonly is_lower_bound: boolean;
  /** The slices that stopped us, by name and state. Empty when a band is given. */
  readonly refused_because: readonly string[];
  readonly max_depth: number;
}

export interface ApiInventoryRoot {
  readonly node_id: string;
  readonly provider_id: string;
  readonly account_id: string;
  readonly node_kind: string;
  readonly resource_type: string;
  readonly region_id: string | null;
  readonly name: string | null;
}

export interface ApiInventoryRoots {
  readonly roots: readonly ApiInventoryRoot[];
}

/**
 * FEAT-056. A page of resources, and the denominator.
 *
 * `total` is the count of rows matching the filter that this reader may see, counted through
 * the same scope guard as the page. A count over everything beside a page of the readable rows
 * is the arithmetic that tells a narrowed reader how much they are not allowed to look at.
 */
/** One filter value and how many resources in the scope carry it. Null is counted, not dropped. */
export interface ApiFacetCount {
  readonly value: string | null;
  readonly resources: number;
}

export interface ApiResourceFilters {
  readonly account_id: readonly string[];
  /** Never an empty string. A null region is the global slice and the screen names it. */
  readonly region_id: readonly string[];
  readonly node_kind: readonly string[];
  /** The provider's own words. It has no enumeration, so the data is the only list. */
  readonly resource_type: readonly string[];
  /**
   * How many resources each region and each type holds, largest first, over the scope rather
   * than under the list's own filters. Absent from a payload made before the counts existed.
   */
  readonly region_counts?: readonly ApiFacetCount[];
  readonly type_counts?: readonly ApiFacetCount[];
}

/**
 * One region inside a geography. FEAT-061, ISS-213.
 *
 * `direction` is the compass word the region's own name carries, or null where it carries none.
 * It is what lets the drawing put `eu-west-1` and `eu-central-1` in different parts of Europe
 * with no table of regions to go stale. A word, never a coordinate: where a compass point lands
 * in a picture is the picture's business, which is why the offsets live in `WorldMap`.
 */
export interface ApiRegion {
  readonly region_id: string;
  readonly resources: number;
  readonly direction: string | null;
}

/** One continent's worth of the estate. FEAT-061. */
export interface ApiGeography {
  /** The region name prefix, which is the stable key the drawing positions by. */
  readonly key: string;
  readonly name: string;
  /**
   * Listed rather than counted. The prefix is continental and cannot tell Dublin from
   * Frankfurt, so naming the regions is the honest way to admit what it does not know.
   * Largest first.
   */
  readonly regions: readonly ApiRegion[];
  readonly resources: number;
  /**
   * Distinct across the whole geography, not the sum of its regions' counts. ISS-214: adding
   * per region counts counts an account twice when it is in two regions of one continent.
   */
  readonly accounts: number;
}

/**
 * The estate by continent, with three kinds of leftover that are never added together.
 *
 * `global_resources` belong to no region, which is a fact about the service. `unplaceable` are
 * regions whose prefix the table does not know, which is the one somebody can act on. `refused`
 * are regions a collection could not read, so the counts above them are a floor and not a total.
 */
/**
 * Two regions joined by resources this reader can read at both ends. TASK-P8-017.
 *
 * Undirected: `one_region` sorts before `other_region`, and `links` counts pairs of resources
 * rather than edges, so a peering recorded from both of its ends counts once. Each geography is
 * placed by the server's own prefix rule, and is null where no table knows the prefix. A link
 * inside one geography names it twice: it is real, and a map at continent grain cannot draw it.
 */
export interface ApiGeographyLink {
  readonly one_region: string;
  readonly other_region: string;
  readonly one_geography: string | null;
  readonly other_geography: string | null;
  /** Measured, pairs of resources. */
  readonly links: number;
  /** The kinds of edge that join them, PEERS_WITH for one. */
  readonly kinds: readonly string[];
}

export interface ApiGeographies {
  readonly geographies: readonly ApiGeography[];
  readonly global_resources: number;
  readonly unplaceable: readonly string[];
  readonly unplaceable_resources: number;
  readonly refused: readonly string[];
  readonly links: readonly ApiGeographyLink[];
}

export interface ApiResourceList {
  readonly resources: readonly ApiTopologyNode[];
  /** Matching rows in scope. Not the size of the estate and not the size of the page. */
  readonly total: number;
  readonly limit: number;
  readonly offset: number;
  /** Read from the data, so a filter the estate cannot satisfy is never offered. */
  readonly filters: ApiResourceFilters;
}

/**
 * FEAT-053. One resource, and everything we know about it.
 *
 * Two of these fields are admissions rather than facts, and both exist because the
 * alternative is a page that reads as reassuring. `coverage` says whether the slice this
 * resource came from was read whole, because a neighbour list drawn from a PARTIAL slice may
 * be missing the edge that matters. `unmatched_findings` says how many findings in the same
 * account could not be joined to any resource, because an empty finding list otherwise reads
 * as a clean resource.
 */
export interface ApiEntity {
  readonly node: ApiTopologyNode;
  /** Null means no coverage row exists at all, which is itself worth saying out loud. */
  readonly coverage: ApiSliceCoverage | null;
  /** One hop. Enough to answer what this is attached to without drawing the estate. */
  readonly neighbours: readonly ApiTopologyNode[];
  readonly edges: readonly ApiTopologyEdge[];
  /** Open and closed both, worst money first, carrying FEAT-052's risk verdict. */
  readonly findings: readonly ApiRecommendation[];
  /** Findings in the same account that joined to no resource. Non zero has to be said. */
  readonly unmatched_findings: number;
  /** Null is not zero. A resource the bill does not mention is not a free one. */
  readonly monthly_cost: string | null;
  readonly cost_period: string | null;
  /**
   * FEAT-057. MANAGED, UNMANAGED or NOT_DETERMINED, derived by the server rather than stored.
   *
   * NOT_DETERMINED is the default and is not a synonym for UNMANAGED. The first says we did not
   * find the resource in the state we read; the second says nobody manages it, and only the
   * second is an instruction. Telling somebody to import a resource already inside a module
   * produces a duplicate or a state conflict, so the screen renders the three differently.
   */
  readonly management_state: string;
  /** `module.network.aws_vpc.main`, where there is one. */
  readonly iac_address: string | null;
  /** The state location, so a reader can find the file. */
  readonly iac_state_reference: string | null;
}

/**
 * One quota with a usage figure, and what measured it. FEAT-033.
 *
 * Every quota in this shape has a `used` and a `source`. The ones that do not are
 * `ApiUnmeasurableQuota`, and the two are separate types rather than one type with nullable
 * fields, for the reason the screen shows two lists: a single list has to sort the nulls
 * somewhere and wherever they sort is a claim nobody has earned.
 */
export interface ApiQuota {
  readonly account_id: string;
  /** Null where the quota is global rather than regional, and never a placeholder. */
  readonly region_id: string | null;
  readonly service_code: string;
  readonly quota_code: string;
  readonly quota_name: string;
  /** Null where the provider publishes no limit. Zero is a real and different value. */
  readonly limit: string | null;
  readonly used: string;
  /** AWS_USAGE_METRIC, TRUSTED_ADVISOR or SERVICE_API. Never NONE in this shape. */
  readonly source: string;
  /** The fraction still free, nought to one, or null where the limit is absent or zero. */
  readonly headroom: string | null;
  readonly is_adjustable: boolean;
}

/**
 * One quota nothing measured, and why. FEAT-033, and the point of the sub project.
 *
 * It carries no `used` field at all rather than a null one, which is the difference this
 * type exists to make: a null would invite a bar at zero, and a zero says an account has
 * headroom nobody has measured.
 */
export interface ApiUnmeasurableQuota {
  readonly account_id: string;
  readonly region_id: string | null;
  readonly service_code: string;
  readonly quota_code: string;
  readonly quota_name: string;
  readonly limit: string | null;
  /** Which of the sources declined, and why. Required, and the database refuses a blank. */
  readonly reason: string;
  readonly is_adjustable: boolean;
}

export interface ApiQuotas {
  readonly measurable: readonly ApiQuota[];
  readonly unmeasurable: readonly ApiUnmeasurableQuota[];
  /** Stated rather than counted off the lists, because both lists are truncated. */
  readonly measured_count: number;
  readonly found_count: number;
}

export interface ApiRequestTransition {
  readonly status: string;
  readonly changed_at: string;
}

/** An increase somebody asked AWS for. Read, never written. Spec section 6. */
export interface ApiQuotaRequest {
  readonly request_id: string;
  readonly account_id: string;
  readonly region_id: string | null;
  readonly service_code: string;
  readonly quota_code: string;
  readonly quota_name: string;
  readonly desired_value: string;
  /** AWS's own vocabulary, all seven values. DENIED and NOT_APPROVED stay distinct. */
  readonly status: string;
  /** Whether anything is still going to happen. INVALID_REQUEST is not open. */
  readonly is_open: boolean;
  readonly requested_at: string;
  readonly last_updated_at: string;
  /** Always false. A field rather than a sentence, so nothing can delete the claim. */
  readonly submitted_by_meter: boolean;
}

export interface ApiQuotaRequests {
  readonly requests: readonly ApiQuotaRequest[];
  readonly open_count: number;
}

/** The increase Meter would ask for on one slice, with its working. FEAT-034. */
export interface ApiQuotaDraft {
  readonly account_id: string;
  readonly region_id: string | null;
  readonly current_limit: string;
  readonly observed_usage: string;
  readonly suggested_value: string;
  /** How the number was reached, so a reader disputes the target rather than the figure. */
  readonly working: string;
  readonly console_url: string;
  readonly cli_command: string;
}

/**
 * Why no draft was offered for a slice. FEAT-034.
 *
 * Separate from `ApiQuotaDraft` rather than a nullable field on it, because an empty draft
 * reads as a feature that failed rather than a decision somebody made.
 */
export interface ApiDraftRefusal {
  readonly account_id: string;
  readonly region_id: string | null;
  readonly reason: string;
}

/** One quota everywhere it applies, with every request against it. FEAT-033, FEAT-034. */
export interface ApiQuotaDetail {
  readonly service_code: string;
  readonly quota_code: string;
  readonly quota_name: string;
  readonly is_adjustable: boolean;
  readonly measurable: readonly ApiQuota[];
  readonly unmeasurable: readonly ApiUnmeasurableQuota[];
  readonly requests: readonly ApiQuotaRequest[];
  /** Keyed by request id. A request with no recorded transitions is absent, not empty. */
  readonly history: Readonly<Record<string, readonly ApiRequestTransition[]>>;
  readonly drafts: readonly ApiQuotaDraft[];
  readonly draft_refusals: readonly ApiDraftRefusal[];
}

// --- P6, containers -----------------------------------------------------------------

/** One workload's share of a cluster's cost. FEAT-035. */
export interface ApiContainerCostRow {
  readonly namespace: string;
  readonly workload_name: string;
  /** Empty where the export carried no workload type. Never guessed. */
  readonly workload_type: string;
  readonly cost: string;
  readonly line_items: number;
}

/** One cluster's cost, with its breakdown where there is one. */
export interface ApiClusterCost {
  readonly cluster_name: string;
  /** Attributed plus unattributed. The figure that reconciles to the node charge. */
  readonly total: string;
  readonly allocated: string;
  /** Capacity paid for and requested by no pod. A real figure, not a rounding error. */
  readonly unallocated: string;
  readonly workloads: readonly ApiContainerCostRow[];
  readonly breakdown_available: boolean;
  readonly unmeasurable_reason: string | null;
}

export interface ApiContainerCost {
  readonly clusters: readonly ApiClusterCost[];
  readonly measured_count: number;
  readonly found_count: number;
}

/** Requests against use for one workload. Two figures each, never a percentage. FEAT-036. */
export interface ApiContainerUsageRow {
  readonly namespace: string;
  readonly workload: string;
  readonly workload_kind: string;
  readonly launch_type: string;
  /** Null where the cluster cannot publish requests. Never zero. */
  readonly cpu_requested_millicores: string | null;
  readonly cpu_used_p99_millicores: string | null;
  readonly memory_requested_mib: string | null;
  readonly memory_used_peak_mib: string | null;
  /** UNOBSERVED is not a synonym for NOT_KILLED. */
  readonly oom_status: 'KILLED' | 'NOT_KILLED' | 'UNOBSERVED';
  readonly observation_days: number;
}

export interface ApiClusterUsage {
  readonly cluster_name: string;
  readonly account_id: string;
  readonly region_id: string;
  readonly platform: string;
  readonly enhanced_observability: boolean;
  readonly request_unavailable_reason: string | null;
  readonly workloads: readonly ApiContainerUsageRow[];
}

export interface ApiContainerWaste {
  readonly clusters: readonly ApiClusterUsage[];
  readonly measured_count: number;
  readonly found_count: number;
}

/** One cluster's fleet, Spot ratio and bin packing, where readable. */
export interface ApiClusterInventory {
  readonly cluster_name: string;
  readonly account_id: string;
  readonly region_id: string;
  readonly platform: string;
  readonly enhanced_observability: boolean;
  readonly node_count: number | null;
  /** Fractions of one, as decimal strings. Null where unreadable or where there is no fleet. */
  readonly spot_ratio: string | null;
  readonly packing_efficiency: string | null;
  readonly unmeasurable_reason: string | null;
}

export interface ApiClusters {
  readonly clusters: readonly ApiClusterInventory[];
  /** Clusters with nodes whose packing could be computed, against clusters with nodes. */
  readonly measured_count: number;
  readonly found_count: number;
}

// --- P7, the assistant ----------------------------------------------------------------

/**
 * Where one value in an answer or a digest came from. `CitationOut`, P7 spec section 5.2.
 *
 * The prose holds `{{placeholder}}` and never the value, and the screen puts the value in.
 * So every value a reader sees is one the deterministic layer read, and this record is how
 * they check it without leaving the page.
 */
export interface ApiCitation {
  readonly placeholder: string;
  readonly tool: string;
  /** The tool call it was read from, as named in the exchange's `tool_calls`. */
  readonly call_id: string;
  /** The path into the tool's envelope, such as `data[name=AmazonEC2].effective_cost`. */
  readonly field: string;
  /** As text, so a figure is the figure that was cited and never a float's idea of it. */
  readonly value: string;
  /** A figure renders through Figure. A label is a name, a date or an identifier. */
  readonly kind: 'figure' | 'label';
  /**
   * What a figure counts, as the tool that returned it declares, ISS-231. Null on a label, and
   * on a figure stored before citations carried a unit, which is drawn as unrecognised rather
   * than guessed from the field's name.
   */
  readonly unit: 'usd' | 'count' | null;
  readonly provenance: 'measured' | 'modelled';
  readonly as_of: string;
}

/** Prose with placeholders, and the citation behind each one. */
export interface ApiAnswer {
  readonly prose: string;
  readonly citations: readonly ApiCitation[];
}

/** What is missing, and the screen that would show it once it is not. */
export interface ApiAssistantRefusal {
  /** `tool`, `figure`, `scope`, `budget` or `secret`. A string, so a new one is shown. */
  readonly gap: string;
  readonly reason: string;
  /** A screen path such as `/cost/containers`, or null where no screen would show it. */
  readonly screen: string | null;
}

/** One of the seven typed causes, with what to do about it. */
export interface ApiExchangeFailure {
  readonly cause: string;
  readonly detail: string | null;
  readonly remediation: string;
}

/** One call the model asked for, in order. */
export interface ApiToolCall {
  readonly call_id: string;
  readonly tool: string;
  readonly returned: boolean;
}

/**
 * One question and which of three things came back. `ExchangeOut`.
 *
 * Exactly one of `answer`, `refusal` and `failure` is present, the one `outcome` names. The
 * API validates that before it sends, and the screen still checks, because a refusal drawn as
 * an empty answer is the failure spec section 5.3 exists to prevent.
 */
export interface ApiExchange {
  readonly exchange_id: string;
  /** As typed, with any secret replaced by the name of the rule that found it. */
  readonly question: string;
  readonly outcome: 'ANSWERED' | 'REFUSED' | 'FAILED';
  readonly answer: ApiAnswer | null;
  readonly refusal: ApiAssistantRefusal | null;
  readonly failure: ApiExchangeFailure | null;
  readonly tool_calls: readonly ApiToolCall[];
  /** Null where the question reached no model at all. */
  readonly model_id: string | null;
  readonly input_tokens: number;
  readonly output_tokens: number;
  /** Modelled at list prices, as a decimal string. The bill is the measurement. */
  readonly est_cost: string;
  /** Meter's own work, not a fact about the estate, so there is no `as_of` here. */
  readonly asked_at: string;
  readonly answered_at: string;
}

/** One week's digest, its citations, and whether it went anywhere. `DigestOut`, FEAT-041. */
export interface ApiDigest {
  readonly digest_id: string;
  readonly audience: 'team' | 'executive';
  /** The bill's team tag, `unallocated` for spend no tag claims, null on the executive one. */
  readonly team: string | null;
  readonly period_start: string;
  /** The week's last day, inclusive. */
  readonly period_end: string;
  readonly prose: string;
  readonly citations: readonly ApiCitation[];
  readonly composed_at: string;
  /** Null means composed and not sent, a real state with its reason beside it. */
  readonly sent_at: string | null;
  readonly unsent_reason: string | null;
}

/** What redaction did to one question: the rule and the action, never the secret. FEAT-046. */
export interface ApiRedaction {
  readonly event_id: string;
  readonly exchange_id: string;
  /** A gitleaks rule identifier, such as `aws-access-token`. */
  readonly rule_id: string;
  readonly action: 'BLOCKED' | 'REDACTED';
  readonly occurred_at: string;
}

/** FEAT-065. What one Cost Explorer axis groups by: a FOCUS column, or `tag` and a key. */
export interface ApiExploreGrouping {
  readonly dimension: string;
  readonly tag_key: string | null;
}

/** A run of days, inclusive at both ends, as ISO dates. */
export interface ApiExploreWindow {
  readonly start: string;
  readonly end: string;
}

/** What one named group cost in one day or month. A null series is everything else. */
export interface ApiExplorePoint {
  readonly bucket: string;
  readonly series: string | null;
  readonly cost: string;
}

/** One table row. A null previous is a period never collected, which is not zero. */
export interface ApiExploreRow {
  readonly first: string;
  readonly second: string | null;
  readonly this_period: string;
  readonly previous_period: string | null;
}

/** `GET /cost/explore`. Rows and omissions reconcile to the totals; a null total is none billed. */
export interface ApiExplore {
  readonly metric: string;
  readonly metrics_available: readonly string[];
  readonly period: string;
  readonly granularity: string;
  readonly current: ApiExploreWindow;
  readonly previous: ApiExploreWindow;
  /** The window ends today, so its last day is still being billed. */
  readonly is_open: boolean;
  readonly collected_from: string | null;
  readonly previous_collected: boolean;
  readonly group_by: ApiExploreGrouping;
  readonly then_by: ApiExploreGrouping | null;
  readonly tag_keys: readonly string[];
  readonly total_this_period: string | null;
  readonly total_previous_period: string | null;
  readonly series: readonly string[];
  readonly points: readonly ApiExplorePoint[];
  readonly rows: readonly ApiExploreRow[];
  readonly row_limit: number;
  readonly rows_omitted: number;
  readonly omitted_this_period: string;
  readonly omitted_previous_period: string | null;
  /**
   * Where the first grouping is region, the geography each row's region is in, by region,
   * resolved on the server by the geography map's own prefix rule so this application carries
   * no second copy of it. A region no table knows is absent. TASK-P8-017.
   */
  readonly region_geographies: Readonly<Record<string, ApiGeographyRef>>;
}

/** Which geography a region is in, by key and by name. */
export interface ApiGeographyRef {
  readonly key: string;
  readonly name: string;
}

/** FEAT-066. A forecast is a range, never a point, ADR-0015's second condition. */
export interface ApiForecastRange {
  readonly low: string;
  readonly high: string;
}

/** One month's forecast, or the sentence saying why there is none. */
export interface ApiForecastMonth {
  readonly month: string;
  readonly figure: ApiForecastRange | null;
  readonly withheld: string | null;
  /** How far off the method was at the median, as a share, measured by backtest. */
  readonly median_miss: string | null;
  readonly held_out: number;
}

/** One day of this month: billed so far, cumulative, or the band. Never both. */
export interface ApiForecastDay {
  readonly day: string;
  readonly billed: string | null;
  readonly low: string | null;
  readonly high: string | null;
}

/** One held out month. The range is null where the forecast is withheld. */
export interface ApiForecastTest {
  readonly month: string;
  readonly actual: string;
  readonly miss: string;
  readonly low: string | null;
  readonly high: string | null;
  readonly within: boolean | null;
}

/** `GET /cost/forecast`. Every figure is a forecast, and every forecast is a range. */
export interface ApiForecast {
  readonly provenance: 'forecast';
  readonly method: string;
  readonly method_detail: string;
  readonly interval_percent: number;
  readonly max_median_miss: string;
  readonly min_held_out: number;
  readonly billed_through: string;
  readonly billed_to_date: string;
  readonly month_end: ApiForecastMonth;
  readonly days: readonly ApiForecastDay[];
  readonly ahead: readonly ApiForecastMonth[];
  readonly backtest: readonly ApiForecastTest[];
}

/** Who besides its owner may open a saved view, FEAT-068. */
export type SavedViewVisibility = 'PRIVATE' | 'SHARED';

/** A screen's query string as an object: a parameter's value, or every value of a repeated one. */
export type SavedViewQuery = Readonly<Record<string, string | readonly string[]>>;

/**
 * `GET /reports/views`, one saved view as its reader sees it, FEAT-068. Configuration and never
 * data: a screen and its query under a name, so opening it reads the screen in the reader's scope.
 */
export interface ApiSavedView {
  readonly view_id: string;
  readonly name: string;
  readonly screen_path: string;
  readonly query: SavedViewQuery;
  readonly visibility: SavedViewVisibility;
  /** The reader saved it, so may rename, share or delete it. Who saved anyone else's is not said. */
  readonly owned: boolean;
  readonly created_at: string;
  readonly updated_at: string;
}

/** `POST /reports/views`. */
export interface SavedViewIn {
  readonly name: string;
  readonly screen_path: string;
  readonly query: SavedViewQuery;
  readonly visibility: SavedViewVisibility;
}

/** `PATCH /reports/views/{view_id}`: a new name, a new visibility, or both. */
export interface SavedViewChange {
  readonly name?: string;
  readonly visibility?: SavedViewVisibility;
}

/** The two formats a report is written in, FEAT-067 and FEAT-069. */
export type ReportFormat = 'xlsx' | 'csv';

/** How often a schedule renders, FEAT-069. */
export type ReportCadence = 'DAILY' | 'WEEKLY' | 'MONTHLY' | 'MONTH_CLOSE';

/** What became of a run: streamed to whoever exported it, kept, kept and sent, or failed. */
export type ReportRunStatus = 'STREAMED' | 'RENDERED' | 'SENT' | 'FAILED';

/** `GET /reports/schedules`, one schedule, its owner's alone. FEAT-069. */
export interface ApiSchedule {
  readonly schedule_id: string;
  /** Null once the view is deleted; the schedule then pauses after saying why. */
  readonly view_id: string | null;
  /** The view's name, or null where its owner can no longer open it. */
  readonly view_name: string | null;
  readonly screen_path: string | null;
  readonly export_path: string;
  readonly format: ReportFormat;
  readonly cadence: ReportCadence;
  readonly recipients: readonly string[];
  readonly enabled: boolean;
  readonly next_run_at: string;
  readonly created_at: string;
  readonly updated_at: string;
}

/** `GET /reports/schedules`: the schedules, and what the deployment does with what they make. */
export interface ApiSchedules {
  /** False where no bucket is configured, so nothing renders. */
  readonly rendering: boolean;
  /** How long a file is kept, in the server's words. OPEN-15. */
  readonly retention: string;
  /** Where a file goes, in the server's words. OPEN-11. */
  readonly delivery: string;
  readonly schedules: readonly ApiSchedule[];
}

/** `GET /reports/runs`, one run made for the reader. FEAT-069. */
export interface ApiReportRun {
  readonly run_id: string;
  readonly schedule_id: string | null;
  readonly view_path: string;
  readonly view_query: string;
  readonly format: ReportFormat;
  readonly status: ReportRunStatus;
  readonly rows: number;
  readonly bytes: number;
  readonly truncated: boolean;
  readonly failure_cause: string | null;
  readonly failure_detail: string | null;
  /** A file is kept and can be fetched again. */
  readonly has_file: boolean;
  readonly made_at: string;
  readonly finished_at: string | null;
  readonly as_of: string | null;
  readonly collected_at: string | null;
}

/** `POST /reports/schedules`. */
export interface ScheduleIn {
  readonly view_id: string;
  readonly export_path: string;
  readonly format: ReportFormat;
  readonly cadence: ReportCadence;
  readonly recipients: readonly string[];
}

/** `PATCH /reports/schedules/{schedule_id}`. */
export interface ScheduleChange {
  readonly enabled?: boolean;
  readonly format?: ReportFormat;
  readonly cadence?: ReportCadence;
  readonly recipients?: readonly string[];
}
