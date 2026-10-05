import { expect, test, type Page } from '@playwright/test';

/**
 * The walk in `docs/runbooks/demo.md`, in the order somebody demonstrates it.
 *
 * The other specs each prove one arc. This one exists for a different reason: a screen
 * that breaks between releases should fail the build rather than the demo, in front of
 * an audience, with no way to tell whether it is the product or the laptop.
 *
 * So it asserts a figure on every screen the runbook points at, and the distinctions
 * the runbook tells the driver to say out loud. If a number stops rendering, or the
 * commitments screen stops drawing the distinction it exists for, this goes red and
 * the runbook is wrong before anybody reads it.
 *
 * Stubbed at the network boundary like every other journey, against the real
 * production bundle.
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
async function demoEstate(page: Page): Promise<void> {
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

test('the demo walk reaches every screen the runbook points at', async ({ page }) => {
  await demoEstate(page);

  // 1. Home. The spend tile is the figure the runbook opens on, and it is the same
  // figure the spend screen shows, because Home reads that screen's own hook.
  await page.goto('/');
  await expect(page.getByTestId('home-spend')).toContainText('3,781.93');
  await expect(page.getByRole('link', { name: /Effective Cost/ })).toBeVisible();
  // P1 filled three home slots and left them saying "arrives with P1" until
  // 2026-09-20, on the front page of the demo.
  await expect(page.getByText('P1 Cost Intelligence')).toHaveCount(0);

  // 2. Cost Explorer. The open period says so rather than presenting a part month
  // as a total.
  await page.goto('/analyze/explorer');
  await expect(page.getByText(/still open/i)).toBeVisible();
  await expect(page.getByText('AmazonEC2').first()).toBeVisible();

  // 3. Allocation. The unallocated bucket is a named row, and the name is a sentence
  // rather than the API's key: an empty cell reads as a rendering fault and sends
  // somebody looking for a value that was never there.
  await page.goto('/analyze/allocation');
  await expect(page.getByTestId('allocation-unallocated')).toHaveText('Unallocated cost');
  await expect(page.getByText('814.17')).toBeVisible();

  // 4. Anomalies. The working is shown whole, because a verdict a reader cannot argue
  // with is one they have to take on trust.
  await page.goto('/analyze/anomalies');
  await expect(page.getByText(/313\.6 deviations out/)).toBeVisible();
  await expect(page.getByTestId('anomaly-judged')).toBeVisible();

  // 5. Commitments. The distinction the screen exists to draw, which is the thirty
  // seconds the runbook calls the best in the demo.
  await page.goto('/optimize/commitments');
  await expect(page.getByTestId('utilization-fake-sp-compute')).toHaveText('100.0%');
  await expect(page.getByTestId('coverage-AmazonEC2')).toHaveText('40.3%');
  await expect(page.getByTestId('commitment-waste')).toContainText('300.68');
  await expect(page.getByTestId('commitment-scope-note')).toContainText(/whole payer/i);

  // 6. Export. The screen states the total the file must sum to, which is what makes
  // the claim checkable in ten seconds, shows the rows, and the Export menu beside the
  // title offers them as a workbook or a CSV. FEAT-067.
  await page.goto('/report/exports');
  await expect(page.getByTestId('export-claim')).toContainText('3,781.93');
  await expect(page.getByTestId('export-unallocated-row')).toHaveText('Unallocated cost');
  await page.getByTestId('export-menu').getByText('Export').click();
  await expect(page.getByRole('group', { name: 'Showback' })).toBeVisible();

  // 7. Recommendations. The estimate is labelled modelled, and the finding
  // nobody owns says so in words rather than leaving a cell blank.
  await page.goto('/optimize');
  await expect(page.getByText('412.64')).toBeVisible();
  await expect(page.getByTestId('unowned-2f3c1d4e-5a6b-4c7d-8e9f-0a1b2c3d4e5f')).toHaveText(
    'nobody yet',
  );
  await expect(
    page.getByTestId('confidence-2f3c1d4e-5a6b-4c7d-8e9f-0a1b2c3d4e5f'),
  ).toContainText('LOW on 15 days');

  // 8. Realized savings. The screen allowed to disappoint, and the inconclusive
  // row is the one the runbook tells the driver to stop on.
  await page.goto('/optimize/savings');
  await expect(page.getByTestId('total-VERIFIED')).toBeVisible();
  await expect(page.getByTestId('total-INCONCLUSIVE')).toBeVisible();
  await expect(
    page.getByTestId('unobserved-3a4b5c6d-7e8f-4a0b-9c1d-2e3f4a5b6c7d'),
  ).toContainText('not published');

  // 9. The score, with its parts on the same page. A component nobody could
  // compute says so rather than scoring nought.
  await page.goto('/plan/score');
  await expect(page.getByTestId('score-fake-product-a')).toContainText(
    'out of 85 available weight',
  );
  await expect(page.getByTestId('component-absent-verification')).toContainText(
    'rather than counted as nought',
  );
  await expect(page.getByTestId('unscored-fake-sandbox-c')).toBeVisible();
});

test('the P3 walk keeps the estimate and the realization on separate screens', async ({
  page,
}) => {
  /**
   * TASK-P3-014 against the real bundle. The two figures are different kinds of
   * number, and the whole of FEAT-029 rests on nobody adding them. A screen
   * carrying both would make that one subtraction away.
   */
  await demoEstate(page);

  await page.goto('/optimize');
  // Lower cased, because the table headers render through a text transform and
  // innerText returns what is painted rather than what the source says.
  const recommendations = (await page.locator('body').innerText()).toLowerCase();
  expect(recommendations).toContain('412.64');
  expect(recommendations).not.toContain('cost before');

  await page.goto('/optimize/savings');
  const savings = (await page.locator('body').innerText()).toLowerCase();
  expect(savings).toContain('cost before');
  expect(savings).not.toContain('412.64');
});

test('the commitments screen never puts the two percentages side by side', async ({ page }) => {
  // The one layout rule this feature rests on, asserted against the real bundle rather
  // than against jsdom. Two percentages meaning opposite things, adjacent, would be
  // compared by any reader, and the comparison is meaningless.
  await demoEstate(page);
  await page.goto('/optimize/commitments');

  const row = page.locator('tr', { has: page.getByTestId('utilization-fake-sp-compute') });
  await expect(row.locator('[data-testid^="coverage-"]')).toHaveCount(0);

  await expect(page.getByTestId('utilization-means')).toContainText(
    /what we paid for was used/i,
  );
  await expect(page.getByTestId('coverage-means')).toContainText(/estate is on a commitment/i);
});
