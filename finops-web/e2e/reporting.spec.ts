import { expect, test, type Page } from '@playwright/test';

import { demoEstate } from './estate';

/**
 * The reporting path, end to end, as P8 spec section 8 lists it: open the Overview, change
 * persona, open Cost Explorer, group by two dimensions, export to Excel, save the view and
 * schedule it. TASK-P8-014.
 *
 * Every route is stubbed, as every journey stubs its routes: the demo estate answers the
 * screens, and the explorer, the views and the schedules are answered here by small stores that
 * answer as the API does. What the API makes of a view, a file or a schedule is held by its own
 * tests. What this proves is that one reader walks the whole path in the built bundle, and that
 * the view they built, both groupings included, is the view every later step carries.
 */

const NOW = '2026-10-07T06:00:00Z';

const META = {
  as_of: NOW,
  collected_at: NOW,
  scope_coverage: { visible: 2, total: 2, is_partial: false, unit: 'accounts' },
  degraded: false,
  failures: [],
};

const WORKBOOK = 'meter-cost-explorer-2026-10-07.xlsx';

const ME = {
  principal_id: 'dev@example.local',
  display_name: 'Dev',
  tenant_id: 't-1',
  tiers: ['analyst'],
  is_global: false,
  accounts_in_scope: 2,
};

/** The grouping an address names when it names none, and the values it answers with. */
const SERVICE = ['AmazonEC2', 'AmazonRDS'] as const;

/** Two values for each grouping the journey uses, and what each pair cost. */
const VALUES: Readonly<Record<string, readonly [string, string]>> = {
  service: SERVICE,
  region: ['eu-west-1', 'us-east-1'],
  account: ['111122223333', '444455556666'],
};
const THIS_PERIOD = ['2043.1120', '1738.8215'] as const;
const PREVIOUS_PERIOD = ['2400.0000', '1703.2200'] as const;

/** The explorer's answer for the grouping the address asks for, in the shape the API returns. */
function explored(asked: URLSearchParams) {
  const first = asked.get('group_by') ?? 'service';
  const second = asked.get('then_by');
  // A named fallback, because an index into a Record may be undefined, its own key included.
  const firsts = VALUES[first] ?? SERVICE;
  const seconds = second === null ? null : (VALUES[second] ?? null);
  return {
    metric: 'effective_cost',
    metrics_available: ['effective_cost', 'billed_cost'],
    period: 'mtd',
    granularity: 'daily',
    current: { start: '2026-10-01', end: '2026-10-07' },
    previous: { start: '2026-09-01', end: '2026-09-07' },
    is_open: true,
    collected_from: '2026-09-01',
    previous_collected: true,
    group_by: { dimension: first, tag_key: null },
    then_by: second === null ? null : { dimension: second, tag_key: null },
    tag_keys: ['team'],
    total_this_period: '3781.9335',
    total_previous_period: '4103.2200',
    series: [...firsts],
    points: firsts.map((value, at) => ({
      bucket: '2026-10-06',
      series: value,
      cost: THIS_PERIOD[at],
    })),
    rows: firsts.map((value, at) => ({
      first: value,
      second: seconds === null ? null : seconds[at],
      this_period: THIS_PERIOD[at],
      previous_period: PREVIOUS_PERIOD[at],
    })),
    row_limit: 500,
    rows_omitted: 0,
    omitted_this_period: '0',
    omitted_previous_period: '0',
    region_geographies: {},
  };
}

interface Asked {
  /** Each file the browser asked the explorer for, as the query it asked with. */
  readonly files: Record<string, string>[];
  readonly views: Record<string, unknown>[];
  readonly schedules: Record<string, unknown>[];
}

