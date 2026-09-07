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
    const spend = allScreens().find((s) => s.path === '/cost');
    expect(spend?.arrives).toBe('P1 Cost Intelligence');
  });
});
