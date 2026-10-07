import { expect, test, type Page } from '@playwright/test';

/**
 * The report library, end to end. FEAT-068, TASK-P8-010.
 *
 * The routes are stubbed, as every journey stubs its routes, by a small library held in memory
 * that answers as the API does. Who may change a view, and that opening one reads the screen in
 * the opener's scope, are the API's to enforce and its own tests hold both with two principals.
 * What this journey proves is the browser's half: Save view keeps the screen and its query, the
 * library lists the view and opens it at that address, a colleague's view offers only what its
 * reader may do, and Export from the library lands on the view with its Export menu open.
 */

const NOW = '2026-10-07T06:00:00Z';

const META = {
  as_of: NOW,
  collected_at: NOW,
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
  role_health_checked_at: NOW,
  role_health_error: null,
  as_of: NOW,
  collected_at: NOW,
};

interface View {
  readonly view_id: string;
  readonly name: string;
  readonly screen_path: string;
  readonly query: Readonly<Record<string, string | readonly string[]>>;
  readonly visibility: 'PRIVATE' | 'SHARED';
  readonly owned: boolean;
  readonly created_at: string;
  readonly updated_at: string;
}

const ACTIVE: View = {
  view_id: 'v-active',
  name: 'Active accounts',
  screen_path: '/inventory/accounts',
  query: { status: 'ACTIVE' },
  visibility: 'SHARED',
  owned: true,
  created_at: NOW,
  updated_at: NOW,
};

/** The accounts screen's routes, and a library that keeps what is saved to it. */
async function withLibrary(page: Page, seeded: readonly View[] = []): Promise<unknown[]> {
  const views: View[] = [...seeded];
  const posted: unknown[] = [];
  await page.addInitScript(() => {
    window.localStorage.setItem('meter.token', 'a-session-token');
  });
  await page.route('**/api/v1/accounts*', async (route) => {
    await route.fulfill({ json: { data: [ACCOUNT], meta: META } });
  });
  await page.route('**/api/v1/org/tree', async (route) => {
    await route.fulfill({ json: { data: [], meta: META } });
  });
  await page.route('**/api/v1/reports/views', async (route) => {
    if (route.request().method() === 'POST') {
      const body = route.request().postDataJSON() as Omit<View, 'view_id' | 'owned'>;
      posted.push(body);
      const made: View = {
        ...body,
        view_id: `v-${String(views.length + 1)}`,
        owned: true,
        created_at: NOW,
        updated_at: NOW,
      };
      views.unshift(made);
      await route.fulfill({ status: 201, json: { data: made, meta: META } });
      return;
    }
    const coverage = { visible: views.length, total: views.length, is_partial: false };
    await route.fulfill({
      json: {
        data: views,
        meta: { ...META, scope_coverage: { ...coverage, unit: 'saved views' } },
      },
    });
  });
  return posted;
}

test('a screen saved as a view is listed in the library and opens where it was saved', async ({
  page,
}) => {
  const posted = await withLibrary(page);
  await page.goto('/inventory/accounts?status=ACTIVE');

  const save = page.getByTestId('save-view');
  await save.getByText('Save view').click();
  await save.getByTestId('save-view-name').fill('Active accounts');
  await save.getByTestId('save-view-shared').check();
  await save.getByTestId('save-view-submit').click();
  await expect(save.getByTestId('save-view-saved')).toHaveText(
    'Saved as Active accounts, in the Report Library.',
  );
  expect(posted).toEqual([
    {
      name: 'Active accounts',
      screen_path: '/inventory/accounts',
      query: { status: 'ACTIVE' },
      visibility: 'SHARED',
    },
  ]);

  await save.getByRole('link', { name: 'Report Library' }).click();
  await expect(page).toHaveURL(/\/report\/library$/);
  const row = page.getByTestId('library-row').filter({ hasText: 'Active accounts' });
  await expect(row).toContainText('Everyone, shared by you');

  await row.getByRole('link', { name: 'Active accounts' }).click();
  await expect(page).toHaveURL(/\/inventory\/accounts\?status=ACTIVE$/);
});

test('Export in the library lands on the view with its Export menu open', async ({ page }) => {
  await withLibrary(page, [ACTIVE]);
  await page.goto('/report/library');
  await page.getByTestId('library-row').getByTestId('library-export').click();

  await expect(page).toHaveURL(/\/inventory\/accounts\?status=ACTIVE$/);
  await expect(page.getByTestId('export-menu')).toHaveAttribute('open', '');
});

test("a colleague's shared view can be duplicated, and offers nothing that changes it", async ({
  page,
}) => {
  const posted = await withLibrary(page, [{ ...ACTIVE, owned: false }]);
  await page.goto('/report/library');

  const row = page.getByTestId('library-row');
  await expect(row).toContainText('Everyone, shared with you');
  for (const id of ['library-rename-start', 'library-share', 'library-delete-start']) {
    await expect(row.getByTestId(id)).toHaveCount(0);
  }
  await row.getByTestId('library-duplicate').click();
  await expect(page.getByTestId('library-notice')).toHaveText(
    'Duplicated as Active accounts (copy), private to you.',
  );
  expect(posted).toEqual([
    {
      name: 'Active accounts (copy)',
      screen_path: '/inventory/accounts',
      query: { status: 'ACTIVE' },
      visibility: 'PRIVATE',
    },
  ]);
});
