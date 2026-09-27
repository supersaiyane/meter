import type { ApiGeography } from '../api/types';

/**
 * The estate on a schematic world. FEAT-061.
 *
 * **A schematic and not a projection, and it says so.** The geography comes from a region name
 * prefix, which is continental: it knows a resource is in Europe and cannot know whether that is
 * Dublin or Frankfurt. Drawing coastlines would imply a precision the data does not have, so this
 * draws a graticule and places one marker per continent. The caption states the limit rather than
 * leaving a reader to assume the dot is where the datacentre is.
 *
 * **The positions live here and not in the domain.** The backend decides which geography a region
 * is in; where that geography sits in a picture is a fact about the picture. A geography the
 * backend returns and this table has no position for is therefore not dropped: it is absent from
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

/** Fractions of the drawing, west to east. Not coordinates of anything in the world. */
const POSITIONS: Readonly<Record<string, readonly [number, number]>> = {
  us: [0.19, 0.36],
  ca: [0.2, 0.21],
  sa: [0.3, 0.7],
  eu: [0.49, 0.25],
  af: [0.52, 0.58],
  il: [0.565, 0.4],
  me: [0.62, 0.44],
  cn: [0.755, 0.33],
  ap: [0.8, 0.56],
};

const WIDTH = 1000;
//: Roughly two to one, the shape of an equirectangular world, which is what stops the drawing
//: reading as an empty panel with two dots in it.
const HEIGHT = 500;

//: Evenly spaced with the middle one picked out. A grid at even intervals with a stronger line
//: through the centre is what makes an eye see a projection rather than a box with lines in it.
const GRATICULE = [0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875];
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
  const placed = geographies.filter((one) => POSITIONS[one.key] !== undefined);
  const unplaced = geographies.filter((one) => POSITIONS[one.key] === undefined);

  return (
    <figure data-testid="world-map">
      <svg viewBox={`0 0 ${String(WIDTH)} ${String(HEIGHT)}`} aria-hidden="true">
        {/* The graticule. It says "schematic" without pretending to be cartography, and it
            gives the markers something to be positioned against. */}
        <g data-testid="world-map-grid">
          {GRATICULE.map((at) => (
            <line
              key={`h${String(at)}`}
              x1={0}
              x2={WIDTH}
              y1={at * HEIGHT}
              y2={at * HEIGHT}
              data-major={at === 0.5}
            />
          ))}
          {GRATICULE.map((at) => (
            <line
              key={`v${String(at)}`}
              y1={0}
              y2={HEIGHT}
              x1={at * WIDTH}
              x2={at * WIDTH}
              data-major={at === 0.5}
            />
          ))}
        </g>
        {placed.map((one) => {
          const [x, y] = POSITIONS[one.key] as readonly [number, number];
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
              <circle cx={x * WIDTH} cy={y * HEIGHT} r={radiusFor(one.resources, peak)} />
              <text x={x * WIDTH} y={y * HEIGHT - radiusFor(one.resources, peak) - 12}>
                {one.name}
              </text>
              {/* The count on the marker, so the drawing can be read without running the eye
                  down to the legend for every continent. */}
              <text
                data-testid="world-map-marker-count"
                x={x * WIDTH}
                y={y * HEIGHT + radiusFor(one.resources, peak) + 22}
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
