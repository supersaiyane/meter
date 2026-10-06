import { expect, test, type Page } from '@playwright/test';

/**
 * Export, end to end. FEAT-067, TASK-P8-009.
 *
 * The route is stubbed as every journey stubs its routes, and so is the file it answers with
 * for `format=xlsx`, because what the server writes is held by the API's own tests. What this
 * journey proves is the browser's half: the menu is beside the title of a screen that reads an
 * exportable view, it asks for that view with the format added, and the browser saves the
 * server's file under the server's name.
 */

const META = {
  as_of: '2026-08-27T04:00:00Z',
  collected_at: '2026-08-27T09:54:00Z',
  scope_coverage: { visible: 1, total: 1, is_partial: false, unit: 'accounts' },
  degraded: false,
  failures: [],
};

const ACCOUNT = {
  provider: 'aws',
  account_id: 'fake-platform-a',
  name: 'Platform',
  status: 'ACTIVE',
  role_health: 'HEALTHY',
  role_health_checked_at: '2026-08-27T09:00:00Z',
  role_health_error: null,
  as_of: '2026-08-27T04:00:00Z',
  collected_at: '2026-08-27T09:54:00Z',
};

const WORKBOOK = 'meter-accounts-2026-10-05.xlsx';

/** The accounts route, as a screen and as a file, and every format the browser asked for. */
async function withAccounts(page: Page): Promise<string[]> {
  const asked: string[] = [];
  await page.addInitScript(() => {
    window.localStorage.setItem('meter.token', 'a-session-token');
  });
  await page.route('**/api/v1/accounts*', async (route) => {
    const format = new URL(route.request().url()).searchParams.get('format');
    if (format === null) {
      await route.fulfill({ json: { data: [ACCOUNT], meta: META } });
      return;
    }
    asked.push(format);
    await route.fulfill({
      body: 'a workbook the API wrote',
      headers: {
        'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'Content-Disposition': `attachment; filename="${WORKBOOK}"`,
      },
    });
  });
  await page.route('**/api/v1/org/tree', async (route) => {
    await route.fulfill({ json: { data: [], meta: META } });
  });
  return asked;
}

test('a screen offers its view as a workbook, and the browser saves the server file', async ({
  page,
}) => {
  const asked = await withAccounts(page);
  await page.goto('/inventory/accounts');

  const menu = page.getByTestId('export-menu');
  await menu.getByText('Export').click();
  const offered = menu.getByRole('group', { name: 'Accounts' });
  await expect(offered.getByTestId('export-csv')).toHaveText('CSV, every row');

  const download = page.waitForEvent('download');
  await offered.getByTestId('export-xlsx').click();
  expect((await download).suggestedFilename()).toBe(WORKBOOK);
  expect(asked).toEqual(['xlsx']);
});

test('a failed export says why in the menu rather than doing nothing', async ({ page }) => {
  await withAccounts(page);
  await page.route('**/api/v1/accounts?format=*', async (route) => {
    await route.fulfill({ status: 403, body: 'An export is recorded against a person.' });
  });
  await page.goto('/inventory/accounts');

  const menu = page.getByTestId('export-menu');
  await menu.getByText('Export').click();
  // The screen's own table, named, because its charts offer their numbers in the same menu.
  await menu.getByRole('group', { name: 'Accounts' }).getByTestId('export-csv').click();
  await expect(menu.getByRole('alert')).toContainText('recorded against a person');
});
