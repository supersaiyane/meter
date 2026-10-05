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

async function withSession(page: Page): Promise<void> {
  // The session is the token. There is no login screen in P0 and none is faked.
  await page.addInitScript(() => {
    window.localStorage.setItem('meter.token', 'a-session-token');
  });

  await page.route('**/api/v1/cost/summary*', async (route) => {
    await route.fulfill({
      json: {
        data: {
          // Open, so the screen has to say so. That label is the difference
          // between a reader understanding a part month and a reader
          // concluding that spending collapsed.
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
          change: '-1684.9431',
        },
        meta: META,
      },
    });
  });
  await page.route('**/api/v1/cost/by-service*', async (route) => {
    await route.fulfill({
      json: {
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
        ],
        meta: META,
      },
    });
  });
  await page.route('**/api/v1/cost/trend*', async (route) => {
    await route.fulfill({
      json: {
        data: [{ day: '2026-08-01', effective_cost: '193.1000' }],
        meta: META,
      },
    });
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
  await expect(page.getByTestId('cost-total')).toContainText(/\d/);

  // Whether the period is finished is on the page one way or the other. Absent
  // would leave a reader needing the calendar to interpret the number, which is
  // how a part month gets read as a collapse in spend.
  await expect(page.getByTestId('cost-period')).toContainText(/\d{4}-\d{2}-\d{2}/);

  // Services, ranked. A ranking is the claim that the top row is worth reading
  // first, so an empty table is a screen making no claim at all.
  await expect(page.locator('tbody tr').first()).toBeVisible();

  await page.goto('/analyze/allocation');
  await expect(page.getByTestId('allocation-gap')).toBeVisible();

  // The row this screen exists for. An allocation view that drops what it
  // cannot attribute reports a smaller estate than exists, and the gap between
  // that and the invoice is the first thing finance finds.
  await expect(page.getByTestId('allocation-unallocated')).toBeVisible();
});
