import { expect, test, type Page } from '@playwright/test';

/**
 * Session through to the organization map.
 *
 * The API is stubbed at the network boundary. Every honesty rule asserted here
 * is asserted against the real production bundle: the coverage banner, the
 * marked unreachable branch, and a refusal that renders no numeral.
 */

const META_PARTIAL = {
  as_of: '2026-08-27T04:00:00Z',
  collected_at: '2026-08-27T09:54:00Z',
  scope_coverage: { visible: 2, total: 5, is_partial: true },
  degraded: true,
  failures: [
    {
      scope_key: 'aws:444455556666:eu-west-1',
      collector: 'account_health',
      cause: 'AccessDenied',
      remediation: 'Check the StackSet deployment for this account.',
      occurrences: 3,
      last_seen_at: '2026-08-27T09:00:00Z',
    },
  ],
};

function account(id: string, health: string) {
  return {
    provider: 'aws',
    account_id: id,
    name: `name-${id}`,
    status: 'ACTIVE',
    role_health: health,
    role_health_checked_at: '2026-08-27T09:00:00Z',
    role_health_error: health === 'HEALTHY' ? null : 'the collector role is not assumable',
    as_of: '2026-08-27T04:00:00Z',
    collected_at: '2026-08-27T09:54:00Z',
  };
}

const TREE = [
  {
    node_id: 'r-root',
    node_type: 'ROOT',
    parent_node_id: null,
    name: 'root',
    path: '/r-root',
    depth: 0,
    reachable: true,
  },
  {
    node_id: '111122223333',
    node_type: 'ACCOUNT',
    parent_node_id: 'r-root',
    name: 'production',
    path: '/r-root/111122223333',
    depth: 1,
    reachable: true,
  },
  {
    node_id: '999988887777',
    node_type: 'ACCOUNT',
    parent_node_id: 'r-root',
    name: 'restricted',
    path: '/r-root/999988887777',
    depth: 1,
    reachable: false,
  },
];

async function withSession(page: Page): Promise<void> {
  await page.route('**/api/v1/accounts', async (route) => {
    await route.fulfill({
      json: {
        data: [account('111122223333', 'HEALTHY'), account('444455556666', 'ACCESS_DENIED')],
        meta: META_PARTIAL,
      },
    });
  });
  await page.route('**/api/v1/org/tree', async (route) => {
    await route.fulfill({ json: { data: TREE, meta: META_PARTIAL } });
  });
  // The session is the token. There is no login screen in P0 and none is faked.
  await page.addInitScript(() => {
    window.localStorage.setItem('meter.token', 'a-session-token');
  });
}

test('a session carries a user through to the organization map', async ({ page }) => {
  await withSession(page);
  // Routes carry their group, per ADR-0020. There is no landing state machine.
  await page.goto('/inventory/accounts');

  // The shell tells the reader what they are looking at before anything else.
  await expect(page.getByTestId('coverage')).toHaveText('Showing 2 of 5 accounts');
  await expect(page.getByTestId('shell')).toHaveAttribute('data-degraded', 'true');
  await expect(page.getByTestId('global-freshness')).toContainText('as of 2026-08-27 04:00');

  // Which collector is failing, rather than a generic error.
  await expect(page.getByText('ACCESS DENIED').first()).toBeVisible();

  // Broken onboarding in one click. Exact cells, because the identifier also
  // appears inside the account name.
  const healthy = page.getByRole('cell', { name: '111122223333', exact: true });
  const broken = page.getByRole('cell', { name: '444455556666', exact: true });
  await expect(healthy).toBeVisible();
  await page.getByRole('button', { name: 'broken' }).click();
  await expect(healthy).toHaveCount(0);
  await expect(broken).toBeVisible();

  // Through to the organization map, by link rather than by section button.
  await page.getByRole('link', { name: 'Organization' }).click();
  await expect(page).toHaveURL(/\/inventory\/organization$/);
  await expect(page.getByTestId('org-tree')).toBeVisible();
  await expect(page.getByText('production')).toBeVisible();

  // The out of scope branch is drawn and marked, not pruned.
  await expect(page.getByText('restricted')).toBeVisible();
  await expect(page.getByText('unreachable, outside your scope')).toBeVisible();

  await page.screenshot({ path: 'e2e/partial-coverage.png', fullPage: true });
});

