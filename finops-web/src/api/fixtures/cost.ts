import type {
  ApiBudgets,
  ApiCommitments,
  ApiCostAnomalies,
  ApiCostSlice,
  ApiCostSummary,
  ApiEnvelope,
} from '../types';

/**
 * A bill for a screen whose API is unreachable, and for tests that need one.
 *
 * These stand in through the same seam every other surface uses. They are
 * deliberately not round numbers: a fixture full of hundreds makes an
 * arithmetic mistake on the screen invisible, because every wrong answer also
 * looks like a round number.
 *
 * The open period here holds fewer days than a whole month, and its total is
 * therefore lower than the month before it. That is exactly the case the open
 * period label exists for, and a fixture without it lets the label look
 * decorative.
 */

const AS_OF = '2026-08-24T06:00:00Z';
const COLLECTED_AT = '2026-08-24T06:05:00Z';

/**
 * Shared by the P3 fixtures too, so every offline surface carries the same two
 * timestamps. Constraint 10 in a fixture rather than only in production.
 */
export function meta(visible: number) {
  return {
    as_of: AS_OF,
    collected_at: COLLECTED_AT,
    scope_coverage: { visible, total: visible, is_partial: false, unit: 'accounts' },
    degraded: false,
    failures: [],
  };
}

export function costSummaryFixture(): ApiEnvelope<ApiCostSummary> {
  return {
    data: {
      current: {
        period: '2026-08-01',
        is_open: true,
        effective_cost: '4512.7113',
        billed_cost: '4873.7282',
        line_items: 575,
      },
      previous: {
        period: '2026-07-01',
        is_open: false,
        effective_cost: '6197.6544',
        billed_cost: '6693.4668',
        line_items: 775,
      },
      // Negative, because a part month is smaller than a whole one. The screen
      // has to say why, or this reads as spending having collapsed.
      change: '-1684.9431',
    },
    meta: meta(5),
  };
}

export function costByAccountFixture(): ApiEnvelope<ApiCostSlice[]> {
  return {
    data: [
      {
        name: 'fake-platform-a',
        effective_cost: '1808.2131',
        billed_cost: '1952.8701',
        line_items: 115,
      },
      {
        name: 'fake-platform-b',
        effective_cost: '1121.0921',
        billed_cost: '1210.7794',
        line_items: 115,
      },
      {
        name: 'fake-product-a',
        effective_cost: '741.3673',
        billed_cost: '800.6766',
        line_items: 115,
      },
      {
        name: 'fake-product-b',
        effective_cost: '506.3000',
        billed_cost: '546.8040',
        line_items: 115,
      },
      // On the bill although Meter cannot assume a role into it, because the
      // bill comes from the payer. Unreadable and unbilled are different facts.
      {
        name: 'fake-product-denied',
        effective_cost: '271.2539',
        billed_cost: '292.9542',
        line_items: 115,
      },
    ],
    meta: meta(5),
  };
}

export function costAllocationFixture(): ApiEnvelope<ApiCostSlice[]> {
  return {
    data: [
      {
        name: 'platform',
        effective_cost: '2382.9683',
        billed_cost: '2573.6058',
        line_items: 184,
      },
      // Second largest on purpose. An allocation fixture where everything is
      // attributed lets the screen look finished while never rendering the row
      // that matters.
      {
        name: 'unallocated',
        effective_cost: '1366.5155',
        billed_cost: '1475.8367',
        line_items: 276,
      },
      { name: 'product', effective_cost: '763.4322', billed_cost: '824.5068', line_items: 115 },
    ],
    meta: meta(5),
  };
}

export function costCommitmentsFixture(): ApiEnvelope<ApiCommitments> {
  return {
    data: {
      window_start: '2026-09-01',
      window_end: '2026-10-01',
      commitments: [
        {
          // Over bought. The coverage looks healthy and the purchase was still a
          // mistake, which is the pair of readings this screen exists to separate.
          commitment_id: 'fake-ri-rds',
          commitment_type: 'ReservedInstance',
          status: 'ACTIVE',
          term_start: '2026-03-01',
          term_end: '2027-03-01',
          committed: '967.0100',
          used: '599.5500',
          wasted: '367.4600',
          utilization: '0.6200',
        },
        {
          // Fully consumed and under committed. Reading utilization alone says the
          // purchase was correct; its service is under half covered.
          commitment_id: 'fake-sp-compute',
          commitment_type: 'SavingsPlan',
          status: 'ACTIVE',
          term_start: '2026-01-01',
          term_end: '2027-01-01',
          committed: '761.0700',
          used: '761.0700',
          wasted: '0.0000',
          utilization: '1.0000',
        },
        {
          commitment_id: 'fake-sp-expired',
          commitment_type: 'SavingsPlan',
          status: 'EXPIRED',
          term_start: '2025-08-01',
          term_end: '2026-09-15',
          committed: '202.9500',
          used: '202.9500',
          wasted: '0.0000',
          utilization: '1.0000',
        },
        {
          // Null on purpose. It has not started, and zero would say the whole
          // commitment was wasted.
          commitment_id: 'fake-sp-queued',
          commitment_type: 'SavingsPlan',
          status: 'QUEUED',
          term_start: '2026-10-01',
          term_end: '2027-10-01',
          committed: '0.0000',
          used: '0.0000',
          wasted: '0.0000',
          utilization: null,
        },
      ],
      coverage: [
        {
          commitment_type: 'SavingsPlan',
          dimension: 'SERVICE',
          dimension_value: 'AmazonEC2',
          eligible_spend: '2387.6760',
          covered_spend: '964.0200',
          coverage: '0.4037',
        },
        {
          commitment_type: 'ReservedInstance',
          dimension: 'SERVICE',
          dimension_value: 'AmazonRDS',
          eligible_spend: '1074.4542',
          covered_spend: '599.5500',
          coverage: '0.5580',
        },
        {
          // Eligible and entirely uncovered, which is a zero and says buy.
          commitment_type: 'SavingsPlan',
          dimension: 'SERVICE',
          dimension_value: 'AWSLambda',
          eligible_spend: '149.2298',
          covered_spend: '0.0000',
          coverage: '0.0000',
        },
      ],
      // FEAT-055. The coverage above as things somebody owns. Deliberately one action rather
      // than one per coverage row: most gaps fall below the configured minimum saving, and a
      // fixture where every gap became an action would hide that the floor exists.
      actions: [
        {
          commitment_type: 'SAVINGS_PLAN',
          dimension: 'SERVICE',
          dimension_value: 'AmazonEC2',
          window_start: '2026-09-01',
          window_end: '2026-10-01',
          eligible_spend: '18400.0000',
          covered_spend: '7360.0000',
          estimated_monthly_saving: '3360.7200',
          usage_floor_percent: '70.0',
          term_months: 12,
          confidence: 'MEDIUM',
          severity: 'CRITICAL',
          lifecycle: 'OPEN',
          // Unowned, which is the state ISS-021 says a finding dies in.
          owner: null,
          rationale:
            '40.0 percent of eligible SERVICE spend for AmazonEC2 was covered by a ' +
            'commitment between 2026-09-01 and 2026-10-01, leaving 11040.0000 USD uncovered ' +
            'over that window. Covering it would save about 3360.7200 USD a month, modelled ' +
            'from a configured discount rather than from a quote. A commitment obligates 12 ' +
            'months whether or not the usage continues, so this is worth doing while usage ' +
            "stays above 70.0 percent of today's for the whole term, and costs more than it " +
            'saves below that.',
        },
      ],
      wasted_total: '367.4600',
    },
    meta: meta(4),
  };
}

