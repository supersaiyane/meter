import { useId, useState, type KeyboardEvent } from 'react';

import { arc, radiusFor, weightFor, type GeographyLink } from '../screens/geographyModel';
import { DenseRegion } from './DenseRegion';
import { dotPath, project } from './equalEarth';
import { Figure } from './Figure';
import type { Freshness } from './provenance';
import { ANCHORS } from './worldLand';
import { FRAME, ROWS, WORLD } from './worldDots';

/**
 * The estate on a world of dots. FEAT-061, redrawn by TASK-P8-017 to the owner's direction of
 * 2026-10-05: land as fine dots on a rounded projection, each geography a glowing bubble sized by
 * this month's Effective Cost with its resource count beside it, and lines for links across
 * regions.
 *
 * **A real coastline, from the outline every mapping library uses.** The dots are generated from
 * the Natural Earth 110m land by `make world` into `worldDots.ts`, with dev only dependencies, so
 * the page draws the world with no runtime library and no fetch. Two earlier versions drew
 * continents from memory and produced shapes nobody recognised; a third drew outlines, and two of
 * them crossed the antimeridian as stray lines across the whole map. Dots cannot.
 *
 * **A continent is the finest grain, because a region name is.** A region name says which
 * geography it is in and never which city, so one bubble per geography sits on a point inside the
 * continent, never on a datacentre. The regions inside it are named in the tooltip, in its tile
 * and in the table, which is the honest way to admit what the name cannot tell.
 *
 * **Bubbles are sized by area, not by radius.** Four times the cost is four times the ink, and a
 * cost that could not be read draws every bubble the same size and says so, rather than sizing by
 * something else or drawing a failure as nought.
 *
 * **Every number on the drawing is also in a table under it.** A bubble is a button a keyboard
 * reaches, so hover and focus show the same numbers, and the screen's tables hold them all.
 */

/** One geography as the map draws it. */
export interface MapGeography {
  readonly key: string;
  readonly name: string;
  readonly resources: number;
  readonly accounts: number;
  /** The regions inside it this reader can see, named because the prefix cannot say more. */
  readonly regions: readonly string[];
  /** This month's Effective Cost, measured, or null where it was not read. */
  readonly cost: number | null;
  /** Pairs of resources joined to another region, summed over this geography's regions. */
  readonly links: number;
}

export interface WorldMapProps {
  readonly geographies: readonly MapGeography[];
  /** Links between two different geographies, which is all a map at continent grain can draw. */
  readonly links: readonly GeographyLink[];
  /**
   * Why no bubble is sized by this month's cost, which is loading or could not be read, or null
   * when every bubble is. Said in the caption, so equal bubbles are never read as equal costs.
   */
  readonly unsized: string | null;
  readonly freshness: Freshness;
  /** The geography whose resources are being listed, or null for none. */
  readonly selected: string | null;
  readonly onSelect: (key: string) => void;
}

//: Built once. Four and a half thousand dots are one path, and one path is one element.
const LAND = dotPath(ROWS, WORLD.pitch);

function plural(count: number, one: string, many: string): string {
  return `${count.toLocaleString('en-GB')} ${count === 1 ? one : many}`;
}

/** What a bubble says to a screen reader, which is what the tooltip says to a pointer. */
function spoken(one: MapGeography): string {
  const cost =
    one.cost === null
      ? 'Effective Cost not read'
      : `$${Math.round(one.cost).toLocaleString('en-GB')} Effective Cost this month`;
  return `${one.name}: ${cost}, ${plural(one.resources, 'resource', 'resources')}, ${plural(
    one.accounts,
    'account',
    'accounts',
  )}, ${plural(one.links, 'link', 'links')} to other regions`;
}