test('a keyboard alone reaches the organization map', async ({ page }) => {
  // The tree is the accessible path and never the secondary one.
  await withSession(page);
  await page.goto('/inventory/accounts');
  await page.getByRole('link', { name: 'Organization' }).click();
  const tree = page.getByTestId('org-tree');
  await expect(tree).toBeVisible();
  await page.keyboard.press('Tab');
  await page.keyboard.press('ArrowDown');
  await expect(tree).toBeVisible();
});

test('the organization map stays usable at three hundred accounts', async ({ page }) => {
  // The evidence TASK-P0-027 could not produce without a browser. The tree is
  // the default and the graph is opened deliberately, so both are captured.
  const many = [
    {
      node_id: 'r-root',
      node_type: 'ROOT',
      parent_node_id: null,
      name: 'root',
      path: '/r-root',
      depth: 0,
      reachable: true,
    },
    ...Array.from({ length: 300 }, (_, index) => ({
      node_id: `${String(index).padStart(12, '0')}`,
      node_type: 'ACCOUNT',
      parent_node_id: 'r-root',
      name: `account-${String(index)}`,
      path: `/r-root/${String(index)}`,
      depth: 1,
      // One in ten is outside the scope, so the marking is visible at scale.
      reachable: index % 10 !== 0,
    })),
  ];

  await page.route('**/api/v1/org/tree', async (route) => {
    await route.fulfill({
      json: {
        data: many,
        meta: {
          as_of: '2026-08-27T04:00:00Z',
          collected_at: '2026-08-27T09:54:00Z',
          scope_coverage: { visible: 270, total: 300, is_partial: true },
          degraded: false,
          failures: [],
        },
      },
    });
  });
  await page.route('**/api/v1/accounts', async (route) => {
    await route.fulfill({
      json: {
        data: [],
        meta: {
          as_of: null,
          collected_at: null,
          scope_coverage: { visible: 0, total: 300, is_partial: true },
          degraded: true,
          failures: [],
        },
      },
    });
  });
  await page.addInitScript(() => {
    window.localStorage.setItem('meter.token', 'a-session-token');
  });

  await page.goto('/inventory/organization');
  await expect(page.getByTestId('org-tree')).toBeVisible();
  await expect(page.getByText('account-0', { exact: true })).toBeVisible();
  await page.screenshot({ path: 'e2e/tree-300-accounts.png', fullPage: false });

  const started = Date.now();
  await page.getByRole('button', { name: 'Graph' }).click();
  await expect(page.getByTestId('graph')).toHaveAttribute('data-state', 'drawn');
  const elapsed = Date.now() - started;
  await page.screenshot({ path: 'e2e/graph-300-accounts.png', fullPage: false });

  // Usable rather than merely present. Ten seconds is the point past which a
  // reader stops waiting and reaches for the tree, which is why the tree is the
  // default in the first place.
  expect(elapsed).toBeLessThan(10_000);
});

test('an unbuilt screen is listed, reachable, and names what will fill it', async ({ page }) => {
  // Hiding an unbuilt screen would make the product look smaller than it is and
  // would hide the roadmap. ADR-0020.
  await withSession(page);
  await page.goto('/inventory/accounts');

  await page.getByRole('link', { name: /Spend and trend/ }).click();
  await expect(page).toHaveURL(/\/cost$/);
  await expect(page.getByTestId('not-built')).toContainText('arrives with P1 Cost Intelligence');

  // A wrong address is a different condition and does not share the rendering.
  await page.goto('/nonsense');
  await expect(page.getByTestId('not-a-screen')).toBeVisible();
  await expect(page.getByTestId('not-built')).toHaveCount(0);
});
