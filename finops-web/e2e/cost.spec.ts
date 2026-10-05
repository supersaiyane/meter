import { expect, test, type Page } from '@playwright/test';

/**
 * The cost surface, end to end. TASK-P1-012.
 *
 * The arc a person actually walks: open the bill, see what it cost and whether
 * the period is finished, then ask who it belongs to and find that a quarter of
 * it belongs to nobody.
 *
 * The routes are stubbed, because a failed route deliberately does not fall
 * back to a fixture: it raises, the screen renders the typed cause, and no
 * numeral appears. That is the right behaviour and it means a journey against
 * a dead API would be testing the failure state. The backend has its own suite
 * and is called there.
 */

const META = {
  as_of: '2026-08-24T06:00:00Z',
  collected_at: '2026-08-24T06:05:00Z',
  scope_coverage: { visible: 5, total: 5, is_partial: false, unit: 'accounts' },
  degraded: false,
  failures: [],
};

/**
 * One explorer answer whose rows, points and totals agree, the way the route's do: $4,512.71
 * this month to date against $6,197.65 for the same days of the month before.
 */
function explored(twoWay: boolean): unknown {
  const region = (name: string): string | null => (twoWay ? name : null);
  return {
    metric: 'effective_cost',
    metrics_available: ['effective_cost', 'billed_cost'],
    period: 'mtd',
    granularity: 'daily',
    current: { start: '2026-08-01', end: '2026-08-24' },
    previous: { start: '2026-07-01', end: '2026-07-24' },
    is_open: true,
    collected_from: '2026-06-01',
    previous_collected: true,
    group_by: { dimension: 'service', tag_key: null },
    then_by: twoWay ? { dimension: 'region', tag_key: null } : null,
    tag_keys: ['team'],
    total_this_period: '4512.7113',
    total_previous_period: '6197.6544',
    series: ['AmazonEC2', 'AmazonRDS', 'unallocated'],
    points: [
      { bucket: '2026-08-01', series: 'AmazonEC2', cost: '2388.4032' },
      { bucket: '2026-08-01', series: 'AmazonRDS', cost: '1074.7814' },
      { bucket: '2026-08-02', series: 'unallocated', cost: '1049.5267' },
    ],
    rows: [
      {
        first: 'AmazonEC2',
        second: region('eu-west-2'),
        this_period: '2388.4032',
        previous_period: '3300.0000',
      },
      {
        first: 'AmazonRDS',
        second: region('eu-west-2'),
        this_period: '1074.7814',
        previous_period: '1500.0000',
      },
      {
        first: 'unallocated',
        second: region('us-east-1'),
        this_period: '1049.5267',
        previous_period: '1397.6544',
      },
    ],
    row_limit: 500,
    rows_omitted: 0,
    omitted_this_period: '0',
    omitted_previous_period: '0',
  };
}

async function withSession(page: Page): Promise<void> {
  // The session is the token. There is no login screen in P0 and none is faked.
  await page.addInitScript(() => {
    window.localStorage.setItem('meter.token', 'a-session-token');
  });

  // Cost Explorer's answer. A second grouping is answered with a second column, the way the
  // route answers it, so the journey sees the table change shape when it groups twice.
  await page.route('**/api/v1/cost/explore*', async (route) => {
    const twoWay = new URL(route.request().url()).searchParams.get('then_by') === 'region';
    await route.fulfill({ json: { data: explored(twoWay), meta: META } });
  });
  await page.route('**/api/v1/cost/allocation*', async (route) => {
    await route.fulfill({
      json: {
        data: [
          {
            name: 'platform',
            effective_cost: '2382.9683',
            billed_cost: '2573.6058',
            line_items: 184,
          },
          // The row the allocation screen exists for.
          {
            name: 'unallocated',
            effective_cost: '1366.5155',
            billed_cost: '1475.8367',
            line_items: 276,
          },
        ],
        meta: META,
      },
    });
  });
}

test('the bill is legible, and says what it cannot attribute', async ({ page }) => {
  await withSession(page);

  await page.goto('/analyze/explorer');

  // A figure, not a spinner and not a dash. The screen either has the number
  // or says why it does not.
  await expect(page.getByTestId('kpi-value').first()).toContainText(/\d/);

  // Which days the figure covers, and that the month is still open, are on the page.
  // Absent, a reader needs the calendar to interpret the number, which is how a part
  // month gets read as a collapse in spend.
  await expect(page.getByTestId('cost-period')).toContainText(/\d{4}/);
  await expect(page.getByText(/still open/)).toBeVisible();
  // The explorer's own table. Each chart carries a table of its numbers too, closed until
  // asked for, so the first row on the page is no longer this table's.
  await expect(page.getByTestId('explore-table').locator('tbody tr').first()).toBeVisible();

  // Grouped two ways, the journey the P8 spec names. The view is the address, so the
  // link a reader copies opens this view and not the default one.
  await page.getByLabel('Then by').selectOption('region');
  await expect(page).toHaveURL(/then_by=region/);
  await expect(page.getByRole('columnheader', { name: /^Region/ })).toBeVisible();

  // A value in the table is a filter, and the filter is a chip that takes itself away.
  await page.getByRole('link', { name: 'AmazonEC2' }).click();
  await expect(page).toHaveURL(/service=AmazonEC2/);
  await expect(
    page.getByRole('button', { name: 'Remove the filter Service: AmazonEC2' }),
  ).toBeVisible();

  await page.goto('/analyze/allocation');
  await expect(page.getByTestId('allocation-gap')).toBeVisible();

  // The row this screen exists for. An allocation view that drops what it
  // cannot attribute reports a smaller estate than exists, and the gap between
  // that and the invoice is the first thing finance finds.
  await expect(page.getByTestId('allocation-unallocated')).toBeVisible();
});
