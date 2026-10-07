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

test('every figure on each dashboard links to the screen that owns it', async ({ page }) => {
  // P8 spec section 12 item 6. A figure is a panel or a tile, each a glass panel of its own, and
  // the Overview owns none of them, so each must lead to a screen the rail offers. A region
  // inside one, such as a table's scroll box, is part of that figure.
  await demoEstate(page);
  await page.goto('/');
  const screens = new Set(
    await page
      .locator('#sections a')
      .evaluateAll((links) => links.map((link) => link.getAttribute('href') ?? '')),
  );
  const unlinked: string[] = [];
  let figures = 0;
  for (const persona of ['FinOps practitioner', 'Executive', 'Engineering lead']) {
    await page.getByText(persona, { exact: true }).click();
    await expect(page.getByRole('radio', { name: persona })).toBeChecked();
    await expect(page.locator("main [aria-busy='true']")).toHaveCount(0);
    const shown = page.locator('main section.meter-panel');
    await expect(shown.first()).toBeVisible();
    for (const figure of await shown.all()) {
      figures += 1;
      const owners = await figure
        .getByRole('link')
        .evaluateAll((links) =>
          links.map((link) => new URL((link as HTMLAnchorElement).href).pathname),
        );
      if (!owners.some((owner) => screens.has(owner))) {
        unlinked.push(`${persona}: ${(await figure.getAttribute('aria-label')) ?? 'unnamed'}`);
      }
    }
  }
  expect(figures).toBeGreaterThan(0);
  expect(unlinked).toEqual([]);
});
