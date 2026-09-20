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
  scope_coverage: { visible: 2, total: 5, is_partial: true, unit: 'accounts' },
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
      node_id: String(index).padStart(12, '0'),
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
          scope_coverage: { visible: 270, total: 300, is_partial: true, unit: 'accounts' },
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
          scope_coverage: { visible: 0, total: 300, is_partial: true, unit: 'accounts' },
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
  //
  // The screen under test is derived, never named. This journey was pinned to
  // `/cost` and then to `/cost/anomalies`, and both shipped, so it failed twice
  // for a reason that had nothing to do with the mechanism it exists to check,
  // and each failure read like a regression. It now takes whichever screen is
  // unbuilt today.
  await withSession(page);

  // Home, because Home's group holds nothing else. Every other group is folded
  // here, so the first unbuilt link is necessarily inside a closed section,
  // which is the state the next two assertions are about.
  await page.goto('/');

  const unbuilt = page.locator('nav[aria-label="Sections"] a[data-arrives]').first();
  await expect(unbuilt).toBeAttached();

  const href = await unbuilt.getAttribute('href');
  const arrives = await unbuilt.getAttribute('data-arrives');
  expect(href).toBeTruthy();
  expect(arrives).toBeTruthy();

  // Listed even while its section is closed. The navigation is an accordion, so
  // a screen in another section is in the document and not on screen. That
  // distinction is the whole point: absent would mean the roadmap is hidden,
  // and this is one expansion away. Located by attribute rather than by role,
  // because a closed details element is out of the accessibility tree and
  // getByRole would report it missing when it is merely folded.
  await expect(unbuilt).not.toBeVisible();

  const section = page.locator('nav[aria-label="Sections"] details', {
    has: page.locator(`a[href="${href ?? ''}"]`),
  });
  await section.locator('summary').click();
  await expect(unbuilt).toBeVisible();
  await unbuilt.click();
  await expect(page).toHaveURL(new RegExp(`${href ?? ''}$`));
  await expect(page.getByTestId('not-built')).toContainText(`arrives with ${arrives ?? ''}`);

  // A wrong address is a different condition and does not share the rendering.
  await page.goto('/nonsense');
  await expect(page.getByTestId('not-a-screen')).toBeVisible();
  await expect(page.getByTestId('not-built')).toHaveCount(0);
});

