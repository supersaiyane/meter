/**
 * The navigation, per ADR-0030, which supersedes ADR-0020's seven groups. Nine
 * groups, each answering to a domain of the FinOps Framework, approved by the
 * owner on 2026-10-05 in P8 spec section 5.2. A sub project adds screens inside
 * a group; a new group, or a renamed one, takes an ADR, as it did here.
 *
 * `arrives` is null when the screen is built. When it is a sub project name the
 * screen is listed and reachable, and says what will fill it. Hiding an unbuilt
 * screen would make the product look smaller than it is and hide the roadmap.
 *
 * Detail screens are not listed here. This is the navigation, and a finding
 * detail is reached from its finding rather than from a menu.
 */

export interface ScreenDef {
  readonly path: string;
  readonly label: string;
  /** Null when built. The sub project name when it is not. */
  readonly arrives: string | null;
  /** The query string keys this screen reads as filters, P8 spec section 5.6. */
  readonly filters?: readonly string[];
}

export interface GroupDef {
  readonly label: string;
  readonly path: string;
  readonly screens: readonly ScreenDef[];
}

/** One view of a screen that another screen merged into. */
export interface TabDef {
  readonly path: string;
  readonly label: string;
}

/**
 * What an unbuilt screen says when no sub project is planned to build it. One
 * sentence, so a screen nobody can plan around says so in a way a test can hold.
 */
export const UNPLANNED = 'a sub project not yet planned';

/**
 * The filters each filtered screen reads from its address, declared once here
 * and imported by the screen, so the navigation, the screen and the shell agree
 * on which parameters are filters. Saved views store exactly these.
 */
export const RECOMMENDATION_FILTERS = ['finding'] as const;
export const ALLOCATION_FILTERS = ['tag'] as const;
/**
 * Cost Explorer's whole view, so a link lands on the same view: both groupings, the period,
 * the granularity, the measure, and a filter for each grouping column and for a tag. The names
 * are the route's own, so the screen hands its query string to `GET /cost/explore` unchanged.
 */
export const EXPLORER_FILTERS = [
  'group_by',
  'group_by_tag',
  'then_by',
  'then_by_tag',
  'period',
  'start',
  'end',
  'granularity',
  'metric',
  'service',
  'service_category',
  'account',
  'region',
  'availability_zone',
  'charge_category',
  'commitment_discount_type',
  'commitment_discount_status',
  'tag_key',
  'tag_value',
] as const;
export const ACCOUNT_FILTERS = ['status'] as const;
export const RESOURCE_FILTERS = ['account', 'region', 'geography', 'kind', 'type'] as const;

