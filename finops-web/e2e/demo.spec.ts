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

  await stub(page, '/api/v1/cost/by-service', {
    data: [
      {
        name: 'AmazonEC2',
        effective_cost: '2043.1120',
        billed_cost: '2306.5600',
        line_items: 95,
      },
      {
        name: 'AmazonRDS',
        effective_cost: '879.1794',
        billed_cost: '949.1100',
        line_items: 95,
      },
    ],
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
}

test('the demo walk reaches every screen the runbook points at', async ({ page }) => {
  await demoEstate(page);

  // 1. Home. The spend tile is the figure the runbook opens on, and it is the same
  // figure the spend screen shows, because Home reads that screen's own hook.
  await page.goto('/');
  await expect(page.getByTestId('home-spend')).toContainText('3,781.93');
  await expect(page.getByRole('link', { name: /Total spend/ })).toBeVisible();
  // P1 filled three home slots and left them saying "arrives with P1" until
  // 2026-09-20, on the front page of the demo.
  await expect(page.getByText('P1 Cost Intelligence')).toHaveCount(0);

  // 2. Spend and trend. The open period says so rather than presenting a part month
  // as a total.
  await page.goto('/cost');
  await expect(page.getByText(/still open/i)).toBeVisible();
  await expect(page.getByText('AmazonEC2').first()).toBeVisible();

  // 3. Allocation. The unallocated bucket is a named row, and the name is a sentence
  // rather than the API's key: an empty cell reads as a rendering fault and sends
  // somebody looking for a value that was never there.
  await page.goto('/cost/allocation');
  await expect(page.getByTestId('allocation-unallocated')).toHaveText('nobody tagged this');
  await expect(page.getByText('814.17')).toBeVisible();

  // 4. Anomalies. The working is shown whole, because a verdict a reader cannot argue
  // with is one they have to take on trust.
  await page.goto('/cost/anomalies');
  await expect(page.getByText(/313\.6 deviations out/)).toBeVisible();
  await expect(page.getByTestId('anomaly-judged')).toBeVisible();

  // 5. Commitments. The distinction the screen exists to draw, which is the thirty
  // seconds the runbook calls the best in the demo.
  await page.goto('/cost/commitments');
  await expect(page.getByTestId('utilization-fake-sp-compute')).toHaveText('100.0%');
  await expect(page.getByTestId('coverage-AmazonEC2')).toHaveText('40.3%');
  await expect(page.getByTestId('commitment-waste')).toContainText('300.68');
  await expect(page.getByTestId('commitment-scope-note')).toContainText(/whole payer/i);

  // 6. Export. The screen states the total the file must sum to, which is what makes
  // the claim checkable in ten seconds.
  await page.goto('/cost/export');
  await expect(page.getByTestId('export-claim')).toContainText('3,781.93');
  await expect(page.getByTestId('export-not-excel')).toContainText(/CSV only/);
});

test('the commitments screen never puts the two percentages side by side', async ({ page }) => {
  // The one layout rule this feature rests on, asserted against the real bundle rather
  // than against jsdom. Two percentages meaning opposite things, adjacent, would be
  // compared by any reader, and the comparison is meaningless.
  await demoEstate(page);
  await page.goto('/cost/commitments');

  const row = page.locator('tr', { has: page.getByTestId('utilization-fake-sp-compute') });
  await expect(row.locator('[data-testid^="coverage-"]')).toHaveCount(0);

  await expect(page.getByTestId('utilization-heading')).toContainText(
    /what we paid for was used/i,
  );
  await expect(page.getByTestId('coverage-heading')).toContainText(
    /estate is on a commitment/i,
  );
});