test('a violating dashboard is found, attributed, and its control is legible', async ({ page }) => {
  // The P2 arc that exists today. The findings screen went live with
  // TASK-P2-021, so it no longer carries the fixture band: enforcement is the
  // screen that still does, and this journey checks both ends of that.
  // The findings and groups screens went live with TASK-P2-021 and P2-012, so
  // they are stubbed rather than left to the fixture seam. Enforcement is not
  // stubbed on purpose: it is still fixture backed and this journey checks that
  // it says so.
  const meta = {
    as_of: '2026-09-11T04:00:00Z',
    collected_at: '2026-09-11T09:54:00Z',
    scope_coverage: { visible: 2, total: 3, is_partial: true, unit: 'workspaces' },
    degraded: false,
    failures: [],
  };
  await page.route('**/api/v1/query/groups', async (route) => {
    await route.fulfill({
      json: {
        data: [
          {
            cause: 'VERY_FAST_REFRESH',
            label: 'Sub minute auto refresh',
            findings: 12,
            monthly_cost: '200.00',
            severity: 'HIGH',
            as_of: meta.as_of,
            collected_at: meta.collected_at,
          },
        ],
        meta,
      },
    });
  });
  await page.route('**/api/v1/query/findings', async (route) => {
    await route.fulfill({
      json: {
        data: [finding],
        meta,
      },
    });
  });

  const finding = {
    finding_id: '11111111-1111-1111-1111-111111111111',
    dashboard_uid: 'abc123',
    dashboard_title: 'Platform overview',
    panel_title: 'Error rate by service',
    folder_uid: 'folder-platform',
    engine: 'LOGS_INSIGHTS',
    origin: 'PANEL',
    refresh_seconds: 10,
    window_seconds: 2592000,
    runs_per_day: '8640.00',
    scan_bytes_per_run: 4294967296,
    monthly_cost: '5184.00',
    provenance: 'modelled',
    measured_runs: null,
    severity: 'CRITICAL',
    cause: 'VERY_FAST_REFRESH',
    owner: 'platform-team@example.com',
    owner_source: 'FOLDER_MAP',
    why: 'Refreshes every 10 seconds against a 30 day window, so it rescans 4 GiB 8,640 times a day.',
    as_of: meta.as_of,
    collected_at: meta.collected_at,
  };
  await page.route('**/api/v1/query/findings/*', async (route) => {
    await route.fulfill({
      json: {
        data: {
          ...finding,
          query_text: 'fields @timestamp, @message | filter @message like /ERROR/',
          targets: ['/aws/ecs/meter-api'],
          region: 'eu-west-2',
          last_editor: null,
          rate_usd_per_gib: '0.005',
          accuracy_percent: null,
          // A change is still applied, so the screen offers the undo and not a
          // second remediation on top of it.
          applied_change_id: 'aaaaaaaa-0000-4000-8000-000000000001',
        },
        meta,
      },
    });
  });

  await page.goto('/governance/queries');
  await expect(page.getByTestId('fixture-band')).toHaveCount(0);

  // The systemic problem is stated above the list it is drawn from. ADR-0016.
  const groups = page.locator('table', { hasText: 'What is driving the cost' });
  await expect(groups.getByRole('row').nth(1)).toContainText('Sub minute auto refresh');

  // The groups panel sits above the list since TASK-P2-012, so the findings
  // table is the second one on the page. Located by its caption rather than by
  // position, so adding a third panel does not silently retarget this.
  const findings = page.locator('table', { hasText: 'Queries ranked by what they cost' });
  const first = findings.getByRole('row').nth(1);
  await expect(first).toContainText('Error rate by service');
  await expect(first).toContainText('rescans 4 GiB');
  await expect(first).toContainText('platform-team');

  // A modelled figure never reads like a measured one.
  await expect(first.getByTestId('figure').first()).toHaveAttribute(
    'data-provenance',
    'modelled',
  );

  // Through to the working, which must reconcile to the figure above it.
  await page.getByRole('link', { name: /Error rate by service/ }).click();
  await expect(page).toHaveURL(/\/governance\/queries\/11111111/);
  await expect(page.getByTestId('finding-working')).toContainText('1,036,800 GiB scanned per month');
  await expect(page.getByText('~ $5,184.00', { exact: false })).toBeVisible();

  // TASK-P2-019 and the two remediation routes. The control is present because
  // a change is still applied, and it is absent rather than disabled when there
  // is nothing to undo, which is the rule this screen shares with revoke.
  await expect(page.getByTestId('undo')).toBeVisible();
  await expect(page.getByTestId('remediate')).toHaveCount(0);

  await page.route('**/api/v1/query/remediate/*/undo', async (route) => {
    await route.fulfill({
      json: {
        data: {
          finding_id: '11111111-1111-1111-1111-111111111111',
          applied: true,
          reverted: true,
          detail: '',
          change_id: 'aaaaaaaa-0000-4000-8000-000000000001',
        },
        meta,
      },
    });
  });
  await page.getByTestId('undo').click();
  await expect(page.getByTestId('remediation-outcome')).toHaveAttribute('data-applied', 'true');

  // The instance list is where under counting is stopped. Route backed since
  // TASK-P2-021, so it is stubbed like the rest of the arc.
  await page.route('**/api/v1/query/instances', async (route) => {
    await route.fulfill({
      json: {
        data: [
          {
            instance_id: '0a1b2c3d-0000-4000-8000-000000000001',
            name: 'meter-prod-eu-west-1',
            kind: 'AMG',
            endpoint: 'https://g-0a1b2c3d.grafana-workspace.eu-west-1.amazonaws.com',
            account_id: '111122223333',
            region_id: 'eu-west-1',
            reachable: false,
            unreachable_reason: 'AccessDenied',
            refresh_floor_seconds: null,
            query_count: null,
            as_of: meta.as_of,
            collected_at: meta.collected_at,
          },
          {
            instance_id: '8c9d0e1f-0000-4000-8000-000000000003',
            name: 'meter-staging-eu-west-2',
            kind: 'AMG',
            endpoint: 'https://g-8c9d0e1f.grafana-workspace.eu-west-2.amazonaws.com',
            account_id: '444455556666',
            region_id: 'eu-west-2',
            reachable: true,
            unreachable_reason: null,
            refresh_floor_seconds: 30,
            // A genuine zero: read, and holding nothing. It must not be
            // confusable with the null above it.
            query_count: 0,
            as_of: meta.as_of,
            collected_at: meta.collected_at,
          },
        ],
        meta,
      },
    });
  });
  await page.goto('/governance/instances');
  const unreachable = page.getByRole('row').filter({ hasText: 'meter-prod-eu-west-1' });
  await expect(unreachable).toContainText('ACCESS DENIED');
  // A genuine zero, two rows down, still reads as zero.
  const staging = page.getByRole('row').filter({ hasText: 'meter-staging-eu-west-2' });
  await expect(staging).toContainText('0');

  // TASK-P2-017. A workspace enforcing no floor accepts a one second refresh
  // from anybody, and `none set` is not the same claim as a floor of zero.
  await expect(unreachable).toContainText('none set');
  await expect(staging).toContainText('30 s');

  // The control, its expiry in both forms, and a revoke that says what it did.
  await page.goto('/governance/enforcement');
  const throttle = page.getByRole('row').filter({ hasText: 'grafana-datasource' });
  await expect(throttle).toContainText('UTC');
  await expect(
    page.getByRole('row').filter({ hasText: 'reporting' }),
  ).toContainText('does not expire');
  await throttle.getByRole('button', { name: /revoke/i }).click();
  await expect(page.getByTestId('revoke-note')).toContainText('not connected yet');
});
