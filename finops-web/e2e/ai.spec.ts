import { expect, test } from '@playwright/test';

import { demoEstate } from './estate';

/**
 * AI spend, end to end. FEAT-085, TASK-P13-008.
 *
 * The routes are stubbed, as every journey stubs its routes, with the demo's newest closed period:
 * the bill's own model line, a connected provider's, a model line that counted no tokens, a caller
 * the bill priced nothing for and a GPU whose agent never published. What it proves is the promise
 * P13 makes a reader: every figure says measured or modelled, a cost per thousand tokens is drawn
 * past the cent, and every absence is said in words rather than drawn as nought.
 */

test('the rail reaches AI spend, each figure saying how it was arrived at', async ({
  page,
}) => {
  await demoEstate(page);
  await page.goto('/');

  const rail = page.locator('#sections');
  await rail.getByText('Analyze', { exact: true }).click();
  await rail.getByRole('link', { name: 'AI spend' }).click();
  await expect(page).toHaveURL(/\/analyze\/ai/);

  const spend = page.getByTestId('ai-spend');
  await expect(spend.getByTestId('ai-spend-row')).toHaveCount(2);
  await expect(spend.getByTestId('ai-spend-total')).toContainText('August 2026');
  await expect(spend.getByTestId('ai-connected')).toHaveText(
    'Connected: Fake OpenAI (OpenAI).',
  );

  const cloud = spend.getByTestId('ai-spend-row').filter({ hasText: 'Fake' }).first();
  await expect(cloud.getByTestId('ai-per-1k')).toContainText('$0.004467');
  await expect(cloud.getByTestId('ai-per-1k').getByTestId('figure')).toHaveAttribute(
    'data-provenance',
    'measured',
  );
  const provider = spend.getByTestId('ai-spend-row').filter({ hasText: 'OpenAI' });
  await expect(provider.getByTestId('ai-per-1k').getByTestId('figure')).toHaveAttribute(
    'data-provenance',
    'modelled',
  );
  await expect(provider.getByTestId('ai-per-request').getByTestId('figure')).toHaveAttribute(
    'data-provenance',
    'modelled',
  );
});

test('grouping by model lands in the address and says a line nothing counted', async ({
  page,
}) => {
  await demoEstate(page);
  await page.goto('/analyze/ai');
  await page.getByTestId('ai-grouping').getByRole('combobox').selectOption('model');
  await expect(page).toHaveURL(/group_by=model/);
  await expect(page.getByRole('heading', { name: 'Spend by model' })).toBeVisible();

  const silent = page.getByTestId('ai-spend-row').filter({ hasText: 'NovaCanvas' });
  await expect(silent.getByTestId('ai-per-1k')).toHaveText('no tokens counted');
  await expect(silent.getByTestId('ai-per-1k').getByTestId('figure')).toHaveCount(0);
});

test('a caller nobody priced and a GPU that never published are said, not counted', async ({
  page,
}) => {
  await demoEstate(page);
  await page.goto('/analyze/ai');

  const callers = page.getByTestId('ai-callers');
  await expect(callers.getByTestId('ai-caller-row')).toHaveCount(2);
  await expect(
    callers.getByTestId('ai-caller-cost').filter({ hasText: 'not priced' }),
  ).toHaveCount(1);

  const gpu = page.getByTestId('ai-gpu');
  const silent = gpu.locator('[data-utilization="not published"]');
  await expect(silent.getByTestId('ai-gpu-average')).toHaveText('not published');
  await expect(silent.getByTestId('percent-figure')).toHaveCount(0);
  const partly = gpu.locator('[data-utilization="partly published"]');
  await expect(partly.getByTestId('ai-gpu-published')).toHaveText('1 of 31 days, peak 71.00%');
});
