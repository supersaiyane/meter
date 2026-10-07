/**
 * Turn the Natural Earth land outline into the dots the map draws. FEAT-061, TASK-P8-017.
 *
 * **Generated, not hand authored, and that is the whole point of this file.** The first two
 * versions of the map drew continents written out from memory, which produced shapes nobody
 * recognised: a North America with a spike where Alaska should be and a Europe in fragments. That
 * was the wrong approach rather than a bad attempt at the right one. This reads the same public
 * domain outline every mapping library uses.
 *
 * **Dots on a rounded projection, the owner's direction of 2026-10-05.** A regular grid is laid
 * over the Equal Earth projection, each grid point is taken back to a longitude and a latitude,
 * and the point is kept where it falls on land. Equal Earth is equal area, so a continent's dots
 * are in proportion to its size, and its curved sides are what make the world read as round.
 *
 * **No outline is drawn, so nothing can cross the antimeridian.** The outline version drew two
 * stray horizontal lines, Russia's and Fiji's rings, whose longitudes jump from 180 to minus 180
 * and were joined straight across the map. Here each ring is unwrapped into continuous longitudes
 * before a point is tested against it, and only dots are emitted.
 *
 * **Its dependencies are dev only, and the output is committed.** `world-atlas` and
 * `topojson-client` are not in `dependencies` and never reach a browser. What ships is a few
 * kilobytes of numbers, so the page renders the world with no runtime library and no fetch.
 * Re-run with `make world` if the crop or the spacing changes.
 */

import { writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';

import { feature } from 'topojson-client';

const require = createRequire(import.meta.url);
const topology = require('world-atlas/land-110m.json');

/** The crop. Antarctica is out and no provider has a region there. */
const NORTH = 83;
const SOUTH = -56;
const WIDTH = 1000;
/** Drawing units between dots. Five draws about four and a half thousand of them. */
const PITCH = 5;

// Equal Earth, Šavrič, Patterson and Jenny 2018. `equalEarth.ts` carries the same four numbers
// and is tested against the points this file projects, so the two cannot drift apart unseen.
const A1 = 1.340264;
const A2 = -0.081106;
const A3 = 0.000893;
const A4 = 0.003796;
const M = Math.sqrt(3) / 2;
const RAD = Math.PI / 180;

function forward(lambda, phi) {
  const l = Math.asin(M * Math.sin(phi));
  const l2 = l * l;
  const l6 = l2 * l2 * l2;
  return [
    (lambda * Math.cos(l)) / (M * (A1 + 3 * A2 * l2 + l6 * (7 * A3 + 9 * A4 * l2))),
    l * (A1 + A2 * l2 + l6 * (A3 + A4 * l2)),
  ];
}

/** The inverse, by Newton's method on the parametric latitude, as the projection's authors do. */
function inverse(x, y) {
  let l = y;
  for (let step = 0; step < 12; step += 1) {
    const l2 = l * l;
    const l6 = l2 * l2 * l2;
    const delta =
      (l * (A1 + A2 * l2 + l6 * (A3 + A4 * l2)) - y) /
      (A1 + 3 * A2 * l2 + l6 * (7 * A3 + 9 * A4 * l2));
    l -= delta;
    if (Math.abs(delta) < 1e-12) break;
  }
  const l2 = l * l;
  const l6 = l2 * l2 * l2;
  return [
    (M * x * (A1 + 3 * A2 * l2 + l6 * (7 * A3 + 9 * A4 * l2))) / Math.cos(l),
    Math.asin(Math.sin(l) / M),
  ];
}

const LEFT = forward(Math.PI, 0)[0];
const TOP = forward(0, NORTH * RAD)[1];
const BOTTOM = forward(0, SOUTH * RAD)[1];
const SCALE = WIDTH / (2 * LEFT);
const HEIGHT = Math.ceil((TOP - BOTTOM) * SCALE);

function project(lon, lat) {
  const [x, y] = forward(lon * RAD, lat * RAD);
  return [(x + LEFT) * SCALE, (TOP - y) * SCALE];
}

// `feature` returns a FeatureCollection where the topology object is a GeometryCollection and a
// single Feature otherwise, and world-atlas has shipped both shapes across versions.
const land = feature(topology, topology.objects.land);
const geometries =
  land.type === 'FeatureCollection' ? land.features.map((one) => one.geometry) : [land.geometry];
const polygons = geometries.flatMap((geometry) =>
  geometry.type === 'MultiPolygon' ? geometry.coordinates : [geometry.coordinates],
);

/** A ring with its longitudes made continuous, so one crossing 180 degrees is not split. */
function unwrap(ring) {
  const out = [];
  let offset = 0;
  let previous = null;
  for (const [lon, lat] of ring) {
    if (previous !== null) {
      if (lon - previous > 180) offset -= 360;
      else if (lon - previous < -180) offset += 360;
    }
    previous = lon;
    out.push([lon + offset, lat]);
  }
  return out;
}

function boxOf(ring) {
  const lons = ring.map(([lon]) => lon);
  const lats = ring.map(([, lat]) => lat);
  return {
    west: Math.min(...lons),
    east: Math.max(...lons),
    south: Math.min(...lats),
    north: Math.max(...lats),
  };
}

// Outer ring first, then its holes, which at this scale are the large lakes and inland seas.
const shapes = polygons
  .map((polygon) => polygon.map(unwrap).map((ring) => ({ ring, box: boxOf(ring) })))
  .filter(([outer]) => outer.box.north >= SOUTH);

/** Even odd ray casting, tried at the longitude and a turn either side of it. */
function inRing({ ring, box }, lon, lat) {
  if (lat < box.south || lat > box.north) return false;
  for (const shift of [0, 360, -360]) {
    const x = lon + shift;
    if (x < box.west || x > box.east) continue;
    let inside = false;
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i, i += 1) {
      const [xi, yi] = ring[i];
      const [xj, yj] = ring[j];
      if (yi > lat !== yj > lat && x < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) {
        inside = !inside;
      }
    }
    if (inside) return true;
  }
  return false;
}

