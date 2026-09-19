import type { ApiCostDay, ApiCostSlice, ApiCostSummary, ApiEnvelope } from '../types';

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