export const GROUPS: readonly GroupDef[] = [
  {
    // Understand Usage and Cost: Reporting and Analytics. The persona
    // dashboards of TASK-P8-012 land on this screen.
    label: 'Overview',
    path: '/',
    screens: [{ path: '/', label: 'Overview', arrives: null }],
  },
  {
    // Understand Usage and Cost: Reporting and Analytics, Allocation, and
    // Anomaly Management. The three container screens stay separate here, the
    // owner's choice on 2026-10-05.
    label: 'Analyze',
    path: '/analyze',
    screens: [
      {
        path: '/analyze/explorer',
        label: 'Cost Explorer',
        arrives: null,
        filters: EXPLORER_FILTERS,
      },
      {
        path: '/analyze/allocation',
        label: 'Allocation and Showback',
        arrives: null,
        filters: ALLOCATION_FILTERS,
      },
      { path: '/analyze/anomalies', label: 'Anomalies', arrives: null },
      { path: '/analyze/kubernetes-cost', label: 'Kubernetes cost', arrives: null },
      {
        path: '/analyze/kubernetes-rightsizing',
        label: 'Kubernetes rightsizing',
        arrives: null,
      },
      { path: '/analyze/clusters', label: 'Clusters', arrives: null },
    ],
  },
  {
    // Quantify Business Value: Budgeting, Forecasting, KPIs and Benchmarking,
    // and Unit Economics. The FinOps Score sits beside the budgets it is read
    // with, because the Framework places KPIs here.
    label: 'Plan',
    path: '/plan',
    screens: [
      { path: '/plan/budgets', label: 'Budgets', arrives: null },
      { path: '/plan/forecasts', label: 'Forecasts', arrives: null },
      { path: '/plan/score', label: 'FinOps Score', arrives: null },
      { path: '/plan/unit-economics', label: 'Unit Economics', arrives: UNPLANNED },
    ],
  },
  {
    // Optimize Usage and Cost: Usage Optimization and Rate Optimization.
    label: 'Optimize',
    path: '/optimize',
    screens: [
      {
        path: '/optimize',
        label: 'Recommendations',
        arrives: null,
        filters: RECOMMENDATION_FILTERS,
      },
      { path: '/optimize/commitments', label: 'Commitments', arrives: null },
      { path: '/optimize/savings', label: 'Realized Savings', arrives: null },
    ],
  },
  {
    // Manage the FinOps Practice: Governance, Policy and Risk. Enforcement is
    // Policies, the owner's choice on 2026-10-05.
    label: 'Govern',
    path: '/govern',
    screens: [
      { path: '/govern/query-cost', label: 'Query Cost', arrives: null },
      { path: '/govern/quotas', label: 'Quotas', arrives: null },
      { path: '/govern/policies', label: 'Policies', arrives: null },
    ],
  },
  {
    // No Framework domain owns inventory. The ITAM persona and Data Ingestion
    // are the nearest, which is why this group stands beside the four.
    label: 'Inventory',
    path: '/inventory',
    screens: [
      {
        path: '/inventory/accounts',
        label: 'Accounts',
        arrives: null,
        filters: ACCOUNT_FILTERS,
      },
      {
        path: '/inventory/resources',
        label: 'Resources',
        arrives: null,
        filters: RESOURCE_FILTERS,
      },
      { path: '/inventory/topology', label: 'Topology', arrives: null },
    ],
  },
  {
    // Understand Usage and Cost: Reporting and Analytics.
    label: 'Report',
    path: '/report',
    screens: [
      { path: '/report/library', label: 'Report Library', arrives: null },
      { path: '/report/scheduled', label: 'Scheduled', arrives: null },
      { path: '/report/exports', label: 'Exports', arrives: null },
    ],
  },
  {
    // AI for FinOps.
    label: 'Assist',
    path: '/assist',
    screens: [
      { path: '/assist', label: 'Ask Meter', arrives: null },
      { path: '/assist/digests', label: 'Digests', arrives: null },
    ],
  },
  {
    // Manage the FinOps Practice: Automation, Tools and Services. Flags stays
    // listed as arriving, the owner's choice on 2026-10-05.
    label: 'Platform',
    path: '/platform',
    screens: [
      { path: '/platform/freshness', label: 'Data Freshness', arrives: null },
      { path: '/platform/ingest', label: 'Ingestion', arrives: null },
      { path: '/platform/cost', label: 'Meter Cost', arrives: null },
      { path: '/platform/flags', label: 'Flags', arrives: 'P0, not yet surfaced' },
    ],
  },
];

/**
 * Screens that merged into another, drawn as tabs of the screen they joined.
 * The first tab is the screen itself, so its address does not change.
 */
export const TABS: Readonly<Record<string, readonly TabDef[]>> = {
  '/inventory/accounts': [
    { path: '/inventory/accounts', label: 'Accounts' },
    { path: '/inventory/accounts/organization', label: 'Organization' },
  ],
  '/inventory/topology': [
    { path: '/inventory/topology', label: 'Topology' },
    { path: '/inventory/topology/geography', label: 'Geography' },
  ],
  '/govern/query-cost': [
    { path: '/govern/query-cost', label: 'Findings' },
    { path: '/govern/query-cost/surfaces', label: 'Sources' },
    { path: '/govern/query-cost/adhoc', label: 'Ad hoc' },
  ],
};

/**
 * Where each path that left the navigation went, so a bookmark, a digest link
 * or a link in a pull request body made before P8 still lands. Exact paths
 * only: an address is matched whole, never by prefix, except the two detail
 * families below.
 */
export const REDIRECTS: Readonly<Record<string, string>> = {
  '/cost': '/analyze/explorer',
  '/cost/allocation': '/analyze/allocation',
  '/cost/anomalies': '/analyze/anomalies',
  '/cost/commitments': '/optimize/commitments',
  '/cost/budgets': '/plan/budgets',
  '/cost/export': '/report/exports',
  '/cost/containers': '/analyze/kubernetes-cost',
  '/waste': '/optimize',
  '/waste/savings': '/optimize/savings',
  '/waste/score': '/plan/score',
  '/waste/containers': '/analyze/kubernetes-rightsizing',
  '/governance/queries': '/govern/query-cost',
  '/governance/instances': '/govern/query-cost/surfaces',
  '/governance/adhoc': '/govern/query-cost/adhoc',
  '/governance/enforcement': '/govern/policies',
  '/governance/quotas': '/govern/quotas',
  '/inventory/organization': '/inventory/accounts/organization',
  '/inventory/geography': '/inventory/topology/geography',
  '/inventory/clusters': '/analyze/clusters',
  '/assistant': '/assist',
  '/assistant/digests': '/assist/digests',
};

