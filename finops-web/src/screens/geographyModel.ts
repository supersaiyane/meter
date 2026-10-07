import type { ApiExplore, ApiGeographyLink } from '../api/types';
import { inWords } from '../components/displayNames';
import { exploreQuery } from './exploreSeries';

/**
 * The Geography screen's arithmetic, FEAT-061 and TASK-P8-017. Pure, so every rule here is
 * tested without drawing a map.
 *
 * **No prefix rule lives here.** Which geography a region is in comes from the server, on the
 * geography route for resources and links and on Cost Explorer's answer for cost, because two
 * copies of that rule would one day put one region on two continents.
 */

/** The word Cost Explorer groups cost under when it carries no region, which is global by nature. */
export const NO_REGION = 'unallocated';

export interface GeographyCosts {
  /** This period's Effective Cost by geography key. Measured. */
  readonly now: ReadonlyMap<string, number>;
  /** The same days of the period before, by key, or null where it was never collected. */
  readonly before: ReadonlyMap<string, number> | null;
  /** The regions that carried cost, by key, which is what each tile's trend asks for. */
  readonly regions: ReadonlyMap<string, readonly string[]>;
  /** Each geography's name, including one with cost and no resources on the map. */
  readonly names: ReadonlyMap<string, string>;
  /** Cost carrying no region at all: global services, a fact about the service. */
  readonly global: number;
  /** Regions with cost whose prefix no table knows, each with what it cost. */
  readonly unplaced: readonly { readonly region: string; readonly cost: number }[];
  /** Groups past Cost Explorer's row limit and what they add up to, never silently dropped. */
  readonly omitted: { readonly groups: number; readonly cost: number };
}

/**
 * Cost Explorer's view by region, added up by geography. Every row lands somewhere: a geography,
 * the global line, or the unplaced list, so the parts always reconcile to the view's total.
 */
export function costsByGeography(view: ApiExplore): GeographyCosts {
  const now = new Map<string, number>();
  const before = view.previous_collected ? new Map<string, number>() : null;
  const regions = new Map<string, readonly string[]>();
  const names = new Map<string, string>();
  const unplaced: { region: string; cost: number }[] = [];
  let global = 0;
  for (const row of view.rows) {
    const cost = Number(row.this_period);
    if (row.first === NO_REGION) {
      global += cost;
      continue;
    }
    const placed = view.region_geographies[row.first];
    if (placed === undefined) {
      unplaced.push({ region: row.first, cost });
      continue;
    }
    now.set(placed.key, (now.get(placed.key) ?? 0) + cost);
    before?.set(placed.key, (before.get(placed.key) ?? 0) + Number(row.previous_period ?? 0));
    names.set(placed.key, placed.name);
    regions.set(placed.key, [...(regions.get(placed.key) ?? []), row.first]);
  }
  return {
    now,
    before,
    regions,
    names,
    global,
    unplaced,
    omitted: { groups: view.rows_omitted, cost: Number(view.omitted_this_period) },
  };
}

/** Links between two geographies, summed from the region pairs that join them. */
export interface GeographyLink {
  /** The two geography keys, in the order of the first region pair that named them. */
  readonly between: readonly [string, string];
  readonly links: number;
  readonly kinds: readonly string[];
}

interface LinkSum {
  readonly between: readonly [string, string];
  readonly links: number;
  readonly kinds: ReadonlySet<string>;
}

/**
 * The links a map at continent grain can draw: both ends placed, in two different geographies.
 * A link inside one geography, or to a region no table knows, is real and stays in the table.
 */
export function linksBetween(links: readonly ApiGeographyLink[]): readonly GeographyLink[] {
  const found = new Map<string, LinkSum>();
  for (const link of links) {
    const { one_geography: one, other_geography: other } = link;
    if (one === null || other === null || one === other) continue;
    const key = [one, other].sort().join(' ');
    const sum: LinkSum = found.get(key) ?? { between: [one, other], links: 0, kinds: new Set() };
    found.set(key, {
      between: sum.between,
      links: sum.links + link.links,
      kinds: new Set([...sum.kinds, ...link.kinds]),
    });
  }
  return [...found.values()].map((one) => ({
    between: one.between,
    links: one.links,
    kinds: [...one.kinds].sort(),
  }));
}

export const SMALLEST = 6;
export const LARGEST = 34;
/** Every bubble's size when the cost could not be read: one size, so none claims a share. */
export const UNSIZED = 12;

/**
 * A bubble's radius, by area rather than by radius. A geography costing four times another gets
 * four times the ink, and doubling the radius would claim sixteen. A measured nought is the
 * smallest bubble, a real figure; a cost that could not be read is never drawn as nought.
 */
export function radiusFor(cost: number | null, peak: number): number {
  if (cost === null) return UNSIZED;
  if (peak <= 0 || cost <= 0) return SMALLEST;
  return SMALLEST + Math.sqrt(Math.min(cost, peak) / peak) * (LARGEST - SMALLEST);
}

/** A curve between two bubbles, lifted towards the north so lines that share an end separate. */
export function arc(from: readonly [number, number], to: readonly [number, number]): string {
  const [x1, y1] = from;
  const [x2, y2] = to;
  const lift = Math.hypot(x2 - x1, y2 - y1) * 0.25;
  const at = (x: number, y: number): string => `${x.toFixed(1)} ${y.toFixed(1)}`;
  return `M${at(x1, y1)}Q${at((x1 + x2) / 2, (y1 + y2) / 2 - lift)} ${at(x2, y2)}`;
}

/** A line's weight, which grows with the count but slowly, so one busy pair does not drown the map. */
export function weightFor(links: number): number {
  return 1 + Math.min(4, Math.log2(Math.max(1, links)));
}

/** A view's points added up by day, in day order: every series, named or not, in one total. */
export function dailyTotals(view: ApiExplore | undefined): readonly number[] {
  if (view === undefined) return [];
  const byDay = new Map<string, number>();
  for (const point of view.points) {
    byDay.set(point.bucket, (byDay.get(point.bucket) ?? 0) + Number(point.cost));
  }
  return [...byDay.keys()].sort().map((day) => byDay.get(day) ?? 0);
}

/**
 * One geography's own Cost Explorer view: its regions, by day, over a window. The route takes a
 * column filter as the parameter repeated, up to twenty values, and no geography has twenty
 * regions.
 */
export function regionsQuery(
  regions: readonly string[],
  window: { readonly start: string; readonly end: string },
): string {
  const query = new URLSearchParams(
    exploreQuery({ period: 'custom', start: window.start, end: window.end, granularity: 'daily' }),
  );
  for (const region of regions) {
    query.append('region', region);
  }
  return query.toString();
}

/** Each kind of edge in words, because a code is not a sentence a reader can use. */
const KIND_WORDS: Readonly<Record<string, string>> = {
  PEERS_WITH: 'peering',
  ROUTES_TO: 'routing',
  TARGETS: 'load balancer target',
  ATTACHED_TO: 'attachment',
  PERMITS: 'security group rule',
  TRUSTS: 'trust',
  CONTAINS: 'containment',
};

export function kindName(kind: string): string {
  return KIND_WORDS[kind] ?? inWords(kind).toLowerCase();
}

/** Pairs of resources joined across a region boundary that touch one geography, each once. */
export function linksTouching(key: string, links: readonly ApiGeographyLink[]): number {
  return links
    .filter((link) => link.one_geography === key || link.other_geography === key)
    .reduce((total, link) => total + link.links, 0);
}
