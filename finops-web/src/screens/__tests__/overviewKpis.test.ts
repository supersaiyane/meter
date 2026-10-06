import { describe, expect, it } from 'vitest';

import { costBudgetsFixture } from '../../api/fixtures/cost';
import type { ApiCommitments, ApiCostSlice, ApiRecommendation } from '../../api/types';
import {
  budgetConsumed,
  commitmentCoverage,
  costAllocated,
  dailyPace,
  effectiveCost,
  effectiveSavingsRate,
  estateBudget,
  forecastToMonthEnd,
  mostAtRisk,
  openRecommendations,
  rankedRows,
  savingsByCategory,
  topMovers,
} from '../overviewKpis';
import { exploreOf, forecastOf } from './fixtures';

/**
 * The Overview's figures, FEAT-070. Each is arithmetic over a route another screen reads, so each
 * is checked here against fixtures whose numbers are known, and each figure the data cannot
 * support is checked to carry no number at all.
 */

const BUDGETS = costBudgetsFixture().data.budgets;

function commitments(partial: Partial<ApiCommitments> = {}): ApiCommitments {
  return {
    window_start: '2026-09-01',
    window_end: '2026-10-01',
    commitments: [
      { committed: '600.00', used: '450.00' },
      { committed: '400.00', used: '300.00' },
    ],
    coverage: [
      { eligible_spend: '1000.00', covered_spend: '400.00' },
      { eligible_spend: '1000.00', covered_spend: '600.00' },
    ],
    actions: [],
    wasted_total: '250.00',
    ...partial,
  } as ApiCommitments;
}

describe('effective cost to date', () => {
  it('is the month to date total against the same days last month', () => {
    const kpi = effectiveCost(exploreOf());
    expect(kpi.value).toBe(4512.71);
    expect(kpi.previous).toBe(4203.1);
    expect(kpi.period).toBe('1 September to 5 September');
    expect(kpi.formula).toContain('1 October to 5 October');
  });

  it('has no change when the month before was never collected', () => {
    expect(effectiveCost(exploreOf({ previous_collected: false })).previous).toBeNull();
  });

  it('has no figure before the view arrives', () => {
    expect(effectiveCost(undefined).value).toBeNull();
  });
});

describe('budgets', () => {
  it('shows the budget furthest ahead of its calendar, not the biggest one', () => {
    expect(mostAtRisk(BUDGETS)?.name).toBe('Platform team');
    const kpi = budgetConsumed(BUDGETS);
    expect(kpi.value).toBe(1.067);
    expect(kpi.note).toBe('83.3% of the period gone, Platform team');
  });

  it('has no figure when no budget has a number', () => {
    expect(budgetConsumed([]).value).toBeNull();
  });

  it('finds the one budget covering every account, and refuses to pick between two', () => {
    expect(estateBudget(BUDGETS)?.name).toBe('Cloud, all accounts');
    const estate = BUDGETS.find((one) => one.scope === 'ALL');
    expect(estate).toBeDefined();
    if (estate === undefined) return;
    expect(estateBudget([...BUDGETS, { ...estate, budget_id: 'second' }])).toBeNull();
  });

  it('paces the estate budget across its own days, the end exclusive', () => {
    const pace = dailyPace(estateBudget(BUDGETS), ['2026-09-29', '2026-09-30', '2026-10-01']);
    expect(pace).toEqual([12500 / 30, 12500 / 30, null]);
    expect(dailyPace(null, ['2026-09-30'])).toBeUndefined();
  });
});

describe('the forecast to month end', () => {
  it('is the interval, set against the estate budget', () => {
    const kpi = forecastToMonthEnd(forecastOf(), estateBudget(BUDGETS));
    expect(kpi.range).toEqual({ low: 15000, high: 16000 });
    expect(kpi.note).toBe('120.0% to 128.0% of the Cloud, all accounts budget');
    expect(kpi.formula).toBe(
      "The weekday profile forecast's 80 percent interval, billed through 4 October",
    );
  });

  it('carries the forecast own reason when it was withheld, and no figure', () => {
    const withheld = forecastOf({
      month_end: {
        month: '2026-10-01',
        figure: null,
        withheld: 'Too few months held out to test the range',
        median_miss: null,
        held_out: 1,
      },
    });
    const kpi = forecastToMonthEnd(withheld, null);
    expect(kpi.value).toBeNull();
    expect(kpi.unsupported).toBe('Too few months held out to test the range');
  });
});

