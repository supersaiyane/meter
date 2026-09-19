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
    // Anomalies rather than spend. `/cost` carried this until 2026-09-19 and
    // then got built, which is what this assertion is supposed to notice: the
    // claim is about the mechanism, so it has to be made against a screen that
    // has not arrived yet.
    const anomalies = allScreens().find((s) => s.path === '/cost/anomalies');
    expect(anomalies?.arrives).toBe('P1 Cost Intelligence');
  });

  it('carries no arrival note on a screen that is built', () => {
    const spend = allScreens().find((s) => s.path === '/cost');
    expect(spend).toBeDefined();
    expect(spend?.arrives).toBeNull();
  });
});
