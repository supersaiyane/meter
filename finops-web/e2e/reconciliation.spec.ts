import { expect, test, type Page } from '@playwright/test';

import { demoEstate, RECONCILED, reconciliationOf } from './estate';

/**
 * Invoice reconciliation, end to end. FEAT-076, TASK-P10-005.
 *
 * The route is stubbed, as every journey stubs its routes. The demo estate answers with the
 * newest closed period, which matches its rows; the journey through the screen answers with the
 * oldest, which does not, beside a Marketplace invoice no row carries. What it proves is the
 * promise P10 makes a reader: every comparison is said in words with its difference beside it,
 * and nothing that was not compared is shown as a figure.
 */

const META = {
  as_of: '2026-09-03T06:00:00Z',
  collected_at: '2026-09-03T06:05:00Z',
  scope_coverage: { visible: 1, total: 1, is_partial: false, unit: 'payer' },
  degraded: false,
  failures: [],
};

const PAYER_WIDE =
  'Invoice reconciliation needs the whole organization in view. An invoice totals every ' +
  "account under the payer, so a comparison over fewer accounts would be a different number under the invoice's name. ADR-0025.";

async function answering(page: Page, body: unknown, status = 200): Promise<void> {
  await page.route('**/api/v1/cost/reconciliation*', async (route) => {
    await route.fulfill({ status, json: body });
  });
}

test('the rail reaches every comparison in words, its difference beside it', async ({
  page,
}) => {
  await demoEstate(page);
  await answering(page, {
    data: reconciliationOf([
      {
        ...RECONCILED,
        invoice_before_tax: '6200.1500',
        invoice_billed_cost: '6200.1500',
        difference_before_tax: '-2.5000',
        state: 'Mismatched',
      },
      {
        ...RECONCILED,
        invoice_id: 'fake-marketplace-2026-08',
        invoice_issuer_name: 'Fake Marketplace',
        invoice_before_tax: '40.0000',
        invoice_billed_cost: '40.0000',
        meter_before_tax: null,
        meter_tax: null,
        difference_before_tax: null,
        difference_tax: null,
        state: 'No rows',
      },
    ]),
    meta: META,
  });
  await page.goto('/');

  const rail = page.locator('#sections');
  await rail.getByText('Report', { exact: true }).click();
  await rail.getByRole('link', { name: 'Invoice reconciliation' }).click();
  await expect(page).toHaveURL(/\/report\/reconciliation/);

  const rows = page.getByTestId('reconciliation-row');
  await expect(rows).toHaveCount(2);
  const mismatch = rows.filter({ hasText: 'fake-invoice-2026-08' });
  await expect(mismatch.getByTestId('reconciliation-state')).toHaveText(
    'Differs from the invoice',
  );
  await expect(mismatch.getByTestId('reconciliation-difference')).toHaveText(/-\$2\.50/);
  const marketplace = rows.filter({ hasText: 'fake-marketplace-2026-08' });
  await expect(marketplace.getByTestId('reconciliation-state')).toHaveText(
    'No cost row carries this invoice',
  );
  await expect(marketplace.getByTestId('reconciliation-difference')).toHaveText('Not compared');
  await expect(page.getByTestId('reconciliation-provenance')).toHaveAttribute(
    'data-provenance',
    'measured',
  );
});

test("the practitioner's Overview says how much of the invoice Meter matches", async ({
  page,
}) => {
  await demoEstate(page);
  await page.goto('/');
  await expect(page.getByRole('radio', { name: 'FinOps practitioner' })).toBeChecked();

  const tile = page.getByRole('region', { name: 'Matches the invoice' });
  await expect(tile).toHaveAttribute('data-provenance', 'measured');
  await expect(tile).toContainText('1 of 1 invoices matched');
  await tile.getByRole('link', { name: 'Matches the invoice' }).click();
  await expect(page).toHaveURL(/\/report\/reconciliation/);
  await expect(page.getByTestId('reconciliation-state')).toHaveText('Matches the invoice');
});

test('a reader who cannot see the whole payer is told why and shown no total', async ({
  page,
}) => {
  await demoEstate(page);
  await answering(page, { detail: PAYER_WIDE }, 403);
  await page.goto('/report/reconciliation');
  await expect(page.getByTestId('reconciliation-instead')).toHaveText(PAYER_WIDE);
  await expect(page.getByTestId('reconciliation-row')).toHaveCount(0);
});
