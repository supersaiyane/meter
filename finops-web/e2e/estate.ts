import type { Page } from '@playwright/test';

/**
 * The demo estate, shared by every journey that needs a screen with its figures in it.
 *
 * It lived in demo.spec.ts until 2026-10-06, when the viewport journey needed the same
 * estate: a layout is only proven against content, and a second copy of these figures
 * would drift from the first.
 */

const META = {
  as_of: '2026-09-19T04:00:00Z',
  collected_at: '2026-09-20T06:22:00Z',
  scope_coverage: { visible: 5, total: 5, is_partial: false, unit: 'accounts' },
  degraded: false,
  failures: [],
};

const PAYER_META = {
  ...META,
  scope_coverage: { visible: 1, total: 1, is_partial: false, unit: 'payer' },
};

async function stub(page: Page, path: string, json: unknown): Promise<void> {
  await page.route(`**${path}*`, async (route) => {
    await route.fulfill({ json });
  });
}

/** The estate the runbook describes, at the grain each screen reads it. */
export async function demoEstate(page: Page): Promise<void> {
  await page.addInitScript(() => {
    window.localStorage.setItem('meter.token', 'a-session-token');
  });

  await stub(page, '/api/v1/cost/summary', {
    data: {
      current: {
        period: '2026-09-01',
        is_open: true,
        effective_cost: '3781.9335',
        billed_cost: '4102.5100',
        line_items: 455,
      },
      previous: {
        period: '2026-08-01',
        is_open: false,
        effective_cost: '6197.6500',
        billed_cost: '6500.0000',
        line_items: 700,
      },
      change: '-2415.7165',
    },
    meta: META,
  });

  // FEAT-045 through FEAT-067: the showback rows the Export screen shows and its menu writes.
  // They add up to the summary's Effective Cost, which is the claim the screen makes.
  await stub(page, '/api/v1/cost/showback', {
    data: [
      ['fake-platform-a', 'AmazonEC2', 'platform', '3281.9335', '3602.5100', 400],
      ['fake-product-b', 'AmazonS3', 'unallocated', '500.0000', '500.0000', 55],
    ].map(([account, service, tag, effective, billed, items]) => ({
      billing_period: '2026-09-01',
      account_id: account,
      service_name: service,
      tag_value: tag,
      effective_cost: effective,
      billed_cost: billed,
      line_items: items,
      as_of: META.as_of,
      collected_at: META.collected_at,
      accounts_in_file: 2,
      accounts_in_organization: 2,
    })),
    meta: META,
  });

  // Cost Explorer's answer for the same month the summary above describes, so the figure
  // the runbook opens on is the figure the explorer adds up to: $3,781.93.
  await stub(page, '/api/v1/cost/explore', {
    data: {
      metric: 'effective_cost',
      metrics_available: ['effective_cost', 'billed_cost'],
      period: 'mtd',
      granularity: 'daily',
      current: { start: '2026-09-01', end: '2026-09-19' },
      previous: { start: '2026-08-01', end: '2026-08-19' },
      is_open: true,
      collected_from: '2026-08-01',
      previous_collected: true,
      group_by: { dimension: 'service', tag_key: null },
      then_by: null,
      tag_keys: ['team'],
      total_this_period: '3781.9335',
      total_previous_period: '4103.2200',
      series: ['AmazonEC2', 'AmazonRDS', 'unallocated'],
      points: [
        { bucket: '2026-09-18', series: 'AmazonEC2', cost: '2043.1120' },
        { bucket: '2026-09-18', series: 'AmazonRDS', cost: '879.1794' },
        { bucket: '2026-09-19', series: 'unallocated', cost: '859.6421' },
      ],
      rows: [
        {
          first: 'AmazonEC2',
          second: null,
          this_period: '2043.1120',
          previous_period: '2400.0000',
        },
        {
          first: 'AmazonRDS',
          second: null,
          this_period: '879.1794',
          previous_period: '903.2200',
        },
        {
          first: 'unallocated',
          second: null,
          this_period: '859.6421',
          previous_period: '800.0000',
        },
      ],
      row_limit: 500,
      rows_omitted: 0,
      omitted_this_period: '0',
      omitted_previous_period: '0',
    },
    meta: META,
  });

  await stub(page, '/api/v1/cost/trend', {
    data: [
      { day: '2026-09-18', effective_cost: '186.9800' },
      { day: '2026-09-19', effective_cost: '292.0900' },
    ],
    meta: META,
  });

  await stub(page, '/api/v1/cost/allocation', {
    data: [
      {
        name: 'platform',
        effective_cost: '2138.9800',
        billed_cost: '2300.0000',
        line_items: 162,
      },
      // Named, never dropped. The runbook tells the driver to point at this row.
      {
        name: 'unallocated',
        effective_cost: '814.1700',
        billed_cost: '900.0000',
        line_items: 171,
      },
    ],
    meta: META,
  });

  await stub(page, '/api/v1/cost/anomalies', {
    data: {
      anomalies: [
        {
          account_id: 'fake-product-a',
          service_name: 'AmazonEC2',
          day: '2026-09-19',
          observed: '107.2560',
          baseline: '17.2610',
          delta: '89.9950',
          deviations: '313.6000',
          severity: 'MEDIUM',
          why: '+90.00 against a usual 17.26, which is 313.6 deviations out',
        },
      ],
      days_collected: 81,
      days_needed: 14,
    },
    meta: META,
  });

  await stub(page, '/api/v1/cost/commitments', {
    data: {
      window_start: '2026-09-01',
      window_end: '2026-10-01',
      commitments: [
        {
          commitment_id: 'fake-ri-rds',
          commitment_type: 'ReservedInstance',
          status: 'ACTIVE',
          term_start: '2026-03-01',
          term_end: '2027-03-01',
          committed: '791.2600',
          used: '490.5800',
          wasted: '300.6800',
          utilization: '0.6200',
        },
        {
          commitment_id: 'fake-sp-compute',
          commitment_type: 'SavingsPlan',
          status: 'ACTIVE',
          term_start: '2026-01-01',
          term_end: '2027-01-01',
          committed: '649.5700',
          used: '649.5700',
          wasted: '0.0000',
          utilization: '1.0000',
        },
      ],
      coverage: [
        {
          commitment_type: 'SavingsPlan',
          dimension: 'SERVICE',
          dimension_value: 'AmazonEC2',
          eligible_spend: '2043.1120',
          covered_spend: '822.7900',
          coverage: '0.4027',
        },
      ],
      wasted_total: '300.6800',
    },
    meta: PAYER_META,
  });

  // P3. Three surfaces, and each one carries the case it exists to render
  // honestly rather than a tidy row of successes.
  await stub(page, '/api/v1/waste/recommendations', {
    data: {
      recommendations: [
        {
          recommendation_id: '2f3c1d4e-5a6b-4c7d-8e9f-0a1b2c3d4e5f',
          account_id: 'fake-product-a',
          source: 'METER',
          waste_class: 'RIGHTSIZE_INSTANCE',
          resource_id: 'i-0a1b2c3d4e5f6a7b8',
          region_id: 'eu-west-1',
          estimated_monthly_saving: '412.6400',
          severity: 'HIGH',
          // Large money, low confidence. The pair the screen must not let a
          // reader collapse into one judgement.
          confidence: 'LOW',
          observation_days: 15,
          lifecycle: 'OPEN',
          owner: null,
          ticket_reference: null,
          rationale: 'p99 CPU of 11.4 percent against 4 vCPU over 15 days, so 1 vCPU',
        },
      ],
      unowned: 1,
    },
    meta: META,
  });

  await stub(page, '/api/v1/waste/savings', {
    data: {
      savings: [
        {
          recommendation_id: '3a4b5c6d-7e8f-4a0b-9c1d-2e3f4a5b6c7d',
          cost_before: '540.0000',
          cost_after: '324.0000',
          usage_before: null,
          usage_after: null,
          verdict: 'INCONCLUSIVE',
          why: 'The billing rows carry no usage quantity for this resource, so there is no control. Unobserved, not zero',
          window_before_start: '2026-05-24',
          window_after_end: '2026-08-22',
        },
      ],
      by_verdict: {
        VERIFIED: { count: 1, realized_monthly: '192.0000' },
        INCONCLUSIVE: { count: 1, realized_monthly: '216.0000' },
      },
    },
    meta: META,
  });

  await stub(page, '/api/v1/waste/score', {
    data: {
      scores: [
        {
          account_id: 'fake-product-a',
          total: 54,
          available_weight: 85,
          why: '54 out of 100, from 3 of 4 components carrying 85 of 100 weight',
          components: [
            {
              name: 'waste',
              points: '22.400',
              weight: 40,
              why: '412.64 of identified monthly saving against 9380.00 of spend',
              findings: ['2f3c1d4e-5a6b-4c7d-8e9f-0a1b2c3d4e5f'],
            },
            {
              name: 'verification',
              points: null,
              weight: 15,
              why: 'Nothing has been verified either way',
              findings: [],
            },
          ],
          as_of: '2026-09-21T06:00:00+00:00',
        },
      ],
      unscored: ['fake-sandbox-c'],
    },
    meta: META,
  });
}
