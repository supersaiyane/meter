import { expect, test } from '@playwright/test';

/**
 * TASK-P8-003, closing ISS-235: a filter lives in the address, so a link, a bookmark
 * and the browser's own back and forward all carry it.
 */

test('a filter is in the address, and back and forward walk through it', async ({ page }) => {
  await page.goto('/inventory/accounts');
  const chips = page.getByRole('group', { name: 'Filter by role health' });
  await chips.getByRole('button', { name: 'broken' }).click();
  await expect(page).toHaveURL(/status=Broken/);
  await chips.getByRole('button', { name: 'healthy' }).click();
  await expect(page).toHaveURL(/status=HEALTHY/);

  await page.goBack();
  await expect(page).toHaveURL(/status=Broken/);
  await expect(chips.getByRole('button', { name: 'broken' })).toHaveAttribute(
    'aria-pressed',
    'true',
  );

  await page.goForward();
  await expect(chips.getByRole('button', { name: 'healthy' })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
});

test('a parameter the screen does not take is named, and not applied', async ({ page }) => {
  await page.goto('/inventory/accounts?colour=red');
  await expect(page.getByTestId('ignored-filters')).toContainText('colour');
});
