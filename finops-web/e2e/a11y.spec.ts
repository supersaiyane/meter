import { expect, test, type Page } from '@playwright/test';

/**
 * TASK-P8-002: the shell is axe clean in both themes.
 *
 * In a real browser, because jsdom has no layout and no paint, so axe's colour
 * contrast rule never runs in the unit suite. axe-core comes from the project's
 * own dependencies and is injected as a script, so nothing new is admitted for
 * this. Scoped to what this task redraws: the rail, the trust strip and a
 * merged screen's tabs. Each screen's own content is held by TASK-P8-014.
 */

const SHELL = [
  "[data-testid='shell'] > header",
  "[data-testid='trust-strip']",
  "[data-testid='screen-tabs']",
] as const;

async function shellViolations(page: Page): Promise<readonly string[]> {
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
  }, SHELL);
}

for (const scheme of ['light', 'dark'] as const) {
  for (const path of ['/', '/inventory/accounts']) {
    test(`the shell at ${path} is axe clean in ${scheme}`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme });
      await page.goto(path);
      await expect(page.getByTestId('screen-title')).toBeVisible();
      expect(await shellViolations(page)).toEqual([]);
    });
  }
}
