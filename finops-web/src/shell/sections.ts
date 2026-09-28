/**
 * The navigation, per ADR-0020. Seven groups, fixed for the life of the
 * product. A sub project adds screens inside a group and never adds a top level
 * entry, which is why this array does not grow as the roadmap lands.
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
}

export interface GroupDef {
  readonly label: string;
  readonly path: string;
  readonly screens: readonly ScreenDef[];
}

export const GROUPS: readonly GroupDef[] = [
  {
    label: 'Home',
    path: '/',
    screens: [{ path: '/', label: 'Home', arrives: null }],
  },
  {
    label: 'Cost',
    path: '/cost',
    screens: [
      { path: '/cost', label: 'Spend and trend', arrives: null },
      { path: '/cost/allocation', label: 'Allocation', arrives: null },
      { path: '/cost/anomalies', label: 'Anomalies', arrives: null },
      { path: '/cost/commitments', label: 'Commitments', arrives: null },
      { path: '/cost/budgets', label: 'Budgets', arrives: null },
      { path: '/cost/export', label: 'Export', arrives: null },
    ],
  },
  {
    label: 'Waste',
    path: '/waste',
    screens: [
      { path: '/waste', label: 'Recommendations', arrives: null },
      { path: '/waste/savings', label: 'Realized savings', arrives: null },
      { path: '/waste/score', label: 'FinOps Score', arrives: null },
    ],
  },
  {
    label: 'Governance',
    path: '/governance',
    screens: [
      { path: '/governance/queries', label: 'Query findings', arrives: null },
      { path: '/governance/instances', label: 'Query surfaces', arrives: null },
      { path: '/governance/adhoc', label: 'Ad hoc queries', arrives: null },
      { path: '/governance/enforcement', label: 'Enforcement', arrives: null },
      { path: '/governance/quotas', label: 'Quotas', arrives: null },
    ],
  },
  {
    label: 'Inventory',
    path: '/inventory',
    screens: [
      { path: '/inventory/accounts', label: 'Accounts', arrives: null },
      { path: '/inventory/organization', label: 'Organization', arrives: null },
      { path: '/inventory/resources', label: 'Resources', arrives: null },
      { path: '/inventory/topology', label: 'Topology', arrives: null },
      { path: '/inventory/geography', label: 'Geography', arrives: null },
    ],
  },
  {
    label: 'Platform',
    path: '/platform',
    screens: [
      { path: '/platform/ingest', label: 'Ingest', arrives: null },
      { path: '/platform/freshness', label: 'Freshness', arrives: null },
      { path: '/platform/cost', label: 'Meter cost', arrives: null },
      { path: '/platform/flags', label: 'Flags', arrives: 'P0, not yet surfaced' },
    ],
  },
  {
    label: 'Assistant',
    path: '/assistant',
    screens: [
      { path: '/assistant', label: 'Ask', arrives: 'P7 Insight and LLM layer' },
      { path: '/assistant/digests', label: 'Digests', arrives: 'P7 Insight and LLM layer' },
    ],
  },
];

export function allScreens(): readonly ScreenDef[] {
  return GROUPS.flatMap((group) => group.screens);
}

/** The screen a path names, or undefined when the path is not a screen at all. */
export function screenFor(path: string): ScreenDef | undefined {
  return allScreens().find((screen) => screen.path === path);
}

/**
 * The screen this path belongs to, and the group that holds it.
 *
 * One matcher, because the page heading and the open navigation group are two
 * answers to the same question, and two matchers is how a page ends up titled
 * by one screen while the menu highlights another. A detail path resolves to
 * the screen it was reached from, by longest matching prefix.
 */
function matchFor(pathname: string): { group: GroupDef; screen: ScreenDef } | null {
  let best: { group: GroupDef; screen: ScreenDef } | null = null;
  for (const group of GROUPS) {
    for (const screen of group.screens) {
      const exact = screen.path === pathname;
      const child = screen.path !== '/' && pathname.startsWith(`${screen.path}/`);
      if (!exact && !child) continue;
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

/**
 * A group that is only itself, like Home, whose single screen is the group's
 * own route. Drawing that as an accordion produces a section named Home holding
 * one link named Home, so it is drawn as a plain link instead.
 */
export function isSelfGroup(group: GroupDef): boolean {
  return group.screens.length === 1 && group.screens[0]?.path === group.path;
}
