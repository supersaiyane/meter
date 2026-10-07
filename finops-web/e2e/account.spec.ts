import { expect, test, type Page } from '@playwright/test';

import { demoEstate } from './estate';

/**
 * The account chosen in the address, FEAT-075, in the built bundle.
 *
 * A shared link is the first way an account arrives, so this opens one. The account is named
 * under the title, every read of a figure carries it to the server as `chosen_account`, and
 * moving to another screen through the rail keeps it. Two reads go without it: the list of
 * accounts to choose from, which a choice must never narrow, and the reader's own schedules,
 * which hold no figure to narrow, as saved views and report runs hold none.
 */

const CHOSEN = '444455556666';

/** The reads that carry no account, each for the reason above. */
const UNNARROWED: ReadonlySet<string> = new Set([
  '/api/v1/accounts',
  '/api/v1/reports/schedules',
]);

const META = {
  as_of: '2026-09-19T04:00:00Z',
  collected_at: '2026-09-20T06:22:00Z',
  scope_coverage: { visible: 1, total: 1, is_partial: false, unit: 'accounts' },
  degraded: false,
  failures: [],
};

const PLATFORM = {
  provider: 'aws',
  account_id: CHOSEN,
  name: 'Platform',
  status: 'ACTIVE',
  role_health: 'HEALTHY',
  role_health_checked_at: '2026-09-20T06:00:00Z',
  role_health_error: null,
  as_of: '2026-09-19T04:00:00Z',
  collected_at: '2026-09-20T06:22:00Z',
};

/** The demo estate, and the accounts the shell names a choice from. */
async function estate(page: Page): Promise<void> {
  await demoEstate(page);
  await page.route('**/api/v1/accounts', async (route) => {
    await route.fulfill({ json: { data: [PLATFORM], meta: META } });
  });
}

/** Every read the page sends to the API, as a path and its query. */
function reads(page: Page): string[] {
  const seen: string[] = [];
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (url.pathname.startsWith('/api/v1/')) {
      seen.push(`${url.pathname}${url.search}`);
    }
  });
  return seen;
}

const narrowed = (path: string) => path.includes(`chosen_account=${CHOSEN}`);

/** The Overview's Effective Cost figure: Cost Explorer's month to date total, in whole dollars. */
const spend = (page: Page) =>
  page.getByRole('region', { name: 'Effective Cost' }).getByTestId('kpi-value');

test('a shared link opens one account, and every read and every move keeps it', async ({
  page,
}) => {
  await estate(page);
  const seen = reads(page);

  await page.goto(`/?account=${CHOSEN}`);
  await expect(page.getByTestId('chosen-account')).toHaveText(`Account Platform, ${CHOSEN}`);
  await expect(spend(page)).toHaveText('$3,782');
  expect(seen.some(narrowed)).toBe(true);
  expect(seen.filter((path) => !UNNARROWED.has(path) && !narrowed(path))).toEqual([]);

  await page.getByTestId('group-Analyze').locator('summary').click();
  await page.getByRole('link', { name: 'Cost Explorer' }).click();
  await expect(page).toHaveURL(new RegExp(`/analyze/explorer\\?account=${CHOSEN}$`));
  await expect(page.getByText('AmazonEC2').first()).toBeVisible();
  const explored = seen.filter((path) => path.startsWith('/api/v1/cost/explore'));
  expect(explored.length).toBeGreaterThan(0);
  expect(explored.every(narrowed)).toBe(true);
});

test('with no account chosen nothing is narrowed and no account is named', async ({ page }) => {
  await estate(page);
  const seen = reads(page);

  await page.goto('/');
  await expect(spend(page)).toHaveText('$3,782');
  await expect(page.getByTestId('chosen-account')).toHaveCount(0);
  expect(seen.filter((path) => path.includes('chosen_account'))).toEqual([]);
});

const CHECKOUT = {
  node_id: 'n-1',
  provider_id: `arn:aws:ecs:eu-west-1:${CHOSEN}:service/checkout-api`,
  account_id: CHOSEN,
  node_kind: 'COMPUTE',
  resource_type: 'AWS::ECS::Service',
  region_id: 'eu-west-1',
  availability_zone: null,
  name: 'checkout-api',
  as_of: '2026-09-19T04:00:00Z',
  collected_at: '2026-09-20T06:22:00Z',
};

test('the search box chooses an account, opens a service and finds a resource', async ({
  page,
}) => {
  await estate(page);
  await page.route('**/api/v1/cost/by-service*', async (route) => {
    const service = { name: 'AmazonEC2', effective_cost: '412.64', billed_cost: '412.64' };
    await route.fulfill({ json: { data: [service], meta: META } });
  });
  await page.route('**/api/v1/inventory/resources?q=*', async (route) => {
    const resources = { resources: [CHECKOUT], total: 1, limit: 8, offset: 0, filters: {} };
    await route.fulfill({ json: { data: resources, meta: META } });
  });
  await page.goto('/analyze/anomalies');
  const box = page.getByRole('combobox', { name: 'Search accounts, services and resources' });
  await expect(box).toHaveValue('All accounts');

  await box.click();
  await box.fill('plat');
  await page.getByRole('option', { name: `Platform (${CHOSEN})` }).click();
  await expect(page).toHaveURL(new RegExp(`/analyze/anomalies\\?account=${CHOSEN}$`));
  await expect(page.getByTestId('chosen-account')).toHaveText(`Account Platform, ${CHOSEN}`);
  await expect(box).toHaveValue(`Platform (${CHOSEN})`);

  await box.click();
  await box.fill('ec2');
  await page.getByRole('option', { name: 'AmazonEC2' }).click();
  await expect(page).toHaveURL(
    new RegExp(`/analyze/explorer\\?service=AmazonEC2&account=${CHOSEN}$`),
  );

  await box.click();
  await box.fill('checkout');
  await page.getByRole('option', { name: 'checkout-api' }).click();
  await expect(page).toHaveURL(new RegExp(`/inventory/resources/n-1\\?account=${CHOSEN}$`));
});
