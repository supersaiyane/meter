import { describe, expect, it } from 'vitest';

import {
  GROUPS,
  REDIRECTS,
  TABS,
  UNPLANNED,
  allScreens,
  redirectFor,
  screenTitleFor,
  tabsFor,
} from '../sections';

/**
 * Every path the navigation listed before P8, written out rather than derived,
 * because the point is that a bookmark made before 2026-10-05 still lands, and
 * a list derived from the new navigation would forget exactly the paths that
 * left it.
 */
const BEFORE_P8 = [
  '/',
  '/cost',
  '/cost/allocation',
  '/cost/anomalies',
  '/cost/commitments',
  '/cost/budgets',
  '/cost/export',
  '/cost/containers',
  '/waste',
  '/waste/savings',
  '/waste/score',
  '/waste/containers',
  '/governance/queries',
  '/governance/instances',
  '/governance/adhoc',
  '/governance/enforcement',
  '/governance/quotas',
  '/inventory/accounts',
  '/inventory/organization',
  '/inventory/resources',
  '/inventory/topology',
  '/inventory/geography',
  '/inventory/clusters',
  '/platform/ingest',
  '/platform/freshness',
  '/platform/cost',
  '/platform/flags',
  '/assistant',
  '/assistant/digests',
] as const;

/** Every address a person can land on: a screen, or a tab of one. */
function landable(): ReadonlySet<string> {
  return new Set([
    ...allScreens().map((screen) => screen.path),
    ...Object.values(TABS)
      .flat()
      .map((tab) => tab.path),
  ]);
}

describe('navigation groups', () => {
  it('has the nine groups the owner approved on 2026-10-05, in order', () => {
    expect(GROUPS.map((g) => g.label)).toEqual([
      'Overview',
      'Analyze',
      'Plan',
      'Optimize',
      'Govern',
      'Inventory',
      'Report',
      'Assist',
      'Platform',
    ]);
  });

  it('lists the screens of P8 spec section 5.2 with the owner’s three placements', () => {
    // Placed by the owner on 2026-10-05, because the spec named no home for them:
    // the three container screens stay separate under Analyze, Enforcement
    // becomes Policies, and Flags stays under Platform as arriving.
    expect(
      Object.fromEntries(GROUPS.map((g) => [g.label, g.screens.map((s) => s.label)])),
    ).toEqual({
      Overview: ['Overview'],
      Analyze: [
        'Cost Explorer',
        'Allocation and Showback',
        'Anomalies',
        'Kubernetes cost',
        'Kubernetes rightsizing',
        'Clusters',
      ],
      Plan: ['Budgets', 'Forecasts', 'FinOps Score', 'Unit Economics'],
      Optimize: ['Recommendations', 'Commitments', 'Realized Savings', 'Savings ledger'],
      Govern: ['Query Cost', 'Quotas', 'Policies'],
      Inventory: ['Accounts', 'Resources', 'Topology'],
      Report: ['Report Library', 'Scheduled', 'Exports', 'Invoice reconciliation'],
      Assist: ['Ask Meter', 'Digests'],
      Platform: ['Data Freshness', 'Ingestion', 'Meter Cost', 'Flags'],
    });
  });

  it('gives every screen a route inside its own group', () => {
    for (const group of GROUPS) {
      for (const screen of group.screens) {
        expect(screen.path.startsWith(group.path), screen.path).toBe(true);
      }
    }
  });

  it('never issues the same route twice, counting tabs', () => {
    const paths = [
      ...allScreens().map((s) => s.path),
      ...Object.values(TABS)
        .flat()
        .map((t) => t.path),
    ];
    // A screen is its own first tab, so its path appears once as a screen and
    // once as a tab, and only that repetition is allowed.
    const firstTabs = Object.keys(TABS);
    expect(new Set(paths).size).toBe(paths.length - firstTabs.length);
  });

  it('marks an unbuilt screen with the sub project that brings it, or says none is planned', () => {
    // Derived, not named. This assertion was once pinned to `/cost` and then to
    // `/cost/anomalies`, and both shipped, so it failed twice for a reason that
    // had nothing to do with the mechanism it was testing.
    const unbuilt = allScreens().filter((s) => s.arrives !== null);
    expect(unbuilt.length).toBeGreaterThan(0);
    for (const screen of unbuilt) {
      if (screen.arrives !== UNPLANNED) {
        expect(screen.arrives).toMatch(/^P\d+\b/);
      }
    }
  });

  it('lists Unit Economics as arriving, never as built', () => {
    expect(allScreens().find((s) => s.label === 'Unit Economics')?.arrives).toBe(UNPLANNED);
  });

  it('carries no arrival note on a screen that is built', () => {
    const explorer = allScreens().find((s) => s.path === '/analyze/explorer');
    expect(explorer).toBeDefined();
    expect(explorer?.arrives).toBeNull();
  });
});

describe('every old path keeps working', () => {
  it('sends every path the navigation had before P8 somewhere a person can land', () => {
    const can = landable();
    for (const path of BEFORE_P8) {
      expect(can.has(redirectFor(path) ?? path), path).toBe(true);
    }
  });

  it('redirects only paths that left, so a current address is never moved', () => {
    const can = landable();
    for (const from of Object.keys(REDIRECTS)) {
      expect(can.has(from), from).toBe(false);
      expect(BEFORE_P8 as readonly string[], from).toContain(from);
    }
  });

  it('carries a detail address to the same detail under its new screen', () => {
    expect(redirectFor('/governance/queries/abc-123')).toBe(
      '/govern/query-cost/findings/abc-123',
    );
    expect(redirectFor('/governance/quotas/ec2/L-1216C47A')).toBe(
      '/govern/quotas/ec2/L-1216C47A',
    );
    expect(redirectFor('/inventory/resources/node-1')).toBeNull();
  });

  it('leaves an address that never existed alone', () => {
    expect(redirectFor('/nowhere')).toBeNull();
  });
});

describe('screens that merged are tabs of the screen they joined', () => {
  it('draws Organization, Geography and the three query cost screens as tabs', () => {
    expect(
      Object.fromEntries(
        Object.entries(TABS).map(([screen, tabs]) => [screen, tabs.map((t) => t.label)]),
      ),
    ).toEqual({
      '/inventory/accounts': ['Accounts', 'Organization'],
      '/inventory/topology': ['Topology', 'Geography'],
      '/govern/query-cost': ['Findings', 'Sources', 'Ad hoc'],
    });
  });

  it('titles a tab by its screen and marks the tab that is open', () => {
    expect(screenTitleFor('/inventory/accounts/organization')).toBe('Accounts');
    expect(tabsFor('/inventory/accounts/organization')?.current).toBe(
      '/inventory/accounts/organization',
    );
    expect(tabsFor('/govern/query-cost/findings/abc-123')?.current).toBe('/govern/query-cost');
    expect(tabsFor('/plan/budgets')).toBeNull();
  });
});
