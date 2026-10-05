import { describe, expect, it } from 'vitest';

import { EXPLORER_FILTERS } from '../../shell/sections';
import {
  apiQuery,
  bucketLabel,
  bucketTotals,
  chartOf,
  chipsOf,
  dayLabel,
  dollars,
  filterTo,
  groupingChange,
  groupingName,
  groupingValue,
  notesFor,
  periodLine,
  signedDollars,
  tableRows,
  valueName,
  windowLabel,
  type ExploreValues,
} from '../exploreModel';
import { exploreOf } from './fixtures';

/** FEAT-065. Cost Explorer's rules, without rendering the screen. */

function valuesOf(partial: Partial<ExploreValues> = {}): ExploreValues {
  const empty = Object.fromEntries(EXPLORER_FILTERS.map((key) => [key, ''])) as ExploreValues;
  return { ...empty, ...partial };
}

describe('the address and the route', () => {
  it('hands the route nothing for the default view, so the route chooses the defaults', () => {
    expect(apiQuery(valuesOf())).toBe('');
  });

  it('hands the route the same names the address uses, the empty ones left out', () => {
    const values = valuesOf({ group_by: 'service', then_by: 'region', service: 'AmazonEC2' });
    expect(apiQuery(values)).toBe('group_by=service&then_by=region&service=AmazonEC2');
  });
});

describe('groupings', () => {
  it('names a column grouping by the column and a tag grouping by its key', () => {
    expect(groupingValue('region', '')).toBe('region');
    expect(groupingValue('tag', 'finops:module')).toBe('tag:finops:module');
  });

  it('turns a choice into the address, keeping a tag key that holds a colon whole', () => {
    expect(groupingChange('group_by', 'tag:finops:module')).toEqual({
      group_by: 'tag',
      group_by_tag: 'finops:module',
    });
    expect(groupingChange('then_by', 'region')).toEqual({ then_by: 'region', then_by_tag: '' });
  });

  it('calls a grouping what a reader would', () => {
    expect(groupingName({ dimension: 'account', tag_key: null })).toBe('Sub account');
    expect(groupingName({ dimension: 'tag', tag_key: 'team' })).toBe('Tag: team');
    expect(groupingName({ dimension: 'something new', tag_key: null })).toBe('something new');
  });

  it('names the unallocated bucket rather than showing the route its word', () => {
    expect(valueName('unallocated')).toBe('Unallocated');
    expect(valueName('AmazonEC2')).toBe('AmazonEC2');
  });
});

describe('filters', () => {
  it('filters to a column value, or to a tag key and value', () => {
    expect(filterTo({ dimension: 'service', tag_key: null }, 'AmazonEC2')).toEqual({
      service: 'AmazonEC2',
    });
    expect(filterTo({ dimension: 'tag', tag_key: 'team' }, 'payments')).toEqual({
      tag_key: 'team',
      tag_value: 'payments',
    });
    expect(filterTo({ dimension: 'something new', tag_key: null }, 'x')).toEqual({});
  });

  it('shows each filter in force as a chip that clears it', () => {
    const chips = chipsOf(
      valuesOf({ service: 'AmazonEC2', tag_key: 'team', tag_value: 'unallocated' }),
    );
    expect(chips.map((chip) => chip.label)).toEqual([
      'Service: AmazonEC2',
      'Tag team: Unallocated',
    ]);
    expect(chips.map((chip) => chip.clear)).toEqual([
      { service: '' },
      { tag_key: '', tag_value: '' },
    ]);
  });

  it('shows no chip for half a tag filter, because the route applies none', () => {
    expect(chipsOf(valuesOf({ tag_key: 'team' }))).toEqual([]);
  });
});

describe('dates', () => {
  it('says a window the way a reader would, naming a shared month or year once', () => {
    expect(windowLabel({ start: '2026-10-01', end: '2026-10-05' })).toBe('1 to 5 October 2026');
    expect(windowLabel({ start: '2026-08-01', end: '2026-10-05' })).toBe(
      '1 August to 5 October 2026',
    );
    expect(windowLabel({ start: '2025-11-01', end: '2026-10-05' })).toBe(
      '1 November 2025 to 5 October 2026',
    );
    expect(windowLabel({ start: '2026-10-05', end: '2026-10-05' })).toBe('5 October 2026');
  });

  it('labels a day by its date and a month by its name', () => {
    expect(dayLabel('2026-08-01')).toBe('1 August 2026');
    expect(bucketLabel('2026-10-02', 'daily')).toBe('2 Oct');
    expect(bucketLabel('2026-10-01', 'monthly')).toBe('Oct 2026');
  });

  it('says what the period is compared with, and says nothing of a comparison it cannot make', () => {
    expect(periodLine(exploreOf())).toBe(
      '1 to 5 October 2026, month to date, compared with 1 to 5 September 2026',
    );
    expect(periodLine(exploreOf({ previous_collected: false }))).toBe(
      '1 to 5 October 2026, month to date',
    );
  });
});

