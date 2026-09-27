import type { ApiGeography } from '../api/types';
import { ANCHORS, LAND, type Ring } from './worldLand';

/**
 * The estate on a schematic world. FEAT-061.
 *
 * **A real coastline, coarsely drawn.** The first version was a graticule and two dots, on the
 * argument that a coastline implies a precision the prefix does not have. That argument was wrong
 * about where the claim lives: a coastline says "this is the world", and it is the marker's
 * position that would claim a datacentre. Without land a reader cannot tell which dot is North
 * America without reading the label, which makes the picture decorative rather than informative.
 * The outlines in `worldLand.ts` are deliberately coarse, so they read as a schematic, and the
 * caption still says a marker is a continent and not a datacentre.
 *
 * **Equirectangular, and cropped north and south.** The simplest projection there is, one
 * multiplication per axis, because the drawing's job is recognition and not measurement. Cropped
 * to the latitudes that hold land people run things in, which drops Antarctica and most of the
 * empty ocean the full range spends half its height on.
 *
 * **The positions live in the drawing and not in the domain.** The backend decides which geography
 * a region is in; where that geography sits in a picture is a fact about the picture. A geography
 * the backend returns and this table has no anchor for is therefore not dropped: it is absent from
 * the drawing, still listed in the legend, and counted in a sentence, because a map that silently
 * omits a continent reports a smaller estate than exists.
 *
 * **Markers are sized by area, not by radius.** A continent with four times the resources gets a
 * marker with four times the area, so doubling the radius would claim four times again. That is
 * the oldest lie in data drawing and it is one square root away from being honest.
 *
 * **The drawing is decoration and the legend is the content.** The SVG carries `aria-hidden` and
 * every figure in it is written out as text underneath, which is the same choice `RankedBars`
 * makes and for the same reason: a reader who cannot see the picture loses a faster way to
 * compare numbers that are all written down.
 */

//: The latitudes the drawing keeps. Antarctica is out, which costs nothing because no provider
//: has a region there, and the far north is trimmed to where Greenland ends. The full range spends
//: half its height on empty ocean.
const NORTH = 83;
const SOUTH = -56;

const WIDTH = 1000;
//: Set by the projection rather than chosen: at this crop the degrees per pixel are equal on both
//: axes, so the continents are the shape people recognise instead of squashed or stretched.
const HEIGHT = Math.round((WIDTH * (NORTH - SOUTH)) / 360);

//: Every thirty degrees, with the equator and the prime meridian picked out. A graticule at real
//: intervals is what tells a reader this is a projection rather than a decorative grid.
const MERIDIANS = [-150, -120, -90, -60, -30, 0, 30, 60, 90, 120, 150];
const PARALLELS = [60, 30, 0, -30];

/** Longitude and latitude to a point in the drawing. Equirectangular, which is two multiplies. */
function project(lon: number, lat: number): readonly [number, number] {
  return [((lon + 180) / 360) * WIDTH, ((NORTH - lat) / (NORTH - SOUTH)) * HEIGHT];
}

function pointsOf(ring: Ring): string {
  return ring
    .map(([lon, lat]) => {
      const [x, y] = project(lon, lat);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');
}
const SMALLEST = 7;
const LARGEST = 34;

export interface WorldMapProps {
  readonly geographies: readonly ApiGeography[];
  /** The geography whose resources are being listed, or null for none. */
  readonly selected: string | null;
  readonly onSelect: (key: string) => void;
}

/** Marker radius, by area rather than by radius. See the note above. */
function radiusFor(resources: number, peak: number): number {
  if (peak <= 0) return SMALLEST;
  const share = Math.sqrt(resources / peak);
  return SMALLEST + share * (LARGEST - SMALLEST);
}

export function WorldMap({ geographies, selected, onSelect }: WorldMapProps) {
  const peak = geographies.reduce((most, one) => Math.max(most, one.resources), 0);
  const placed = geographies.filter((one) => ANCHORS[one.key] !== undefined);
  const unplaced = geographies.filter((one) => ANCHORS[one.key] === undefined);

  return (
    <figure data-testid="world-map">
      <svg viewBox={`0 0 ${String(WIDTH)} ${String(HEIGHT)}`} aria-hidden="true">
        {/* The graticule. It says "schematic" without pretending to be cartography, and it
            gives the markers something to be positioned against. */}
        <g data-testid="world-map-grid">
          {PARALLELS.map((lat) => (
            <line
              key={`lat${String(lat)}`}
              x1={0}
              x2={WIDTH}
              y1={project(0, lat)[1]}
              y2={project(0, lat)[1]}
              data-major={lat === 0}
            />
          ))}
          {MERIDIANS.map((lon) => (
            <line
              key={`lon${String(lon)}`}
              y1={0}
              y2={HEIGHT}
              x1={project(lon, 0)[0]}
              x2={project(lon, 0)[0]}
              data-major={lon === 0}
            />
          ))}
        </g>
        {/* The land, under the graticule's lines and over its background. Coarse on purpose:
            recognisable enough to place a marker, plainly not cartography. */}
        <g data-testid="world-map-land">
          {LAND.map((ring) => (
            <polygon key={pointsOf(ring).slice(0, 24)} points={pointsOf(ring)} />
          ))}
        </g>
        {placed.map((one) => {
          const [lon, lat] = ANCHORS[one.key] as readonly [number, number];
          const [x, y] = project(lon, lat);
          return (
            <g
              key={one.key}
              data-testid="world-map-marker"
              data-key={one.key}
              data-selected={selected === one.key}
              onClick={() => {
                onSelect(one.key);
              }}
            >
              <circle cx={x} cy={y} r={radiusFor(one.resources, peak)} />
              <text x={x} y={y - radiusFor(one.resources, peak) - 12}>
                {one.name}
              </text>
              {/* The count on the marker, so the drawing can be read without running the eye
                  down to the legend for every continent. */}
              <text
                data-testid="world-map-marker-count"
                x={x}
                y={y + radiusFor(one.resources, peak) + 22}
              >
                {one.resources}
              </text>
            </g>
          );
        })}
      </svg>

      <figcaption data-testid="world-map-caption">
        Continents, from region names. A region name says which geography it is in and never
        which city, so a marker is a continent and not a datacentre.
        {unplaced.length > 0 ? (
          // Never dropped. A drawing that omits a continent reports a smaller estate.
          <span data-testid="world-map-unplaced">
            {' '}
            {unplaced.length === 1
              ? '1 geography is not on the drawing and is listed below'
              : `${String(unplaced.length)} geographies are not on the drawing and are listed below`}
            .
          </span>
        ) : null}
      </figcaption>

      {/* The content. Every figure in the drawing, written out, and the control that actually
          works from a keyboard. */}
      <ul data-testid="world-map-legend">
        {geographies.map((one) => (
          <li key={one.key}>
            <button
              type="button"
              data-testid="world-map-choice"
              data-key={one.key}
              aria-pressed={selected === one.key}
              onClick={() => {
                onSelect(one.key);
              }}
            >
              <span data-testid="world-map-name">{one.name}</span>
              <span data-testid="world-map-count">
                {one.resources} {one.resources === 1 ? 'resource' : 'resources'}
              </span>
              {/* Named, because the prefix cannot tell one city from another and a reader
                  looking at Europe is entitled to know which regions that means. */}
              <span data-testid="world-map-regions">{one.regions.join(', ')}</span>
            </button>
          </li>
        ))}
      </ul>
    </figure>
  );
}