/** Detail addresses, which carry an identifier after a fixed prefix. */
const MOVED_DETAILS: readonly (readonly [from: string, to: string])[] = [
  ['/governance/queries/', '/govern/query-cost/findings/'],
  ['/governance/quotas/', '/govern/quotas/'],
];

/** Where an address that left the navigation lives now, or null when it never moved. */
export function redirectFor(pathname: string): string | null {
  const exact = REDIRECTS[pathname];
  if (exact !== undefined) {
    return exact;
  }
  for (const [from, to] of MOVED_DETAILS) {
    if (pathname.startsWith(from) && pathname.length > from.length) {
      return `${to}${pathname.slice(from.length)}`;
    }
  }
  return null;
}

export function allScreens(): readonly ScreenDef[] {
  return GROUPS.flatMap((group) => group.screens);
}

/** The screen a path names, or undefined when the path is not a screen at all. */
export function screenFor(path: string): ScreenDef | undefined {
  return allScreens().find((screen) => screen.path === path);
}

/** True when `pathname` is `path` itself or an address beneath it. */
function within(pathname: string, path: string): boolean {
  return pathname === path || (path !== '/' && pathname.startsWith(`${path}/`));
}

/**
 * The screen this path belongs to, and the group that holds it.
 *
 * One matcher, because the page heading and the open navigation group are two
 * answers to the same question, and two matchers is how a page ends up titled
 * by one screen while the menu highlights another. A detail path and a tab
 * resolve to the screen they belong to, by longest matching prefix.
 */
function matchFor(pathname: string): { group: GroupDef; screen: ScreenDef } | null {
  let best: { group: GroupDef; screen: ScreenDef } | null = null;
  for (const group of GROUPS) {
    for (const screen of group.screens) {
      if (!within(pathname, screen.path)) continue;
      if (best === null || screen.path.length > best.screen.path.length) {
        best = { group, screen };
      }
    }
  }
  return best;
}

/**
 * What to call the page at this path. The navigation is the only list of screen
 * names, so the heading is taken from it rather than restated.
 */
export function screenTitleFor(pathname: string): string {
  // An unrouted path is still a page and still needs naming. Saying it is not
  // built is truer than leaving the heading empty.
  return matchFor(pathname)?.screen.label ?? 'Not built yet';
}

/**
 * Which group to open. Null for a path in none of them, where opening nothing
 * is right: a wrong address should not make a section look current.
 */
export function activeGroupFor(pathname: string): string | null {
  return matchFor(pathname)?.group.label ?? null;
}

/** The query string keys the screen at this path reads as filters; none for most. */
export function filtersFor(pathname: string): readonly string[] {
  return matchFor(pathname)?.screen.filters ?? [];
}

/** The tabs of the screen at this path, and which one is open, or null for a screen without tabs. */
export function tabsFor(pathname: string): {
  readonly screen: ScreenDef;
  readonly tabs: readonly TabDef[];
  readonly current: string;
} | null {
  const match = matchFor(pathname);
  const tabs = match === null ? undefined : TABS[match.screen.path];
  if (match === null || tabs === undefined) {
    return null;
  }
  // The deepest tab the path sits in, so a finding's detail page keeps its
  // Query findings tab open.
  const current = tabs
    .filter((tab) => within(pathname, tab.path))
    .reduce(
      (deepest, tab) => (tab.path.length > deepest.length ? tab.path : deepest),
      match.screen.path,
    );
  return { screen: match.screen, tabs, current };
}

/**
 * A group that is only itself, like Overview, whose single screen is the
 * group's own route. Drawing that as an accordion produces a section named
 * Overview holding one link named Overview, so it is drawn as a plain link.
 */
export function isSelfGroup(group: GroupDef): boolean {
  return group.screens.length === 1 && group.screens[0]?.path === group.path;
}

/** The report library, FEAT-068, whose rows are saved views and which is no view itself. */
export const LIBRARY_PATH = '/report/library';

/**
 * True for an address a view can be saved from, FEAT-068: a built screen or a tab of one, which
 * is what the API's list of screens holds, other than the library, whose rows are the views.
 */
export function isSavable(pathname: string): boolean {
  if (pathname === LIBRARY_PATH) {
    return false;
  }
  const screen = screenFor(pathname);
  if (screen !== undefined) {
    return screen.arrives === null;
  }
  return Object.entries(TABS).some(
    ([owner, tabs]) =>
      screenFor(owner)?.arrives === null && tabs.some((tab) => tab.path === pathname),
  );
}
