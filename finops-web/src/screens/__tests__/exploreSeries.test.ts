import { describe, expect, it } from 'vitest';

import { exploreQuery, lastDays, stacked } from '../exploreSeries';
import { exploreOf } from './fixtures';

describe('a Cost Explorer view', () => {
  it('is asked the way the Explorer asks it, so the two share one answer', () => {
    expect(exploreQuery()).toBe(exploreQuery({}));
    expect(exploreQuery({ period: '12m', granularity: 'monthly' })).toContain('period=12m');
  });

  it('names the last days ending today, today included', () => {
    expect(lastDays(30, new Date('2026-10-06T09:00:00Z'))).toEqual({
      start: '2026-09-07',
      end: '2026-10-06',
    });
  });
});

describe('stacking explore series', () => {
  it('keeps the largest named series and folds the rest with the route own everything else', () => {
    const shape = stacked(exploreOf(), 1, 'All other services');
    expect(shape.periods).toEqual(['2026-10-01', '2026-10-02']);
    expect(shape.series.map((one) => one.label)).toEqual(['AmazonEC2', 'All other services']);
    expect(shape.series[0]?.values).toEqual([1000, 1388.4]);
    expect(shape.series[1]?.values[0]).toBeCloseTo(1100, 2);
    expect(shape.series[1]?.values[1]).toBeCloseTo(1024.31, 2);
  });

  it('never calls the route everything else unallocated', () => {
    const shape = stacked(exploreOf(), 5, 'Everything else');
    expect(shape.series.map((one) => one.label)).toEqual([
      'AmazonEC2',
      'unallocated',
      'Everything else',
    ]);
    expect(shape.series[2]?.values).toEqual([600, 500]);
  });
});
