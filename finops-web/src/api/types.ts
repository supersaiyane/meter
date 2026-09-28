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
export interface ApiResourceFilters {
  readonly account_id: readonly string[];
  /** Never an empty string. A null region is the global slice and the screen names it. */
  readonly region_id: readonly string[];
  readonly node_kind: readonly string[];
  /** The provider's own words. It has no enumeration, so the data is the only list. */
  readonly resource_type: readonly string[];
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
export interface ApiGeographies {
  readonly geographies: readonly ApiGeography[];
  readonly global_resources: number;
  readonly unplaceable: readonly string[];
  readonly unplaceable_resources: number;
  readonly refused: readonly string[];
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
