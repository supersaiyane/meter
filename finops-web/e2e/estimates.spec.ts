import { expect, test, type Page } from '@playwright/test';

import { demoEstate } from './estate';

/**
 * The Estimates screen, P16, TASK-P16-008: the plans a pull request's pipeline sent, the unpriced
 * count first; one plan's changes, why one is not priced and what the bill said of one created;
 * and how close the estimates came, from the judged alone. And as a narrowed reader reads it,
 * told why none of it is there. The routes are stubbed, as every journey stubs its routes, with
 * answers shaped the way the routes answer.
 */

const META = {
  as_of: '2026-10-16T09:00:00Z',
  collected_at: '2026-10-16T09:10:00Z',
  scope_coverage: { visible: 1, total: 1, is_partial: false, unit: 'payer' },
  degraded: false,
  failures: [],
};

const ME = {
  principal_id: 'p-owner',
  display_name: 'Owner',
  tenant_id: 't-1',
  tiers: ['finops'],
  accounts_in_scope: 5,
};

const PLAN = {
  plan_id: 'plan-1',
  repository: 'acme/infra',
  pull_request: 7,
  head_sha: 'abc1234def0000',
  folder: 'storage',
  status: 'PRICED',
  reason: null,
  received_at: '2026-10-16T09:00:00Z',
  monthly_before: '0.000000',
  monthly_after: '73.000000',
  monthly_change: '73.000000',
  currency: 'USD',
  priced_lines: 1,
  unpriced_lines: 1,
  comment_status: 'WRITTEN',
  comment_url: 'https://code.example/acme/infra/pull/7#issuecomment-1',
  comment_reason: null,
  pull_request_state: 'MERGED',
  as_of: '2026-10-16T09:00:00Z',
  collected_at: '2026-10-16T09:10:00Z',
  basis: 'modelled',
};

const LINES = [
  {
    address: 'aws_nat_gateway.out',
    resource_type: 'aws_nat_gateway',
    actions: ['create'],
    region: 'eu-west-1',
    monthly_before: null,
    monthly_after: null,
    reason: 'usage based: priced by the data it carries, which a plan does not say',
    notes: [],
    unknown: [],
    withheld: [],
    components: [],
    comparison: null,
    basis: 'modelled',
  },
  {
    address: 'aws_instance.web',
    resource_type: 'aws_instance',
    actions: ['create'],
    region: 'eu-west-1',
    monthly_before: null,
    monthly_after: '73.000000',
    reason: null,
    notes: [],
    unknown: [],
    withheld: [],
    components: [
      {
        side: 'after',
        what: 'm7g.large, Linux, shared tenancy',
        quantity: '730',
        unit: 'Hrs',
        unit_price: '0.1000000000',
        monthly: '73.000000',
        sku_price_id: 'sku-1',
        version: '20261001',
        basis: 'modelled',
      },
    ],
    comparison: {
      verdict: 'ABOVE',
      reason: null,
      provider_id: 'i-0123456789abcdef0',
      window_start: '2026-10-12',
      window_end: '2026-11-11',
      list_monthly: '106.458333',
      effective_monthly: '58.400000',
      variance_percent: '45.8333',
      as_of: '2026-11-11T08:00:00Z',
      basis: 'measured',
    },
    basis: 'modelled',
  },
];

const ACCURACY = {
  types: [
    {
      resource_type: 'aws_instance',
      compared: 4,
      within: 3,
      median_error_percent: '6.5000',
      basis: 'modelled against measured',
    },
    {
      resource_type: 'all',
      compared: 4,
      within: 3,
      median_error_percent: '6.5000',
      basis: 'modelled against measured',
    },
  ],
  within_percent: '10',
  window_days: 30,
  pending: 2,
  not_compared: 1,
};

const DETAIL = {
  plan: PLAN,
  lines: LINES,
  assumptions: 'Modelled from list prices, 730 hours a month.',
};

async function withEstimates(page: Page, isGlobal: boolean): Promise<string[]> {
  const read: string[] = [];
  await demoEstate(page);
  await page.route('**/api/v1/me', async (route) => {
    await route.fulfill({ json: { data: { ...ME, is_global: isGlobal }, meta: META } });
  });
  await page.route('**/api/v1/estimates', async (route) => {
    read.push('plans');
    await route.fulfill({ json: { data: { plans: [PLAN], more: false }, meta: META } });
  });
  await page.route('**/api/v1/estimates/accuracy', async (route) => {
    read.push('accuracy');
    await route.fulfill({ json: { data: ACCURACY, meta: META } });
  });
  await page.route('**/api/v1/estimates/plan-1', async (route) => {
    read.push('plan-1');
    await route.fulfill({ json: { data: DETAIL, meta: META } });
  });
  return read;
}

test('a plan opens on what Meter could not price, and the bill says how close it came', async ({
  page,
}) => {
  await withEstimates(page, true);
  await page.goto('/plan/estimates');

  const plans = page.getByTestId('estimate-plans');
  await expect(plans.getByTestId('plan-unpriced')).toHaveText('1 of 2 resources is not priced');
  await expect(plans.getByTestId('figure').first()).toHaveAttribute(
    'data-provenance',
    'modelled',
  );

  await plans.getByTestId('open-plan-plan-1').click();
  const lines = page.getByTestId('estimate-lines');
  await expect(lines.getByTestId('estimate-lines-headline')).toHaveText(
    '1 of 2 resources is not priced',
  );
  await expect(lines.getByTestId('line-why').first()).toContainText('usage based');
  await expect(lines.getByTestId('line-bill').nth(1)).toHaveText(
    'The bill came in 45.8 percent above',
  );

  await expect(page.getByTestId('estimate-accuracy-headline')).toContainText(
    '3 of 4 estimates came within 10 percent of the bill. The median error was 6.5 percent.',
  );
});

test('a narrowed reader is told why, and nothing of the organization is read', async ({
  page,
}) => {
  const read = await withEstimates(page, false);
  await page.goto('/plan/estimates');

  await expect(page.getByTestId('estimates-organization-only')).toContainText(
    'A plan names no account until it is applied',
  );
  await expect(page.getByTestId('estimate-plans')).toHaveCount(0);
  expect(read).toEqual([]);
});
