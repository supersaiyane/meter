import { expect, test } from '@playwright/test';

import { demoEstate } from './estate';

/**
 * The Overview's three dashboards, FEAT-070, in the built bundle: the FinOps practitioner's as
 * drawn opens first, the Executive and Engineering ones are a click away, and the reader's
 * choice outlives a reload.
 */

test('opens on the dashboard as drawn, offers the other two, and remembers the choice', async ({
  page,
}) => {
  await demoEstate(page);
  await page.goto('/');

  await expect(page.getByRole('radio', { name: 'FinOps practitioner' })).toBeChecked();
  await expect(page.getByRole('region', { name: 'Showback by team' })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Meter cost, this month' })).toBeVisible();

  await page.getByText('Executive', { exact: true }).click();
  await expect(page.getByRole('region', { name: 'Top movers' })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Top 10 accounts' })).toBeVisible();

  await page.reload();
  await expect(page.getByRole('radio', { name: 'Executive' })).toBeChecked();

  await page.getByText('Engineering lead', { exact: true }).click();
  await expect(page.getByRole('link', { name: 'Top findings by dollar' })).toBeVisible();
  // Meter's own cost is on the front page whichever dashboard is open, constraint 7.
  await expect(page.getByRole('region', { name: 'Meter cost, this month' })).toBeVisible();
});