/** The demo estate, with the explorer, the library and the schedules answered here. */
async function withReporting(page: Page): Promise<Asked> {
  const asked: Asked = { files: [], views: [], schedules: [] };
  const views: Record<string, unknown>[] = [];
  const schedules: Record<string, unknown>[] = [];
  // Anything neither the estate nor this journey answers fails as a stopped API does, so a step
  // that reads a route nobody stubbed fails here rather than passing on whatever was running.
  await page.route('**/api/v1/**', async (route) => {
    await route.fulfill({ status: 503, body: 'The API is not running in this journey.' });
  });
  await demoEstate(page);
  await page.route('**/api/v1/me', async (route) => {
    await route.fulfill({ json: { data: ME, meta: META } });
  });
  await page.route('**/api/v1/cost/explore*', async (route) => {
    const query = new URL(route.request().url()).searchParams;
    if (query.get('format') === null) {
      await route.fulfill({ json: { data: explored(query), meta: META } });
      return;
    }
    asked.files.push(Object.fromEntries(query));
    await route.fulfill({
      body: 'a workbook the API wrote',
      headers: {
        'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'Content-Disposition': `attachment; filename="${WORKBOOK}"`,
      },
    });
  });
  await page.route('**/api/v1/reports/views', async (route) => {
    if (route.request().method() === 'POST') {
      const body = route.request().postDataJSON() as Record<string, unknown>;
      asked.views.push(body);
      const made = {
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
  await page.route('**/api/v1/reports/schedules', async (route) => {
    if (route.request().method() === 'POST') {
      const body = route.request().postDataJSON() as Record<string, unknown>;
      asked.schedules.push(body);
      const view = views.find((one) => one.view_id === body.view_id);
      const made = {
        ...body,
        schedule_id: `s-${String(schedules.length + 1)}`,
        view_name: view?.name ?? null,
        screen_path: view?.screen_path ?? null,
        enabled: true,
        next_run_at: '2026-11-06T06:00:00Z',
        created_at: NOW,
        updated_at: NOW,
      };
      schedules.push(made);
      await route.fulfill({ status: 201, json: { data: made, meta: META } });
      return;
    }
    const coverage = { visible: schedules.length, total: schedules.length, is_partial: false };
    await route.fulfill({
      json: {
        data: {
          rendering: true,
          retention: 'Files are kept until a retention period is decided, OPEN-15.',
          delivery: 'Nothing is sent yet: where reports go, email or Slack, is OPEN-11.',
          schedules,
        },
        meta: { ...META, scope_coverage: { ...coverage, unit: 'schedules' } },
      },
    });
  });
  return asked;
}

test('a reader goes from the Overview to a scheduled workbook of a view they grouped twice', async ({
  page,
}) => {
  const asked = await withReporting(page);

  // The Overview, on the reader's own dashboard.
  await page.goto('/');
  await page.getByText('Executive', { exact: true }).click();
  await expect(page.getByRole('radio', { name: 'Executive' })).toBeChecked();
  await expect(page.getByRole('region', { name: 'Top movers' })).toBeVisible();

  // Cost Explorer, from its section on the rail, grouped by region and then by sub account,
  // written to the address.
  const rail = page.locator('#sections');
  await rail.getByText('Analyze', { exact: true }).click();
  await rail.getByRole('link', { name: 'Cost Explorer' }).click();
  await expect(page).toHaveURL(/\/analyze\/explorer/);
  const controls = page.getByTestId('explore-controls');
  await controls.getByLabel('Group by').selectOption('region');
  await controls.getByLabel('Then by').selectOption('account');
  await expect(page).toHaveURL(/group_by=region/);
  await expect(page).toHaveURL(/then_by=account/);
  await expect(controls.getByLabel('Then by')).toHaveValue('account');

  // Excel, of the view as built: the file is asked for with both groupings.
  const menu = page.getByTestId('export-menu');
  await menu.getByText('Export').click();
  const download = page.waitForEvent('download');
  await menu.getByRole('group', { name: 'Cost Explorer' }).getByTestId('export-xlsx').click();
  expect((await download).suggestedFilename()).toBe(WORKBOOK);
  expect(asked.files).toEqual([
    expect.objectContaining({ format: 'xlsx', group_by: 'region', then_by: 'account' }),
  ]);

  // Saved, with the address that holds both groupings.
  const save = page.getByTestId('save-view');
  await save.getByText('Save view').click();
  await save.getByTestId('save-view-name').fill('Cost by region and account');
  await save.getByTestId('save-view-submit').click();
  await expect(save.getByTestId('save-view-saved')).toHaveText(
    'Saved as Cost by region and account, in the Report Library.',
  );
  expect(asked.views).toEqual([
    {
      name: 'Cost by region and account',
      screen_path: '/analyze/explorer',
      query: expect.objectContaining({ group_by: 'region', then_by: 'account' }),
      visibility: 'PRIVATE',
    },
  ]);

  // Scheduled from the library, which opens the view on its own screen with the panel open.
  await save.getByRole('link', { name: 'Report Library' }).click();
  await expect(page).toHaveURL(/\/report\/library$/);
  await page
    .getByTestId('library-row')
    .filter({ hasText: 'Cost by region and account' })
    .getByTestId('library-schedule')
    .click();
  await expect(page).toHaveURL(/\/analyze\/explorer\?.*then_by=account/);
  const panel = page.getByTestId('schedule-view');
  await expect(panel).toHaveAttribute('open', '');
  await expect(panel.getByRole('radio', { name: 'Cost Explorer' })).toBeChecked();
  await expect(panel.getByTestId('schedule-view-format-xlsx')).toBeChecked();
  await panel.getByTestId('schedule-view-cadence').selectOption('MONTH_CLOSE');
  await expect(panel.getByTestId('schedule-view-recipients')).toHaveValue('dev@example.local');
  await panel.getByTestId('schedule-view-submit').click();
  await expect(panel.getByTestId('schedule-view-made')).toContainText('Scheduled.');

  expect(asked.schedules).toEqual([
    expect.objectContaining({
      view_id: 'v-1',
      format: 'xlsx',
      cadence: 'MONTH_CLOSE',
      recipients: ['dev@example.local'],
    }),
  ]);
  // The route the schedule renders is the explorer's, grouped as the reader grouped it.
  const route = new URL(String(asked.schedules[0]?.export_path), 'http://meter.test');
  expect(route.pathname).toBe('/api/v1/cost/explore');
  expect(route.searchParams.get('group_by')).toBe('region');
  expect(route.searchParams.get('then_by')).toBe('account');
  expect(route.searchParams.get('format')).toBeNull();

  // Listed, with what the deployment does with what it makes.
  await panel.getByRole('link', { name: 'Scheduled' }).click();
  await expect(page).toHaveURL(/\/report\/scheduled$/);
  await expect(page.getByTestId('scheduled-row')).toContainText('Cost by region and account');
  await expect(page.getByTestId('scheduled-row')).toContainText('When the month closes');
  await expect(page.getByTestId('scheduled-delivery')).toContainText('OPEN-11');
});