export function WorldMap({
  geographies,
  links,
  unsized,
  freshness,
  selected,
  onSelect,
}: WorldMapProps) {
  const glow = useId();
  const tip = useId();
  const [shown, setShown] = useState<string | null>(null);

  const placed = geographies.flatMap((one) => {
    const anchor = ANCHORS[one.key];
    return anchor === undefined ? [] : [{ one, at: project(anchor[0], anchor[1]) }];
  });
  const where = new Map(placed.map(({ one, at }) => [one.key, at]));
  const peak = placed.reduce((most, { one }) => Math.max(most, one.cost ?? 0), 0);
  const unplaced = geographies.filter((one) => ANCHORS[one.key] === undefined);
  const showing = placed.find(({ one }) => one.key === shown);

  const press = (key: string) => (event: KeyboardEvent<SVGGElement>) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      onSelect(key);
    }
  };

  return (
    <figure data-testid="world-map">
      <div data-testid="world-map-canvas">
        <svg
          viewBox={`0 0 ${String(WORLD.width)} ${String(WORLD.height)}`}
          role="group"
          aria-label="The estate by geography, on a world map"
        >
          <defs>
            <radialGradient id={glow}>
              <stop offset="0%" data-testid="world-map-glow-core" />
              <stop offset="100%" data-testid="world-map-glow-edge" />
            </radialGradient>
          </defs>
          <path data-testid="world-map-frame" d={FRAME} aria-hidden="true" />
          <path data-testid="world-map-land" d={LAND} aria-hidden="true" />
          <g data-testid="world-map-links" aria-hidden="true">
            {links.flatMap((link) => {
              const from = where.get(link.between[0]);
              const to = where.get(link.between[1]);
              return from === undefined || to === undefined
                ? []
                : [
                    <path
                      key={link.between.join(' ')}
                      data-testid="world-map-link"
                      data-between={link.between.join(' ')}
                      d={arc(from, to)}
                      strokeWidth={weightFor(link.links)}
                    />,
                  ];
            })}
          </g>
          {placed.map(({ one, at: [x, y] }) => {
            const radius = radiusFor(unsized === null ? one.cost : null, peak);
            return (
              <g
                key={one.key}
                data-testid="world-map-marker"
                data-key={one.key}
                data-selected={selected === one.key}
                role="button"
                tabIndex={0}
                aria-pressed={selected === one.key}
                aria-label={spoken(one)}
                aria-describedby={shown === one.key ? tip : undefined}
                onClick={() => {
                  onSelect(one.key);
                }}
                onKeyDown={press(one.key)}
                onMouseEnter={() => {
                  setShown(one.key);
                }}
                onMouseLeave={() => {
                  setShown(null);
                }}
                onFocus={() => {
                  setShown(one.key);
                }}
                onBlur={() => {
                  setShown(null);
                }}
              >
                <circle
                  data-testid="world-map-glow"
                  cx={x}
                  cy={y}
                  r={radius * 2}
                  fill={`url(#${glow})`}
                />
                <circle data-testid="world-map-bubble" cx={x} cy={y} r={radius} />
                <text data-testid="world-map-marker-name" x={x + radius + 6} y={y - 3}>
                  {one.name}
                </text>
                {/* The count beside the bubble, so the drawing reads without the table. */}
                <text data-testid="world-map-marker-count" x={x + radius + 6} y={y + 12}>
                  {plural(one.resources, 'resource', 'resources')}
                </text>
              </g>
            );
          })}
        </svg>
        {showing === undefined ? null : (
          <div
            id={tip}
            role="tooltip"
            data-testid="world-map-tooltip"
            // Below a bubble in the top half and above one in the bottom half, so it opens into
            // the map rather than off it, and held inside the map's width at either edge.
            data-side={showing.at[1] < WORLD.height / 2 ? 'below' : 'above'}
            style={{
              left: `${String(Math.min(85, Math.max(15, (showing.at[0] / WORLD.width) * 100)))}%`,
              top: `${String((showing.at[1] / WORLD.height) * 100)}%`,
            }}
          >
            <strong>{showing.one.name}</strong>
            {/* Dense, as in a table: the figure keeps its provenance, and its freshness is the
                screen's, said once above the map rather than inside every card. */}
            <DenseRegion>
              <dl>
                <dt>Effective Cost, this month</dt>
                <dd>
                  {showing.one.cost === null ? (
                    'Not read'
                  ) : (
                    <Figure
                      value={{ kind: 'measured', amount: showing.one.cost }}
                      freshness={freshness}
                    />
                  )}
                </dd>
                <dt>Resources</dt>
                <dd>{showing.one.resources.toLocaleString('en-GB')}</dd>
                <dt>Accounts</dt>
                <dd>{showing.one.accounts.toLocaleString('en-GB')}</dd>
                <dt>Regions</dt>
                {/* One unbreakable name each, so a list wraps between regions and never
                    inside one at its hyphen. */}
                <dd>
                  {showing.one.regions.map((region, index) => (
                    <span key={region} data-testid="world-map-tooltip-region">
                      {index === 0 ? '' : ', '}
                      {region}
                    </span>
                  ))}
                </dd>
                <dt>Links to other regions</dt>
                <dd>{showing.one.links.toLocaleString('en-GB')}</dd>
              </dl>
            </DenseRegion>
          </div>
        )}
      </div>

      <figcaption data-testid="world-map-caption">
        One bubble per geography, from region names: a region name says which continent it is in
        and never which city, so a bubble is a continent and not a datacentre.{' '}
        {unsized ?? 'Each is sized by its Effective Cost this month, by area.'} Lines join
        geographies whose resources are linked across regions.
        {unplaced.length > 0 ? (
          // Never dropped. A drawing that omits a continent reports a smaller estate.
          <span data-testid="world-map-unplaced">
            {' '}
            {unplaced.length === 1
              ? '1 geography is not on the drawing and is in the table below'
              : `${String(unplaced.length)} geographies are not on the drawing and are in the table below`}
            .
          </span>
        ) : null}
      </figcaption>
    </figure>
  );
}
