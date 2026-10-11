import { expect, test } from '@playwright/test';

import { demoEstate } from './estate';

/**
 * The savings ledger, end to end. FEAT-078, TASK-P11-008.
 *
 * The routes are stubbed, as every journey stubs its routes, with platform's saving held two
 * months and payments' month the bill holds nothing for. What it proves is the promise P11 makes
 * a reader: teams are ranked by what the bill showed their savings hold, measured, a person is
 * named only on their own team's credits and never ranked, and a month nobody could see is said
 * rather than counted as a zero.
 */

test('the rail reaches the ledger, and a team ranked by what its savings held', async ({
  page,
}) => {
  await demoEstate(page);
  await page.goto('/');

  const rail = page.locator('#sections');
  await rail.getByText('Optimize', { exact: true }).click();
  await rail.getByRole('link', { name: 'Savings ledger' }).click();
  await expect(page).toHaveURL(/\/optimize\/ledger/);

  await expect(page.getByTestId('team-platform')).toBeVisible();
  // Teams, never people: nobody is named until a team is chosen.
  await expect(page.getByText('alice')).toHaveCount(0);

  await page.getByTestId('team-platform').click();
  const credits = page.getByTestId('ledger-credits');
  await expect(credits.getByText('alice')).toBeVisible();
  await expect(credits.getByTestId('months-credit-held')).toHaveText(
    'October 2026: held, November 2026: held',
  );
  await expect(credits.getByTestId('figure').first()).toHaveAttribute(
    'data-provenance',
    'measured',
  );
});

test('a month the bill holds nothing for is said, not counted as nought', async ({ page }) => {
  await demoEstate(page);
  await page.goto('/optimize/ledger');
  await page.getByTestId('team-payments').click();
  await expect(page.getByTestId('months-credit-unobserved')).toHaveText(
    'October 2026: not observed',
  );
  await expect(page.getByText('platform@example.local')).toHaveCount(0);
});