describe('the effective savings rate', () => {
  it('is one minus effective cost over list cost', () => {
    const kpi = effectiveSavingsRate(exploreOf(), exploreOf({ total_this_period: '6000.00' }));
    expect(kpi.value).toBeCloseTo(1 - 4512.71 / 6000, 6);
    expect(kpi.formula).toContain('on demand equivalent');
  });

  it('says why when the bill carries no list cost, and shows no figure', () => {
    const kpi = effectiveSavingsRate(
      exploreOf({ metrics_available: ['effective_cost', 'billed_cost'] }),
      undefined,
    );
    expect(kpi.value).toBeNull();
    expect(kpi.unsupported).toContain('no List Cost');
  });
});

describe('commitment coverage', () => {
  it('is covered spend over the spend commitments could cover, with their utilization', () => {
    const kpi = commitmentCoverage(commitments());
    expect(kpi.value).toBe(0.5);
    expect(kpi.note).toBe('Utilization 75.0%');
  });

  it('has no figure when nothing could have been covered', () => {
    expect(commitmentCoverage(commitments({ coverage: [] })).value).toBeNull();
  });
});

describe('cost allocated', () => {
  const slices = [
    { name: 'payments', effective_cost: '750.00' },
    { name: 'unallocated', effective_cost: '250.00' },
  ] as ApiCostSlice[];

  it('is the share carrying the tag, and names what is left', () => {
    const kpi = costAllocated(slices, 'team');
    expect(kpi.value).toBe(0.75);
    expect(kpi.note).toBe('$250 unallocated, by the team tag');
  });

  it('has no figure for an empty period', () => {
    expect(costAllocated([], 'team').value).toBeNull();
  });
});

describe('rankings', () => {
  it('names the services that moved most, either way', () => {
    const movers = topMovers(exploreOf(), 2);
    expect(movers.map((one) => one.name)).toEqual(['AmazonEC2', 'unallocated']);
    expect(movers[0]?.change).toBeCloseTo(187.4, 2);
    expect(movers[1]?.change).toBeCloseTo(112.21, 2);
  });

  it('ranks rows by this period, the largest first', () => {
    expect(rankedRows(exploreOf()).map((row) => row.label)).toEqual([
      'AmazonEC2',
      'unallocated',
      'AmazonRDS',
      'AmazonS3',
    ]);
  });

  it('keeps the recommendations still waiting on somebody, and nothing already acted on', () => {
    const all = ['OPEN', 'ACCEPTED', 'REJECTED', 'DONE', 'OPEN'].map((lifecycle, index) => ({
      recommendation_id: String(index),
      lifecycle,
    })) as ApiRecommendation[];
    expect(openRecommendations(all).map((one) => one.recommendation_id)).toEqual(['0', '4']);
  });

  it('sums the open savings by category, never what was accepted, done or realized', () => {
    const open = [
      {
        waste_class: 'RIGHTSIZE_INSTANCE',
        estimated_monthly_saving: '100.00',
        lifecycle: 'OPEN',
      },
      { waste_class: 'IDLE_INSTANCE', estimated_monthly_saving: '70.00', lifecycle: 'OPEN' },
      {
        waste_class: 'RIGHTSIZE_INSTANCE',
        estimated_monthly_saving: '50.00',
        lifecycle: 'OPEN',
      },
      {
        waste_class: 'RIGHTSIZE_INSTANCE',
        estimated_monthly_saving: '900.00',
        lifecycle: 'ACCEPTED',
      },
      { waste_class: 'EBS_UNATTACHED', estimated_monthly_saving: '40.00', lifecycle: 'DONE' },
    ] as ApiRecommendation[];
    expect(savingsByCategory(open)).toEqual([
      { label: 'Rightsizing', value: 150 },
      { label: 'Idle instance', value: 70 },
    ]);
  });
});
