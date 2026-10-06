import { expect, test, type Page } from '@playwright/test';

import { demoEstate } from './estate';

/**
 * Every screen at every width. TASK-P8-018 and the owner's feedback of 2026-10-05.
 *
 * The shell was called done after a look at 1440 pixels. At or below 1024 the collapsed rail
 * squeezed every screen into a 64 pixel column, and on a phone a row of chips, a forecast
 * figure, a select and a bare table each pushed the page sideways. A sweep at six widths found
 * all of it and then went with the scratchpad that held it. This is that sweep, kept.
 *
 * The screens are read off the rail, so a screen added later is swept without anybody
 * remembering to add it here. The demo estate gives the screens it covers their figures and
 * tables, because a layout is only proven against content. Every other call is answered with a
 * failure, so those screens are measured in the state they show when the API is down, which
 * must not scroll sideways either. The theme is not a dimension: it changes colours, a panel's
 * radius and its blur, and none of them moves an edge.
 */

const NARROW_WIDTHS = [320, 375, 768, 1024] as const;
const WIDE_WIDTHS = [1280, 1920] as const;
const HEIGHT = 900;

/** The rail's column, open and hidden. layout.css. */
const RAIL = { expanded: 248, collapsed: 64 } as const;

/** Sub pixel rounding. Anything wider is a real overflow. */
const SLACK = 1;

type RailState = keyof typeof RAIL;

interface Measure {
  /** How far the page scrolls sideways. */
  overflow: number;
  /** The first element that reaches past the right edge, named for the failure message. */
  culprit: string | null;
  layout: string | undefined;
  rail: number;
  main: number;
  /** The width the shell leaves the screen once its padding, gap and rail are taken. */
  room: number;
}

/** A call the estate does not answer fails, as it would with the API down. */
async function everythingElseFails(page: Page): Promise<void> {
  await page.route('**/api/v1/**', async (route) => {
    await route.fulfill({ status: 503, body: 'The API is not running in this journey.' });
  });
}

/**
 * Routes registered later win, so the estate is laid over the failure. The rail state is
 * stored only when nothing is, so a choice made during the journey outlives a reload.
 */
async function estate(page: Page, rail: RailState): Promise<void> {
  await everythingElseFails(page);
  await demoEstate(page);
  await page.addInitScript((state) => {
    if (window.localStorage.getItem('meter.nav') === null) {
      window.localStorage.setItem('meter.nav', state);
    }
  }, rail);
}

/** Every screen the rail links to, including the ones that say what will fill them. */
async function railScreens(page: Page): Promise<string[]> {
  await page.goto('/');
  const paths = await page
    .locator('#sections a')
    .evaluateAll((links) => links.map((link) => link.getAttribute('href') ?? ''));
  const screens = [...new Set(paths.filter((path) => path.startsWith('/')))];
  // A rail read wrongly would sweep nothing and pass.
  expect(screens).toContain('/analyze/explorer');
  return screens;
}

async function settled(page: Page): Promise<void> {
  await expect(page.getByTestId('screen-title')).toBeVisible();
  await expect(page.locator("[aria-busy='true']")).toHaveCount(0);
}

function measure(page: Page): Promise<Measure> {
  return page.evaluate((slack) => {
    const root = document.documentElement;
    const shell = document.querySelector<HTMLElement>("[data-testid='shell']");
    const rail = shell?.querySelector(':scope > header');
    const main = shell?.querySelector(':scope > main');
    if (!shell || !rail || !main) {
      throw new Error('The shell, its rail or its main element is missing.');
    }
    const style = getComputedStyle(shell);
    const wide = shell.dataset.layout === 'wide';
    const railWidth = rail.getBoundingClientRect().width;
    const padding = parseFloat(style.paddingLeft) + parseFloat(style.paddingRight);
    const beside = wide ? parseFloat(style.columnGap) + railWidth : 0;
    const overflow = root.scrollWidth - root.clientWidth;
    let culprit: string | null = null;
    if (overflow > slack) {
      for (const element of Array.from(document.querySelectorAll('body *'))) {
        const box = element.getBoundingClientRect();
        if (box.right > root.clientWidth + slack) {
          const testid = element.getAttribute('data-testid');
          const name = testid ? `[data-testid='${testid}']` : element.tagName.toLowerCase();
          culprit = `${name} ends at ${String(Math.round(box.right))}`;
          break;
        }
      }
    }
    return {
      overflow,
      culprit,
      layout: shell.dataset.layout,
      rail: Math.round(railWidth),
      main: main.getBoundingClientRect().width,
      room: shell.getBoundingClientRect().width - padding - beside,
    };
  }, SLACK);
}

