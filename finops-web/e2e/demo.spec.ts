import { expect, test } from '@playwright/test';

import { demoEstate } from './estate';

/**
 * The walk in `docs/runbooks/demo.md`, in the order somebody demonstrates it.
 *
 * The other specs each prove one arc. This one exists for a different reason: a screen
 * that breaks between releases should fail the build rather than the demo, in front of
 * an audience, with no way to tell whether it is the product or the laptop.
 *
 * So it asserts a figure on every screen the runbook points at, and the distinctions
 * the runbook tells the driver to say out loud. If a number stops rendering, or the
 * commitments screen stops drawing the distinction it exists for, this goes red and
 * the runbook is wrong before anybody reads it.
 *
 * Stubbed at the network boundary like every other journey, against the real
 * production bundle.
 */

test('the demo walk reaches every screen the runbook points at', async ({ page }) => {
  await demoEstate(page);

  // 1. Home. The Effective Cost tile is the figure the runbook opens on, and it is the same
  // figure Cost Explorer shows, because the Overview reads the Explorer's own view. The bill
  // here carries no List Cost, so the savings rate says why it has no figure. FEAT-070.
  await page.goto('/');
  const spend = page.getByRole('region', { name: 'Effective Cost' });
  await expect(spend.getByTestId('kpi-value')).toHaveText('$3,782');
  await expect(page.getByRole('link', { name: 'Effective Cost', exact: true })).toBeVisible();
  await expect(
    page.getByRole('region', { name: 'Effective savings rate' }).getByTestId('kpi-unsupported'),
  ).toContainText('no List Cost');
  // P1 filled three home slots and left them saying "arrives with P1" until
  // 2026-09-20, on the front page of the demo.
  await expect(page.getByText('P1 Cost Intelligence')).toHaveCount(0);

  // 2. Cost Explorer. The open period says so rather than presenting a part month
  // as a total.
  await page.goto('/analyze/explorer');
  await expect(page.getByText(/still open/i)).toBeVisible();
  await expect(page.getByText('AmazonEC2').first()).toBeVisible();

  // 3. Allocation. The unallocated bucket is a named row, and the name is a sentence
  // rather than the API's key: an empty cell reads as a rendering fault and sends
  // somebody looking for a value that was never there.
  await page.goto('/analyze/allocation');
  await expect(page.getByTestId('allocation-unallocated')).toHaveText('Unallocated cost');
  await expect(page.getByText('814.17')).toBeVisible();

  // 4. Anomalies. The working is shown whole, because a verdict a reader cannot argue
  // with is one they have to take on trust.
  await page.goto('/analyze/anomalies');
  await expect(page.getByText(/313\.6 deviations out/)).toBeVisible();
  await expect(page.getByTestId('anomaly-judged')).toBeVisible();

  // 5. Commitments. The distinction the screen exists to draw, which is the thirty
  // seconds the runbook calls the best in the demo.
  await page.goto('/optimize/commitments');
  await expect(page.getByTestId('utilization-fake-sp-compute')).toHaveText('100.0%');
  await expect(page.getByTestId('coverage-AmazonEC2')).toHaveText('40.3%');
  await expect(page.getByTestId('commitment-waste')).toContainText('300.68');
  await expect(page.getByTestId('commitment-scope-note')).toContainText(/whole payer/i);

  // 6. Export. The screen states the total the file must sum to, which is what makes
  // the claim checkable in ten seconds, shows the rows, and the Export menu beside the
  // title offers them as a workbook or a CSV. FEAT-067.
  await page.goto('/report/exports');
  await expect(page.getByTestId('export-claim')).toContainText('3,781.93');
  await expect(page.getByTestId('export-unallocated-row')).toHaveText('Unallocated cost');
  await page.getByTestId('export-menu').getByText('Export').click();
  await expect(page.getByRole('group', { name: 'Showback' })).toBeVisible();

  // 7. Recommendations. The estimate is labelled modelled, and the finding
  // nobody owns says so in words rather than leaving a cell blank.
  await page.goto('/optimize');
  await expect(page.getByText('412.64')).toBeVisible();
  // Unowned, and its resource's team tag says whom to ask, ISS-021.
  await expect(page.getByTestId('unowned-2f3c1d4e-5a6b-4c7d-8e9f-0a1b2c3d4e5f')).toHaveText(
    'nobody yet; its team tag says platform',
  );
  await expect(
    page.getByTestId('confidence-2f3c1d4e-5a6b-4c7d-8e9f-0a1b2c3d4e5f'),
  ).toContainText('LOW on 15 days');

  // 8. Realized savings. The screen allowed to disappoint, and the inconclusive
  // row is the one the runbook tells the driver to stop on.
  await page.goto('/optimize/savings');
  await expect(page.getByTestId('total-VERIFIED')).toBeVisible();
  await expect(page.getByTestId('total-INCONCLUSIVE')).toBeVisible();
  await expect(
    page.getByTestId('unobserved-3a4b5c6d-7e8f-4a0b-9c1d-2e3f4a5b6c7d'),
  ).toContainText('not published');

  // 9. The score, with its parts on the same page. A component nobody could
  // compute says so rather than scoring nought.
  await page.goto('/plan/score');
  await expect(page.getByTestId('score-fake-product-a')).toContainText(
    'out of 85 available weight',
  );
  await expect(page.getByTestId('component-absent-verification')).toContainText(
    'rather than counted as nought',
  );
  await expect(page.getByTestId('unscored-fake-sandbox-c')).toBeVisible();
});

test('the P3 walk keeps the estimate and the realization on separate screens', async ({
  page,
}) => {
  /**
   * TASK-P3-014 against the real bundle. The two figures are different kinds of
   * number, and the whole of FEAT-029 rests on nobody adding them. A screen
   * carrying both would make that one subtraction away.
   */
  await demoEstate(page);

  await page.goto('/optimize');
  // Waited for, because the figures arrive after the page does. Reading the text the
  // moment the page loaded raced the data, and lost once the rail listed every screen.
  await expect(page.locator('main')).toContainText('412.64');
  // Lower cased, because the table headers render through a text transform and
  // innerText returns what is painted rather than what the source says.
  const recommendations = (await page.locator('body').innerText()).toLowerCase();
  expect(recommendations).toContain('412.64');
  expect(recommendations).not.toContain('cost before');

  await page.goto('/optimize/savings');
  await expect(page.locator('main')).toContainText('cost before', { ignoreCase: true });
  const savings = (await page.locator('body').innerText()).toLowerCase();
  expect(savings).toContain('cost before');
  expect(savings).not.toContain('412.64');
});

test('the commitments screen never puts the two percentages side by side', async ({ page }) => {
  // The one layout rule this feature rests on, asserted against the real bundle rather
  // than against jsdom. Two percentages meaning opposite things, adjacent, would be
  // compared by any reader, and the comparison is meaningless.
  await demoEstate(page);
  await page.goto('/optimize/commitments');

  const row = page.locator('tr', { has: page.getByTestId('utilization-fake-sp-compute') });
  await expect(row.locator('[data-testid^="coverage-"]')).toHaveCount(0);

  await expect(page.getByTestId('utilization-means')).toContainText(
    /what we paid for was used/i,
  );
  await expect(page.getByTestId('coverage-means')).toContainText(/estate is on a commitment/i);
});
