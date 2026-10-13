import { expect, test, type Page } from '@playwright/test';

import { demoEstate } from './estate';

/**
 * The commitments screen as a payer reads it, P14, TASK-P14-009: the effective savings rate first,
 * what is held and when it ends, and Meter's plan beside AWS's, approved with a note. And as a
 * narrowed reader reads it, told why the payer's panels are not there.
 */

const META = {
  as_of: '2026-10-12T00:00:00Z',
  collected_at: '2026-10-13T06:00:00Z',
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

type Step = Readonly<Record<string, string | null>>;

function planOf(status: string) {
  const line = (lineNo: number, tranche: string) => ({
    line_no: lineNo,
    program: 'EC2Instance',
    instance_family: 'm6i',
    region_id: 'us-fake-1',
    tranche_month: tranche,
    hourly_commitment: '0.039',
    discount_percent: '40.0000',
    covers_hourly: '0.0650',
    monthly_saving: '18.98',
    usage_floor_percent: '60.0',
    upfront_cost: '0.00',
    matched_commitment_id: null,
    basis: 'modelled',
  });
  const steps: Step[] = [
    {
      from_status: null,
      to_status: 'DRAFT',
      principal: 'collector:purchase_plan',
      at: '2026-10-13T06:00:00Z',
      note: 'Drafted.',
    },
  ];
  if (status === 'APPROVED') {
    steps.push({
      from_status: 'DRAFT',
      to_status: 'APPROVED',
      principal: 'p-owner',
      at: '2026-10-13T09:00:00Z',
      note: 'Within the ladder',
    });
  }
  return {
    data: {
      plan: {
        plan_id: 'plan-1',
        plan_month: '2026-10-01',
        status,
        target_coverage: '0.800',
        term_years: 1,
        payment_option: 'No Upfront',
        ladder_limit: '0.0833',
        window_start: '2026-09-13',
        window_end: '2026-10-13',
        days_held: 30,
        steady_hourly: '1.0000',
        held_hourly: '0.0000',
        target_hourly: '0.4800',
        beyond_hourly: '0.0120',
        no_purchase_reason: null,
        currency: 'USD',
        unpriced: [],
        as_of: META.as_of,
        collected_at: META.collected_at,
      },
      no_plan_reason: null,
      lines: [line(1, '2026-10-01'), line(2, '2026-11-01')],
      provider: [
        {
          kind: 'savings_plan',
          program: 'Compute',
          term_years: 1,
          payment_option: 'No Upfront',
          lookback_days: 30,
          recommended: true,
          hourly_commitment: '0.850',
          units: null,
          estimated_monthly_savings: '142.35',
          estimated_savings_percent: '21.4',
          upfront_cost: '0',
          currency: 'USD',
          failure_cause: null,
          failure_detail: null,
          as_of: META.as_of,
          collected_at: META.collected_at,
        },
      ],
      difference: [
        "Only Meter's applies the ladder, at most 8.33 percent of the commitment ending in any month: it buys 0.039 USD an hour this month of 0.468 in all, and names the rest as later tranches.",
      ],
      events: steps,
    },
    meta: META,
  };
}

async function payerEstate(page: Page, isGlobal: boolean): Promise<string[]> {
  const notes: string[] = [];
  let status = 'DRAFT';
  await demoEstate(page);
  await page.route('**/api/v1/me', async (route) => {
    await route.fulfill({ json: { data: { ...ME, is_global: isGlobal }, meta: META } });
  });
  await page.route('**/api/v1/commitments/inventory', async (route) => {
    await route.fulfill({
      json: {
        data: {
          commitments: [
            {
              kind: 'savings_plan',
              commitment_id: 'sp-fake-compute-0001',
              program: 'Compute',
              account_id: 'fake-platform-a',
              region_id: null,
              applies_to: null,
              quantity: null,
              hourly_commitment: '3.2000',
              term_months: 12,
              payment_option: 'No Upfront',
              upfront_amount: '0',
              recurring_hourly: '3.2000',
              currency: 'USD',
              starts_at: '2025-11-03T00:00:00Z',
              ends_at: '2026-11-03T00:00:00Z',
              state: 'active',
            },
          ],
          unreadable: ['DynamoDB'],
        },
        meta: META,
      },
    });
  });
  await page.route('**/api/v1/commitments/calendar', async (route) => {
    await route.fulfill({
      json: {
        data: {
          months: [
            {
              month: '2026-11-01',
              commitments: ['sp-fake-compute-0001'],
              hourly_value: '3.2000',
              share: '0.6400',
              basis: 'measured',
              over_limit: true,
            },
          ],
          ladder_limit: '0.0833',
          total_hourly_value: '5.0000',
          total_basis: 'modelled',
        },
        meta: META,
      },
    });
  });
  await page.route('**/api/v1/commitments/plans', async (route) => {
    await route.fulfill({ json: planOf(status) });
  });
  await page.route('**/api/v1/commitments/plans/plan-1/approve', async (route) => {
    const body = route.request().postDataJSON() as { note: string };
    notes.push(body.note);
    status = 'APPROVED';
    await route.fulfill({ json: planOf(status) });
  });
  return notes;
}

test('a payer reads the rate, what is held, and approves the plan with a note', async ({
  page,
}) => {
  const notes = await payerEstate(page, true);
  await page.goto('/optimize/commitments');

  // The headline first: the demo bill carries no List Cost, and the rate says so.
  await expect(page.getByTestId('savings-rate-headline')).toContainText('carries a List Cost');
  await expect(page.getByTestId('commitment-inventory')).toContainText('sp-fake-compute-0001');
  await expect(page.getByTestId('commitment-unreadable')).toContainText('DynamoDB');
  await expect(page.getByTestId('over-limit-2026-11-01')).toContainText('8.33 percent');
  await expect(page.getByTestId('plan-heading')).toContainText(
    "Meter's plan for October 2026: Draft",
  );
  await expect(page.getByTestId('plan-difference')).toContainText('applies the ladder');

  const approve = page.getByRole('button', { name: "Approve this month's tranche" });
  await expect(approve).toBeDisabled();
  await page.getByLabel('Why, for the record').fill('Within the ladder');
  await approve.click();

  await expect(page.getByTestId('plan-heading')).toContainText('Approved');
  await expect(page.getByRole('button', { name: 'Record as bought' })).toBeVisible();
  await expect(page.getByTestId('plan-buy-note')).toContainText('Meter does not buy');
  await expect(page.getByTestId('plan-steps')).toContainText('Approved by p-owner');
  expect(notes).toEqual(['Within the ladder']);
});

test('a narrowed reader is told why the payer panels are not shown', async ({ page }) => {
  await payerEstate(page, false);
  await page.goto('/optimize/commitments');
  await expect(page.getByTestId('commitment-payer-only')).toContainText('whole organization');
  await expect(page.getByTestId('purchase-plans')).toHaveCount(0);
});
