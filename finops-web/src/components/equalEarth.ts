import { WORLD } from './worldDots';

/**
 * Longitude and latitude to a point on the map, by Equal Earth. FEAT-061, TASK-P8-017.
 *
 * The land was projected by `scripts/build_world.mjs` and a geography's bubble is projected here,
 * so both carry the projection's four numbers. `equalEarth.test.ts` projects the generator's own
 * check points again, which is what keeps a bubble on the continent under it: two copies that
 * drifted would put every bubble in the wrong sea, and a test is the only thing that would say so.
 */

// Šavrič, Patterson and Jenny 2018.
const A1 = 1.340264;
const A2 = -0.081106;
const A3 = 0.000893;
const A4 = 0.003796;
const M = Math.sqrt(3) / 2;
const RAD = Math.PI / 180;

export function project(lon: number, lat: number): readonly [number, number] {
  const theta = Math.asin(M * Math.sin(lat * RAD));
  const t2 = theta * theta;
  const t6 = t2 * t2 * t2;
  const x = (lon * RAD * Math.cos(theta)) / (M * (A1 + 3 * A2 * t2 + t6 * (7 * A3 + 9 * A4 * t2)));
  const y = theta * (A1 + A2 * t2 + t6 * (A3 + A4 * t2));
  return [(x + WORLD.left) * WORLD.scale, (WORLD.top - y) * WORLD.scale];
}

/**
 * The land as one path of zero length strokes, one per dot. Round caps turn each into a dot, and
 * one path is one element where four and a half thousand circles would be as many.
 */
export function dotPath(rows: readonly (readonly number[])[], pitch: number): string {
  const parts: string[] = [];
  rows.forEach((runs, row) => {
    const y = (pitch / 2 + row * pitch).toFixed(1);
    for (let index = 0; index + 1 < runs.length; index += 2) {
      const first = runs[index] ?? 0;
      const length = runs[index + 1] ?? 0;
      parts.push(`M${(pitch / 2 + first * pitch).toFixed(1)} ${y}h0`);
      for (let step = 1; step < length; step += 1) {
        parts.push(`m${String(pitch)} 0h0`);
      }
    }
  });
  return parts.join('');
}