/** What is wrong with one screen at one width, in words, or nothing. */
function problems(
  path: string,
  width: number,
  rail: RailState | 'bar',
  found: Measure,
): string[] {
  const where = `${path} at ${String(width)} (${rail})`;
  const wrong: string[] = [];
  if (found.overflow > SLACK) {
    wrong.push(
      `${where} scrolls ${String(found.overflow)}px sideways: ${found.culprit ?? '?'}`,
    );
  }
  if (Math.abs(found.main - found.room) > SLACK) {
    wrong.push(`${where} gives the screen ${String(found.main)}px of ${String(found.room)}px`);
  }
  if (rail !== 'bar' && found.rail !== RAIL[rail]) {
    wrong.push(
      `${where} draws the rail ${String(found.rail)}px wide, not ${String(RAIL[rail])}`,
    );
  }
  return wrong;
}

async function sweep(page: Page, width: number, rail: RailState): Promise<string[]> {
  await page.setViewportSize({ width, height: HEIGHT });
  await estate(page, rail);
  const wrong: string[] = [];
  for (const path of await railScreens(page)) {
    await page.goto(path);
    await settled(page);
    const found = await measure(page);
    const expected = found.layout === 'narrow' ? 'bar' : rail;
    wrong.push(...problems(path, width, expected, found));
  }
  return wrong;
}

test.describe('every screen at every width', () => {
  test.describe.configure({ mode: 'parallel' });

  for (const width of NARROW_WIDTHS) {
    // A hidden rail stored from a wide window is the state that squeezed every narrow screen.
    test(`at ${String(width)} pixels the screen keeps the whole width`, async ({ page }) => {
      test.setTimeout(120_000);
      expect(await sweep(page, width, 'collapsed')).toEqual([]);
    });
  }

  for (const width of WIDE_WIDTHS) {
    for (const rail of ['expanded', 'collapsed'] as const) {
      test(`at ${String(width)} pixels with the rail ${rail}`, async ({ page }) => {
        test.setTimeout(120_000);
        expect(await sweep(page, width, rail)).toEqual([]);
      });
    }
  }
});

test('on a phone the menu opens over the screen and closes on Escape and on a link', async ({
  page,
}) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await estate(page, 'expanded');
  await page.goto('/');
  await settled(page);

  const toggle = page.getByTestId('nav-toggle');
  const sections = page.locator('#sections');
  await expect(page.getByTestId('shell')).toHaveAttribute('data-layout', 'narrow');
  await expect(sections).toBeHidden();

  await toggle.click();
  await expect(toggle).toHaveAttribute('aria-expanded', 'true');
  await expect(sections).toBeVisible();
  expect((await measure(page)).overflow).toBeLessThanOrEqual(SLACK);

  await page.keyboard.press('Escape');
  await expect(sections).toBeHidden();
  await expect(toggle).toHaveAttribute('aria-expanded', 'false');

  await toggle.click();
  const analyze = page.getByTestId('group-Analyze');
  await analyze.locator('summary').click();
  await analyze.getByRole('link', { name: 'Cost Explorer' }).click();
  await expect(page).toHaveURL(/\/analyze\/explorer$/);
  await expect(sections).toBeHidden();
});

test('on a wide screen Hide gives the screen the rail and Show takes it back', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1280, height: HEIGHT });
  await estate(page, 'expanded');
  await page.goto('/analyze/explorer');
  await settled(page);

  const toggle = page.getByTestId('nav-toggle');
  const open = await measure(page);
  expect(open.rail).toBe(RAIL.expanded);

  await toggle.click();
  await expect(page.getByTestId('brand')).toBeHidden();
  await expect(page.locator('#sections')).toBeHidden();
  // Under reduced motion every property still transitions for a hundredth of a millisecond,
  // tokens.css, so the column reaches its width on the next frame rather than the one that hid
  // the sections. Measured in that frame it still reads as open, one run in five.
  await expect.poll(async () => (await measure(page)).rail).toBe(RAIL.collapsed);
  const hidden = await measure(page);
  expect(hidden.main - open.main).toBeCloseTo(RAIL.expanded - RAIL.collapsed, 0);

  // The choice is the person's, so it outlives a reload.
  await page.reload();
  await settled(page);
  expect((await measure(page)).rail).toBe(RAIL.collapsed);

  await page.getByTestId('nav-toggle').click();
  await expect(page.getByTestId('brand')).toBeVisible();
  await expect.poll(async () => (await measure(page)).rail).toBe(RAIL.expanded);
});
