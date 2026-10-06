import { expect, test, type Page } from '@playwright/test';

import { demoEstate } from './estate';

/**
 * TASK-P8-002: the shell is axe clean in both themes. TASK-P8-013: so is every screen's own
 * content, read off the rail and opened over the demo estate.
 *
 * In a real browser, because jsdom has no layout and no paint, so axe's colour
 * contrast rule never runs in the unit suite. axe-core comes from the project's
 * own dependencies and is injected as a script, so nothing new is admitted for
 * this.
 */

const SHELL = [
  "[data-testid='shell'] > header",
  "[data-testid='trust-strip']",
  "[data-testid='screen-tabs']",
] as const;

async function violationsIn(
  page: Page,
  selectors: readonly string[],
): Promise<readonly string[]> {
  await page.addScriptTag({ path: 'node_modules/axe-core/axe.min.js' });
  return page.evaluate(async (selectors) => {
    interface Found {
      readonly id: string;
      readonly help: string;
      readonly nodes: readonly { readonly target: readonly string[] }[];
    }
    const runner = (
      window as unknown as {
        axe: { run: (context: object, options: object) => Promise<{ violations: Found[] }> };
      }
    ).axe;
    // axe refuses a context that names an element the page does not have, and
    // the tabs exist only on a merged screen.
    const include = selectors.filter((selector) => document.querySelector(selector) !== null);
    const { violations } = await runner.run(
      { include: include.map((selector) => [selector]) },
      { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'] } },
    );
    return violations.map(
      (found) =>
        `${found.id}: ${found.help} at ${found.nodes.map((node) => node.target.join(' ')).join(', ')}`,
    );
  }, selectors);
}

for (const scheme of ['light', 'dark'] as const) {
  for (const path of ['/', '/inventory/accounts']) {
    test(`the shell at ${path} is axe clean in ${scheme}`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme });
      await page.goto(path);
      await expect(page.getByTestId('screen-title')).toBeVisible();
      expect(await violationsIn(page, SHELL)).toEqual([]);
    });
  }
}

/** Every screen the rail offers, read off the rail as the viewport journey reads them. */
async function railScreens(page: Page): Promise<string[]> {
  await page.goto('/');
  const paths = await page
    .locator('#sections a')
    .evaluateAll((links) => links.map((link) => link.getAttribute('href') ?? ''));
  return [...new Set(paths.filter((path) => path.startsWith('/')))];
}

for (const scheme of ['light', 'dark'] as const) {
  test(`every screen's content is axe clean in ${scheme}`, async ({ page }) => {
    test.setTimeout(180_000);
    // Anything the demo estate does not answer fails the way a stopped API does, so a screen's
    // failure state is checked as well as its figures.
    await page.route('**/api/v1/**', async (route) => {
      await route.fulfill({ status: 503, body: 'The API is not running in this journey.' });
    });
    await demoEstate(page);
    await page.emulateMedia({ colorScheme: scheme });
    const found: string[] = [];
    for (const path of await railScreens(page)) {
      await page.goto(path);
      await expect(page.getByTestId('screen-title')).toBeVisible();
      await expect(page.locator("[aria-busy='true']")).toHaveCount(0);
      found.push(...(await violationsIn(page, ['main'])).map((one) => `${path}: ${one}`));
    }
    expect(found).toEqual([]);
  });
}
