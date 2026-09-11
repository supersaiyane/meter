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
      { path: '/cost', label: 'Spend and trend', arrives: 'P1 Cost Intelligence' },
      { path: '/cost/allocation', label: 'Allocation', arrives: 'P1 Cost Intelligence' },
      { path: '/cost/anomalies', label: 'Anomalies', arrives: 'P1 Cost Intelligence' },
      { path: '/cost/commitments', label: 'Commitments', arrives: 'P1 Cost Intelligence' },
      { path: '/cost/export', label: 'Export', arrives: 'P1 Cost Intelligence' },
    ],
  },
  {
    label: 'Waste',
    path: '/waste',
    screens: [
      { path: '/waste', label: 'Recommendations', arrives: 'P3 Utilization and Rightsizing' },
      {
        path: '/waste/savings',
        label: 'Realized savings',
        arrives: 'P3 Utilization and Rightsizing',
      },
      {
        path: '/waste/score',
        label: 'FinOps Score',
        arrives: 'P3 Utilization and Rightsizing',
      },
    ],
  },
  {
    label: 'Governance',
    path: '/governance',
    screens: [
      { path: '/governance/queries', label: 'Query findings', arrives: null },
      { path: '/governance/instances', label: 'Query surfaces', arrives: null },
      { path: '/governance/enforcement', label: 'Enforcement', arrives: null },
      { path: '/governance/quotas', label: 'Quotas', arrives: 'P5 Quotas and Limits' },
    ],
  },
  {
    label: 'Inventory',
    path: '/inventory',
    screens: [
      { path: '/inventory/accounts', label: 'Accounts', arrives: null },
      { path: '/inventory/organization', label: 'Organization', arrives: null },
      {
        path: '/inventory/resources',
        label: 'Resources',
        arrives: 'P4 Inventory and Topology',
      },
      { path: '/inventory/topology', label: 'Topology', arrives: 'P4 Inventory and Topology' },
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
