import { expect, test, type Page } from '@playwright/test';

/**
 * Motion, end to end. TASK-P8-018, P8 spec section 2.
 *
 * The owner chose rich motion later on 2026-10-05: a screen fades in, its panels rise into place
 * and a chart draws in. Every other journey runs with reduced motion so it reads the settled
 * screen; this one turns motion on and proves it is there, then proves a reader who asks for
 * reduced motion gets none of it. It reads the computed animation rather than watching one run,
 * so it does not depend on how fast the machine is.
 */

const META = {
  as_of: '2026-08-27T04:00:00Z',
  collected_at: '2026-08-27T09:54:00Z',
  scope_coverage: { visible: 1, total: 1, is_partial: false, unit: 'accounts' },
  degraded: false,
  failures: [],
};

const ACCOUNT = {
  provider: 'aws',
  account_id: 'fake-platform-a',
  name: 'Platform',
  status: 'ACTIVE',
  role_health: 'HEALTHY',
  role_health_checked_at: '2026-08-27T09:00:00Z',
  role_health_error: null,
  as_of: '2026-08-27T04:00:00Z',
  collected_at: '2026-08-27T09:54:00Z',
};

/** The Accounts screen's table, a panel that rises in. Its first child is the column chooser,
 * which is a control and not a panel. */
const PANEL = "main > section > [data-testid='state'] > [data-testid='table-scroll']";

async function accountsScreen(page: Page): Promise<void> {
  await page.addInitScript(() => {
    window.localStorage.setItem('meter.token', 'a-session-token');
  });
  await page.route('**/api/v1/accounts*', async (route) => {
    await route.fulfill({ json: { data: [ACCOUNT], meta: META } });
  });
  await page.route('**/api/v1/org/tree', async (route) => {
    await route.fulfill({ json: { data: [], meta: META } });
  });
  await page.goto('/inventory/accounts');
  await expect(page.locator(PANEL).first()).toBeVisible();
}

/** The animation the screen and its first panel are given, as the browser computed them. */
async function animations(page: Page): Promise<{ screen: string; panel: string }> {
  return page.evaluate((panelSelector) => {
    const screen = document.querySelector("[data-testid='shell'] > main");
    const panel = document.querySelector(panelSelector);
    return {
      screen: screen ? getComputedStyle(screen).animationName : 'missing',
      panel: panel ? getComputedStyle(panel).animationName : 'missing',
    };
  }, PANEL);
}

test.describe('with motion allowed', () => {
  test.use({ contextOptions: { reducedMotion: 'no-preference' } });

  test('a screen fades in and its panels rise into place', async ({ page }) => {
    await accountsScreen(page);
    expect(await animations(page)).toEqual({ screen: 'meter-fade', panel: 'meter-rise' });
  });
});

test.describe('for a reader who asks for reduced motion', () => {
  test.use({ contextOptions: { reducedMotion: 'reduce' } });

  test('nothing fades, rises or lifts', async ({ page }) => {
    await accountsScreen(page);
    expect(await animations(page)).toEqual({ screen: 'none', panel: 'none' });
  });
});