describe('what a reader has to know before trusting the totals', () => {
  it('says a period ending today is still open', () => {
    expect(notesFor(exploreOf())).toEqual([
      'The period ends today and is still open, so it is not yet a whole period.',
    ]);
    expect(notesFor(exploreOf({ is_open: false }))).toEqual([]);
  });

  it('says where the line items start when the period starts earlier', () => {
    const notes = notesFor(
      exploreOf({ is_open: false, collected_from: '2026-10-03', previous_collected: false }),
    );
    expect(notes[0]).toContain('Meter holds line items from 3 October 2026');
    expect(notes[1]).toContain('starts before 3 October 2026, the first day Meter holds');
  });

  it('says there is nothing before the period when nothing was ever collected', () => {
    const notes = notesFor(
      exploreOf({ is_open: false, collected_from: null, previous_collected: false }),
    );
    expect(notes).toEqual(['Meter holds no line items before this period, so it is not compared.']);
  });
});

describe('money', () => {
  it('is drawn to the cent, with the sign of a change said even when it rises', () => {
    expect(dollars(1234.5)).toBe('$1,234.50');
    expect(dollars(-15.34)).toBe('-$15.34');
    expect(signedDollars(309.61)).toBe('+$309.61');
    expect(signedDollars(-15.34)).toBe('-$15.34');
    expect(signedDollars(0)).toBe('$0.00');
  });
});

describe('the chart', () => {
  it('draws a series per named group, unallocated by name, and one for everything else', () => {
    const chart = chartOf(exploreOf());
    expect(chart.categories).toEqual(['1 Oct', '2 Oct']);
    expect(chart.series.map((series) => series.label)).toEqual([
      'AmazonEC2',
      'Unallocated',
      'Everything else',
    ]);
    expect(chart.series.map((series) => series.values)).toEqual([
      [1000, 1388.4],
      [500, 524.31],
      [600, 500],
    ]);
  });

  it('draws a day a group was not billed as nothing billed, not as a gap', () => {
    const explore = exploreOf({
      series: ['AmazonEC2'],
      points: [
        { bucket: '2026-10-01', series: 'AmazonEC2', cost: '10.00' },
        { bucket: '2026-10-02', series: null, cost: '5.00' },
      ],
    });
    expect(chartOf(explore).series.map((series) => series.values)).toEqual([
      [10, 0],
      [0, 5],
    ]);
  });

  it('totals each day for the trend line, oldest first', () => {
    const totals = bucketTotals(exploreOf());
    expect(totals.map((total) => total.toFixed(2))).toEqual(['2100.00', '2412.71']);
  });
});

describe('the table', () => {
  it('carries each row with its change against the period before', () => {
    const rows = tableRows(exploreOf());
    expect(rows.map((row) => [row.first, row.change?.toFixed(2)])).toEqual([
      ['AmazonEC2', '187.40'],
      ['unallocated', '112.21'],
      ['AmazonRDS', '10.00'],
      ['AmazonS3', '0.00'],
    ]);
  });

  it('adds one row for what the limit left out, so the totals still reconcile', () => {
    const rows = tableRows(
      exploreOf({ rows_omitted: 12, omitted_this_period: '40.00', omitted_previous_period: null }),
    );
    expect(rows.at(-1)).toMatchObject({
      first: '12 more rows',
      thisPeriod: 40,
      previousPeriod: null,
      change: null,
      rest: true,
    });
  });

  it('gives no change where the period before was never collected', () => {
    const rows = tableRows(
      exploreOf({
        previous_collected: false,
        rows: [{ first: 'AmazonEC2', second: null, this_period: '1.00', previous_period: null }],
      }),
    );
    expect(rows[0]).toMatchObject({ previousPeriod: null, change: null });
  });
});
