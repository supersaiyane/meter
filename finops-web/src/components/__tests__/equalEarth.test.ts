import { describe, expect, it } from 'vitest';

import { dotPath, project } from '../equalEarth';
import { ANCHORS } from '../worldLand';
import { CHECKS, ROWS, WORLD } from '../worldDots';

/**
 * The map's projection, TASK-P8-017. The land was projected by the generator and the bubbles are
 * projected here, so the two are held to the same points.
 */

describe('the Equal Earth projection', () => {
  it('puts every point where the generator put it', () => {
    expect(CHECKS.length).toBeGreaterThan(0);
    for (const [lon, lat, x, y] of CHECKS) {
      const [drawnX, drawnY] = project(lon, lat);
      expect(drawnX).toBeCloseTo(x, 2);
      expect(drawnY).toBeCloseTo(y, 2);
    }
  });

  it('spans the drawing from one side to the other along the equator', () => {
    expect(project(-180, 0)[0]).toBeCloseTo(0, 6);
    expect(project(180, 0)[0]).toBeCloseTo(WORLD.width, 6);
    expect(project(0, WORLD.north)[1]).toBeCloseTo(0, 6);
  });

  it('keeps every anchor inside the drawing', () => {
    for (const [key, [lon, lat]] of Object.entries(ANCHORS)) {
      const [x, y] = project(lon, lat);
      expect(x, key).toBeGreaterThan(0);
      expect(x, key).toBeLessThan(WORLD.width);
      expect(y, key).toBeGreaterThan(0);
      expect(y, key).toBeLessThan(WORLD.height);
    }
  });
});

describe('the land as dots', () => {
  it('draws one dot per grid point in a run, and nothing for an empty row', () => {
    expect(dotPath([[2, 3], []], 5)).toBe('M12.5 2.5h0m5 0h0m5 0h0');
  });

  it('draws the whole world as one path of every dot', () => {
    const dots = ROWS.reduce(
      (total, runs) => total + runs.filter((_, index) => index % 2 === 1).reduce((a, b) => a + b, 0),
      0,
    );
    const drawn = dotPath(ROWS, WORLD.pitch).match(/h0/g)?.length ?? 0;
    expect(drawn).toBe(dots);
    expect(dots).toBeGreaterThan(1000);
  });
});