function isLand(lon, lat) {
  return shapes.some(
    ([outer, ...holes]) => inRing(outer, lon, lat) && !holes.some((hole) => inRing(hole, lon, lat)),
  );
}

// Row by row, each row as pairs of a first column and a run length, which is a few kilobytes
// where the dots as path data would be sixty.
const columns = Math.floor(WIDTH / PITCH);
const lines = Math.floor(HEIGHT / PITCH);
const rows = [];
let dots = 0;
for (let row = 0; row < lines; row += 1) {
  const runs = [];
  let start = -1;
  for (let column = 0; column <= columns; column += 1) {
    let on = false;
    if (column < columns) {
      const [lambda, phi] = inverse(
        (PITCH / 2 + column * PITCH) / SCALE - LEFT,
        TOP - (PITCH / 2 + row * PITCH) / SCALE,
      );
      on = Math.abs(lambda) <= Math.PI && isLand(lambda / RAD, phi / RAD);
    }
    if (on && start < 0) start = column;
    if (!on && start >= 0) {
      runs.push(start, column - start);
      dots += column - start;
      start = -1;
    }
  }
  rows.push(runs);
}

// The edge of the projection inside the crop, down the west side and up the east.
const edge = [];
for (let lat = NORTH; lat >= SOUTH; lat -= 1) edge.push(project(-180, lat));
for (let lat = SOUTH; lat <= NORTH; lat += 1) edge.push(project(180, lat));
const frame = `M${edge.map(([x, y]) => `${x.toFixed(1)} ${y.toFixed(1)}`).join('L')}Z`;

// Points projected here, for `equalEarth.test.ts` to project again and compare.
const checks = [
  [-98, 39],
  [10, 50],
  [112, -6],
  [-58, -12],
  [180, 0],
  [-180, 83],
].map(([lon, lat]) => [lon, lat, ...project(lon, lat).map((value) => Number(value.toFixed(3)))]);

const out = `// GENERATED by scripts/build_world.mjs. Do not edit: run \`make world\`.
//
// The Natural Earth 110m land, as ${String(dots)} dots on an Equal Earth grid cropped to
// ${String(NORTH)}N and ${String(Math.abs(SOUTH))}S. Public domain, from the world-atlas package, which is a dev
// dependency: nothing here reaches the browser except these numbers.

/** The projection and the grid. \`equalEarth.ts\` projects with these numbers. */
export const WORLD = {
  width: ${String(WIDTH)},
  height: ${String(HEIGHT)},
  north: ${String(NORTH)},
  south: ${String(SOUTH)},
  pitch: ${String(PITCH)},
  scale: ${String(SCALE)},
  left: ${String(LEFT)},
  top: ${String(TOP)},
} as const;

/** Land dots, row by row from the north: each row is pairs of a first column and a run length. */
export const ROWS: readonly (readonly number[])[] = [
${rows.map((runs) => `  [${runs.join(', ')}],`).join('\n')}
];

/** The edge of the projection inside the crop, which is what makes the world read as round. */
export const FRAME = '${frame}';

/** Longitude, latitude, x and y, as this generator projected them. */
export const CHECKS: readonly (readonly [number, number, number, number])[] = [
${checks.map((check) => `  [${check.join(', ')}],`).join('\n')}
];
`;

writeFileSync(new URL('../src/components/worldDots.ts', import.meta.url), out);
console.log(
  `wrote ${String(dots)} dots in ${String(rows.length)} rows, ` +
    `${String(Math.round(out.length / 1024))} KB, ${String(WIDTH)}x${String(HEIGHT)}`,
);