export function costAnomaliesFixture(): ApiEnvelope<ApiCostAnomalies> {
  return {
    data: {
      anomalies: [
        {
          account_id: 'fake-product-a',
          service_name: 'AmazonEC2',
          day: '2026-09-18',
          observed: '742.1900',
          baseline: '191.4400',
          delta: '550.7500',
          deviations: '9.2000',
          severity: 'HIGH',
          why: '+550.75 against a usual 191.44, which is 9.2 deviations out',
        },
        {
          account_id: 'fake-platform-b',
          service_name: 'AmazonCloudWatch',
          day: '2026-09-18',
          observed: '96.3100',
          baseline: '52.8800',
          delta: '43.4300',
          // Null on purpose: a perfectly steady baseline, which the fake estate
          // produces and a real one sometimes does. The screen has to render
          // the absence rather than a zero.
          deviations: null,
          severity: 'MEDIUM',
          why: '+43.43 against a steady 52.88, a baseline that had not moved in 14 days',
        },
      ],
      days_collected: 81,
      days_needed: 14,
    },
    meta: meta(5),
  };
}

/**
 * Budgets, offline. FEAT-060.
 *
 * Four, and only two of them join. That ratio is the point: the first thing a finance reader
 * asks is how many of their budgets this product can actually track, and a fixture where
 * everything joined would leave the answer rendered by nothing a developer opens. One of the
 * two that join is already over, because a demo where every budget is green shows the one
 * state nobody needs a tool for.
 */
export function costBudgetsFixture(): ApiEnvelope<ApiBudgets> {
  return {
    data: {
      period: '2026-09-01',
      budgets: [
        {
          budget_id: 'Cloud, all accounts',
          name: 'Cloud, all accounts',
          scope: 'ALL',
          scope_value: '',
          limit: '12500.0000',
          currency: 'USD',
          period_start: '2026-09-01',
          period_end: '2026-10-01',
          actual: '11907.6863',
          status: 'AT_RISK',
          elapsed: '0.8333',
          used: '0.9526',
        },
        {
          budget_id: 'Platform team',
          name: 'Platform team',
          scope: 'ACCOUNT',
          scope_value: 'fake-platform-a',
          limit: '6000.0000',
          currency: 'USD',
          period_start: '2026-09-01',
          period_end: '2026-10-01',
          actual: '6402.1100',
          status: 'OVER',
          elapsed: '0.8333',
          used: '1.0670',
        },
        {
          // A tag expression. Read, counted, never matched to a number, because the slice it
          // describes is not one this product computes.
          budget_id: 'Cost centre 4471',
          name: 'Cost centre 4471',
          scope: 'UNSUPPORTED',
          scope_value: '',
          limit: '9000.0000',
          currency: 'USD',
          period_start: '2026-09-01',
          period_end: '2026-10-01',
          actual: null,
          status: 'UNKNOWN',
          elapsed: '0.8333',
          used: null,
        },
        {
          budget_id: 'EC2 hours',
          name: 'EC2 hours',
          scope: 'UNSUPPORTED',
          scope_value: '',
          limit: '40000.0000',
          currency: 'USD',
          period_start: '2026-09-01',
          period_end: '2026-10-01',
          actual: null,
          status: 'UNKNOWN',
          elapsed: '0.8333',
          used: null,
        },
      ],
      unsupported: 2,
    },
    meta: {
      as_of: '2026-09-26T06:00:00Z',
      collected_at: '2026-09-26T06:05:00Z',
      scope_coverage: { visible: 1, total: 1, is_partial: false, unit: 'accounts' },
      degraded: false,
      failures: [],
    },
  };
}
