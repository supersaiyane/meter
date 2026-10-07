import { describe, expect, it } from 'vitest';

import type { ApiExploreRow, ApiGeographyLink } from '../../api/types';
import {
  LARGEST,
  SMALLEST,
  UNSIZED,
  arc,
  costsByGeography,
  dailyTotals,
  kindName,
  linksBetween,
  linksTouching,
  radiusFor,
  regionsQuery,
  weightFor,
} from '../geographyModel';
import { exploreOf } from './fixtures';

/**
 * The Geography screen's arithmetic, TASK-P8-017. Each figure is checked against inputs whose
 * answer is known, and each leftover is checked to land somewhere rather than vanish.
 */

function row(first: string, cost: string, previous: string | null = '0'): ApiExploreRow {
  return { first, second: null, this_period: cost, previous_period: previous };
}

const PLACES = {
  'us-east-1': { key: 'us', name: 'United States' },
  'us-west-2': { key: 'us', name: 'United States' },
  'eu-west-1': { key: 'eu', name: 'Europe' },
};

function link(
  one: string,
  other: string,
  oneGeography: string | null,
  otherGeography: string | null,
  links: number,
  kinds: readonly string[] = ['PEERS_WITH'],
): ApiGeographyLink {
  return {
    one_region: one,
    other_region: other,
    one_geography: oneGeography,
    other_geography: otherGeography,
    links,
    kinds,
  };
}

describe('cost by geography', () => {
  const view = exploreOf({
    rows: [
      row('us-east-1', '300.00', '200.00'),
      row('us-west-2', '100.00', '50.00'),
      row('eu-west-1', '80.00', '90.00'),
      row('unallocated', '25.00'),
      row('zz-north-9', '5.00'),
    ],
    region_geographies: PLACES,
    rows_omitted: 2,
    omitted_this_period: '3.50',
  });

  it('adds each region into its geography, this period and the one before', () => {
    const costs = costsByGeography(view);
    expect(costs.now.get('us')).toBe(400);
    expect(costs.now.get('eu')).toBe(80);
    expect(costs.before?.get('us')).toBe(250);
    expect(costs.regions.get('us')).toEqual(['us-east-1', 'us-west-2']);
    expect(costs.names.get('eu')).toBe('Europe');
  });

  it('lands every row somewhere: a geography, the global line or the unplaced list', () => {
    const costs = costsByGeography(view);
    expect(costs.global).toBe(25);
    expect(costs.unplaced).toEqual([{ region: 'zz-north-9', cost: 5 }]);
    expect(costs.omitted).toEqual({ groups: 2, cost: 3.5 });
    const placed = [...costs.now.values()].reduce((a, b) => a + b, 0);
    expect(placed + costs.global + 5).toBe(510);
  });

  it('has no period before when the period before was never collected', () => {
    expect(costsByGeography(exploreOf({ ...view, previous_collected: false })).before).toBeNull();
  });
});

describe('links between geographies', () => {
  it('sums the region pairs joining two geographies, whichever way round they are named', () => {
    const found = linksBetween([
      link('eu-west-1', 'us-east-1', 'eu', 'us', 3),
      link('us-west-2', 'eu-west-1', 'us', 'eu', 2, ['ROUTES_TO']),
    ]);
    expect(found).toEqual([{ between: ['eu', 'us'], links: 5, kinds: ['PEERS_WITH', 'ROUTES_TO'] }]);
  });

  it('draws no line inside one geography, or to a region no table places', () => {
    expect(
      linksBetween([
        link('us-east-1', 'us-west-2', 'us', 'us', 4),
        link('eu-west-1', 'zz-north-9', 'eu', null, 1),
      ]),
    ).toEqual([]);
  });

  it('counts each link touching a geography once, inside it included', () => {
    const links = [
      link('us-east-1', 'us-west-2', 'us', 'us', 4),
      link('eu-west-1', 'us-east-1', 'eu', 'us', 3),
    ];
    expect(linksTouching('us', links)).toBe(7);
    expect(linksTouching('eu', links)).toBe(3);
    expect(linksTouching('ap', links)).toBe(0);
  });

  it('names each kind of link in words', () => {
    expect(kindName('PEERS_WITH')).toBe('peering');
    expect(kindName('SOMETHING_NEW')).toBe('something new');
  });
});

describe('the drawing', () => {
  it('sizes by area, from a floor, and never past the largest', () => {
    expect(radiusFor(100, 100)).toBe(LARGEST);
    expect(radiusFor(25, 100)).toBeCloseTo(SMALLEST + (LARGEST - SMALLEST) / 2, 6);
    expect(radiusFor(0, 100)).toBe(SMALLEST);
    expect(radiusFor(5, 0)).toBe(SMALLEST);
    expect(radiusFor(null, 100)).toBe(UNSIZED);
  });

  it('curves a line north between two points', () => {
    expect(arc([0, 100], [100, 100])).toBe('M0.0 100.0Q50.0 75.0 100.0 100.0');
  });

  it('weighs a line by the log of its count, within bounds', () => {
    expect(weightFor(1)).toBe(1);
    expect(weightFor(4)).toBe(3);
    expect(weightFor(1_000_000)).toBe(5);
    expect(weightFor(0)).toBe(1);
  });
});

describe('a geography’s own view', () => {
  it('adds every series of a day into one total, in day order', () => {
    const view = exploreOf({
      points: [
        { bucket: '2026-10-02', series: 'AmazonEC2', cost: '2.00' },
        { bucket: '2026-10-01', series: 'AmazonEC2', cost: '1.00' },
        { bucket: '2026-10-01', series: null, cost: '0.50' },
      ],
    });
    expect(dailyTotals(view)).toEqual([1.5, 2]);
    expect(dailyTotals(undefined)).toEqual([]);
  });

  it('asks for its regions, each as the filter repeated, daily over the window', () => {
    const query = new URLSearchParams(
      regionsQuery(['us-east-1', 'us-west-2'], { start: '2026-09-07', end: '2026-10-06' }),
    );
    expect(query.getAll('region')).toEqual(['us-east-1', 'us-west-2']);
    expect(query.get('period')).toBe('custom');
    expect(query.get('granularity')).toBe('daily');
    expect(query.get('start')).toBe('2026-09-07');
  });
});
