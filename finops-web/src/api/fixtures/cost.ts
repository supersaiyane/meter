import type {
  ApiCommitments,
  ApiCostAnomalies,
  ApiCostDay,
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

function meta(visible: number) {
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

export function costByServiceFixture(): ApiEnvelope<ApiCostSlice[]> {
  return {
    data: [
      {
        name: 'AmazonEC2',
        effective_cost: '2388.4032',
        billed_cost: '2579.4755',
        line_items: 115,
      },
      {
        name: 'AmazonRDS',
        effective_cost: '1074.7814',
        billed_cost: '1160.7639',
        line_items: 115,
      },
      {
        name: 'AmazonCloudWatch',
        effective_cost: '543.3062',
        billed_cost: '586.7707',
        line_items: 115,
      },
      {
        name: 'AmazonS3',
        effective_cost: '358.2605',
        billed_cost: '386.9213',
        line_items: 115,
      },
      {
        name: 'AWSLambda',
        effective_cost: '149.2752',
        billed_cost: '161.2172',
        line_items: 115,
      },
    ],
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

export function costTrendFixture(): ApiEnvelope<ApiCostDay[]> {
  const days: ApiCostDay[] = [];
  for (let index = 0; index < 23; index += 1) {
    const day = String(index + 1).padStart(2, '0');
    // A slow rise, matching what the fake estate actually produces, so a chart
    // drawn from this looks like a chart drawn from the real thing.
    days.push({
      day: `2026-08-${day}`,
      effective_cost: (193.1 + index * 0.9655).toFixed(4),
    });
  }
  return { data: days, meta: meta(5) };
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
