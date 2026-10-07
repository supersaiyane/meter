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

type Scheme = 'light' | 'dark';

/**
 * Transparency reduced, through the DevTools protocol, because Playwright's own emulation has
 * no switch for it. Both features are named, because this call replaces every emulated one.
 */
async function reduceTransparency(page: Page, scheme: Scheme): Promise<void> {
  const session = await page.context().newCDPSession(page);
  await session.send('Emulation.setEmulatedMedia', {
    features: [
      { name: 'prefers-color-scheme', value: scheme },
      { name: 'prefers-reduced-transparency', value: 'reduce' },
    ],
  });
}

/**
 * A browser without backdrop-filter: it drops every declaration of the property and applies
 * the stylesheet's `@supports not` block. The bundle's own stylesheet is served with exactly
 * those two changes, so the fallback checked is the one shipped. That the block applied is read
 * back off the page as each screen's first check, so a minifier that rewrote the block fails
 * the sweep rather than leaving the glass in place.
 */
async function withoutBlur(page: Page, scheme: Scheme): Promise<void> {
  await page.emulateMedia({ colorScheme: scheme });
  await page.route('**/assets/*.css', async (route) => {
    const response = await route.fetch();
    const unsupported = (await response.text())
      .replace(
        /@supports\s+not\s*\(\(\s*(?:-webkit-)?backdrop-filter[^{]*\{/g,
        '@supports (display: block) {',
      )
      .replace(/(?:-webkit-)?backdrop-filter\s*:[^;}]*;?/g, '');
    await route.fulfill({ response, body: unsupported });
  });
}

interface Glass {
  readonly dark: boolean;
  readonly reduced: boolean;
  /** Whether a panel is the opaque colour its glass would show, the fallback's first switch. */
  readonly solid: boolean;
  /** Every element drawn with a backdrop filter, by tag, test id and class. */
  readonly blurred: readonly string[];
  /** The same, for elements that are, or are inside, a table or a list. */
  readonly blurredInLists: readonly string[];
}

/** What the page draws its glass with, read from computed styles, which only a browser has. */
async function glassOn(page: Page): Promise<Glass> {
  return page.evaluate(() => {
    const named = (element: Element): string => {
      const testId = element.getAttribute('data-testid');
      const classes = [...element.classList].map((name) => `.${name}`).join('');
      return `${element.tagName.toLowerCase()}${testId === null ? '' : `[data-testid='${testId}']`}${classes}`;
    };
    const blurredIn = (selector: string): string[] =>
      [...document.querySelectorAll(selector)]
        .filter((element) => !['', 'none'].includes(getComputedStyle(element).backdropFilter))
        .map(named);
    const root = getComputedStyle(document.documentElement);
    return {
      dark: window.matchMedia('(prefers-color-scheme: dark)').matches,
      reduced: window.matchMedia('(prefers-reduced-transparency: reduce)').matches,
      solid:
        root.getPropertyValue('--surface-raised').trim() ===
        root.getPropertyValue('--surface-raised-solid').trim(),
      blurred: blurredIn('*'),
      blurredInLists: blurredIn(':is(table, ul, ol, dl), :is(table, ul, ol, dl) *'),
    };
  });
}

/** Every screen, opened over the demo estate, with anything it does not answer failing. */
async function eachScreen(
  page: Page,
  arrange: () => Promise<void>,
  check: (path: string) => Promise<readonly string[]>,
): Promise<readonly string[]> {
  await page.route('**/api/v1/**', async (route) => {
    await route.fulfill({ status: 503, body: 'The API is not running in this journey.' });
  });
  await demoEstate(page);
  await arrange();
  const found: string[] = [];
  for (const path of await railScreens(page)) {
    await page.goto(path);
    await expect(page.getByTestId('screen-title')).toBeVisible();
    await expect(page.locator("[aria-busy='true']")).toHaveCount(0);
    found.push(...(await check(path)).map((one) => `${path}: ${one}`));
  }
  return found;
}

const GLASSLESS = [
  { condition: 'with transparency reduced', arrange: reduceTransparency, reduced: true },
  { condition: 'without blur', arrange: withoutBlur, reduced: false },
] as const;

for (const scheme of ['light', 'dark'] as const) {
  for (const { condition, arrange, reduced } of GLASSLESS) {
    test(`every screen is opaque and axe clean in ${scheme} ${condition}`, async ({ page }) => {
      test.setTimeout(180_000);
      const found = await eachScreen(
        page,
        () => arrange(page, scheme),
        async () => {
          const glass = await glassOn(page);
          // The condition holds before anything is judged under it.
          expect({ dark: glass.dark, reduced: glass.reduced, solid: glass.solid }).toEqual({
            dark: scheme === 'dark',
            reduced,
            solid: true,
          });
          return [
            ...glass.blurred.map((element) => `${element} is still blurred`),
            ...(await violationsIn(page, ['main', ...SHELL])),
          ];
        },
      );
      expect(found).toEqual([]);
    });
  }
}

test('no screen draws glass inside a table or a list, and every screen has glass', async ({
  page,
}) => {
  test.setTimeout(180_000);
  const found = await eachScreen(
    page,
    async () => {
      await page.emulateMedia({ colorScheme: 'light' });
    },
    async () => {
      const glass = await glassOn(page);
      // The control: the probe sees glass where there is glass, so an empty answer below is
      // a finding and not a probe that sees nothing.
      expect(glass.blurred.length).toBeGreaterThan(0);
      return glass.blurredInLists.map((element) => `${element} is blurred inside a list`);
    },
  );
  expect(found).toEqual([]);
});
