import { expect, test, type Page } from '@playwright/test';

/**
 * Scheduling a saved view, end to end. FEAT-069, TASK-P8-011.
 *
 * The routes are stubbed, as every journey stubs its routes, by a small store held in memory that
 * answers as the API does. That each recipient's file is made within their own access, and that
 * a kept file is handed back only while their access still covers it, are the API's to enforce,
 * and its own tests hold both with two people. What this journey proves is the browser's half:
 * the library's Schedule opens the view's own screen with the schedule panel open, the panel
 * offers the routes that screen exports, and the schedule it makes is listed on the Scheduled
 * screen with what the deployment does with its files.
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

const VIEW = {
  view_id: 'v-active',
  name: 'Active accounts',
  screen_path: '/inventory/accounts',
  query: { status: 'ACTIVE' },
  visibility: 'PRIVATE',
  owned: true,
  created_at: NOW,
  updated_at: NOW,
};

const ME = {
  principal_id: 'dev@example.local',
  display_name: 'Dev',
  tenant_id: 't-1',
  tiers: ['analyst'],
  is_global: false,
  accounts_in_scope: 1,
};

/** The routes the journey reads, and a schedule store that keeps what is posted to it. */
async function withSchedules(page: Page): Promise<unknown[]> {
  const posted: unknown[] = [];
  const schedules: Record<string, unknown>[] = [];
  await page.addInitScript(() => {
    window.localStorage.setItem('meter.token', 'a-session-token');
  });
  await page.route('**/api/v1/accounts*', async (route) => {
    await route.fulfill({ json: { data: [ACCOUNT], meta: META } });
  });
  await page.route('**/api/v1/org/tree', async (route) => {
    await route.fulfill({ json: { data: [], meta: META } });
  });
  await page.route('**/api/v1/me', async (route) => {
    await route.fulfill({ json: { data: ME, meta: META } });
  });
  await page.route('**/api/v1/reports/views', async (route) => {
    const coverage = { visible: 1, total: 1, is_partial: false, unit: 'saved views' };
    await route.fulfill({
      json: { data: [VIEW], meta: { ...META, scope_coverage: coverage } },
    });
  });
  await page.route('**/api/v1/reports/runs', async (route) => {
    const coverage = { visible: 0, total: 0, is_partial: false, unit: 'report runs' };
    await route.fulfill({ json: { data: [], meta: { ...META, scope_coverage: coverage } } });
  });
  await page.route('**/api/v1/reports/schedules', async (route) => {
    if (route.request().method() === 'POST') {
      const body = route.request().postDataJSON() as Record<string, unknown>;
      posted.push(body);
      const made = {
        ...body,
        schedule_id: `s-${String(schedules.length + 1)}`,
        view_name: VIEW.name,
        screen_path: VIEW.screen_path,
        enabled: true,
        next_run_at: '2026-11-01T06:00:00Z',
        created_at: NOW,
        updated_at: NOW,
      };
      schedules.push(made);
      await route.fulfill({ status: 201, json: { data: made, meta: META } });
      return;
    }
    const coverage = {
      visible: schedules.length,
      total: schedules.length,
      is_partial: false,
      unit: 'schedules',
    };
    await route.fulfill({
      json: {
        data: {
          rendering: true,
          retention: 'Files are kept until a retention period is decided, OPEN-15.',
          delivery: 'Nothing is sent yet: where reports go, email or Slack, is OPEN-11.',
          schedules,
        },
        meta: { ...META, scope_coverage: coverage },
      },
    });
  });
  return posted;
}

test('a saved view is scheduled from its own screen and listed with what becomes of it', async ({
  page,
}) => {
  const posted = await withSchedules(page);
  await page.goto('/report/library');
  await page.getByTestId('library-row').getByTestId('library-schedule').click();

  await expect(page).toHaveURL(/\/inventory\/accounts\?status=ACTIVE$/);
  const panel = page.getByTestId('schedule-view');
  await expect(panel).toHaveAttribute('open', '');
  await expect(panel.getByTestId('schedule-view-title')).toHaveText('Schedule Active accounts');
  await expect(panel.getByRole('radio', { name: 'Accounts' })).toBeChecked();
  await expect(panel.getByTestId('schedule-view-recipients')).toHaveValue('dev@example.local');

  await panel.getByTestId('schedule-view-format-csv').check();
  await panel.getByTestId('schedule-view-cadence').selectOption('MONTHLY');
  await panel.getByTestId('schedule-view-submit').click();
  await expect(panel.getByTestId('schedule-view-made')).toContainText('Scheduled.');
  expect(posted).toEqual([
    {
      view_id: 'v-active',
      // The route as the screen reads it: Accounts filters by status in the browser, so the
      // route it exports, and therefore schedules, carries no status, exactly as Export does.
      export_path: '/api/v1/accounts',
      format: 'csv',
      cadence: 'MONTHLY',
      recipients: ['dev@example.local'],
    },
  ]);

  await panel.getByRole('link', { name: 'Scheduled' }).click();
  await expect(page).toHaveURL(/\/report\/scheduled$/);
  const row = page.getByTestId('scheduled-row');
  await expect(row).toContainText('Active accounts');
  await expect(row).toContainText('Monthly');
  await expect(page.getByTestId('scheduled-delivery')).toContainText('OPEN-11');
  await expect(page.getByTestId('scheduled-retention')).toContainText('OPEN-15');
  await expect(page.getByTestId('runs-empty')).toBeVisible();
});
