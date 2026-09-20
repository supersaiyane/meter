import { describe, expect, it } from 'vitest';

import { GROUPS, allScreens } from '../sections';

describe('navigation groups', () => {
  it('has exactly the seven groups ADR-0020 fixes', () => {
    expect(GROUPS.map((g) => g.label)).toEqual([
      'Home',
      'Cost',
      'Waste',
      'Governance',
      'Inventory',
      'Platform',
      'Assistant',
    ]);
  });

  it('gives every screen a route inside its own group', () => {
    for (const group of GROUPS) {
      for (const screen of group.screens) {
        expect(screen.path.startsWith(group.path)).toBe(true);
      }
    }
  });

  it('never issues the same route twice', () => {
    const paths = allScreens().map((s) => s.path);
    expect(new Set(paths).size).toBe(paths.length);
  });

  it('marks an unbuilt screen with the sub project that brings it', () => {
    // Derived, not named. This assertion was pinned to `/cost` and then to
    // `/cost/anomalies`, and both shipped, so it failed twice for a reason
    // that had nothing to do with the mechanism it was testing. The claim is
    // that an unbuilt screen says what will fill it, so it is made against
    // whichever screen is unbuilt today.
    const unbuilt = allScreens().filter((s) => s.arrives !== null);
    expect(unbuilt.length).toBeGreaterThan(0);
    for (const screen of unbuilt) {
      // Every sub project is named P0 through P5, and an unbuilt screen names
      // the one that brings it. A screen carrying some other sentence is a
      // screen nobody can plan around.
      expect(screen.arrives).toMatch(/^P\d\b/);
    }
  });

  it('carries no arrival note on a screen that is built', () => {
    const spend = allScreens().find((s) => s.path === '/cost');
    expect(spend).toBeDefined();
    expect(spend?.arrives).toBeNull();
  });
});
