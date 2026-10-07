import { expect, test, type Page } from '@playwright/test';

/**
 * The container surfaces, end to end. TASK-P6-011.
 *
 * Three screens in three groups, per ADR-0020: what clusters cost under Cost, what they
 * reserve against what they use under Waste, and what they are under Inventory. The journey
 * asserts a figure on each, and on the waste screen asserts the cluster that cannot publish
 * requests is named with its reason rather than dropped or rendered as zero.
 *
 * Asserted here and not in the unit tests, because these are about the built bundle: the
 * three routes resolve, the navigation reaches them, and the sentences that carry the sub
 * project survive the build. Routes are stubbed for the reason `cost.spec.ts` gives.
 */

const META = {
  as_of: '2026-10-04T06:00:00Z',
  collected_at: '2026-10-04T06:05:00Z',
  scope_coverage: { visible: 2, total: 3, is_partial: true, unit: 'clusters' },
  degraded: true,
  failures: [],
};

const REGION = 'eu-west-1';
const REASON = 'Enhanced observability is not enabled, so pod requests are not published';

async function withSession(page: Page): Promise<void> {
  await page.addInitScript(() => {
    window.localStorage.setItem('meter.token', 'a-session-token');
  });

  await page.route('**/api/v1/cost/containers', async (route) => {
    await route.fulfill({
      json: {
        data: {
          clusters: [
            {
              cluster_name: 'platform-eks',
              total: '1240.00',
              allocated: '1140.80',
              unallocated: '99.20',
              workloads: [
                {
                  namespace: 'ledger',
                  workload_name: 'ledger-api',
                  workload_type: 'Deployment',
                  cost: '1140.80',
                  line_items: 30,
                },
              ],
              breakdown_available: true,
              unmeasurable_reason: null,
            },
          ],
          measured_count: 1,
          found_count: 1,
        },
        meta: { ...META, scope_coverage: { ...META.scope_coverage, visible: 1, total: 1 } },
      },
    });
  });

  await page.route('**/api/v1/waste/containers', async (route) => {
    await route.fulfill({
      json: {
        data: {
          clusters: [
            {
              cluster_name: 'platform-eks',
              account_id: 'fake-platform-a',
              region_id: REGION,
              platform: 'EKS',
              enhanced_observability: true,
              request_unavailable_reason: null,
              workloads: [
                {
                  namespace: 'ledger',
                  workload: 'ledger-api',
                  workload_kind: 'Deployment',
                  launch_type: 'EC2',
                  cpu_requested_millicores: '1000',
                  cpu_used_p99_millicores: '190',
                  memory_requested_mib: '2048',
                  memory_used_peak_mib: '400',
                  oom_status: 'NOT_KILLED',
                  observation_days: 30,
                },
              ],
            },
            {
              cluster_name: 'batch-eks',
              account_id: 'fake-platform-b',
              region_id: REGION,
              platform: 'EKS',
              enhanced_observability: false,
              request_unavailable_reason: REASON,
              workloads: [
                {
                  namespace: 'risk',
                  workload: 'risk-batch',
                  workload_kind: 'Job',
                  launch_type: 'EC2',
                  cpu_requested_millicores: null,
                  cpu_used_p99_millicores: '1800',
                  memory_requested_mib: null,
                  memory_used_peak_mib: '3100',
                  oom_status: 'UNOBSERVED',
                  observation_days: 30,
                },
              ],
            },
          ],
          measured_count: 1,
          found_count: 2,
        },
        meta: META,
      },
    });
  });

  await page.route('**/api/v1/inventory/clusters', async (route) => {
    await route.fulfill({
      json: {
        data: {
          clusters: [
            {
              cluster_name: 'platform-eks',
              account_id: 'fake-platform-a',
              region_id: REGION,
              platform: 'EKS',
              enhanced_observability: true,
              node_count: 5,
              spot_ratio: '0.4000',
              packing_efficiency: '0.6300',
              unmeasurable_reason: null,
            },
            {
              cluster_name: 'product-ecs',
              account_id: 'fake-product-a',
              region_id: REGION,
              platform: 'ECS',
              enhanced_observability: true,
              node_count: null,
              spot_ratio: null,
              packing_efficiency: null,
              unmeasurable_reason:
                'Fargate runs tasks without nodes, so there is no fleet to pack and none to price on Spot',
            },
          ],
          measured_count: 1,
          found_count: 1,
        },
        meta: { ...META, scope_coverage: { ...META.scope_coverage, visible: 1, total: 1 } },
      },
    });
  });
}

test('a cluster cost reconciles in plain sight, every figure measured', async ({ page }) => {
  await withSession(page);
  await page.goto('/analyze/kubernetes-cost');

  const cluster = page.getByTestId('container-cost-cluster').first();
  await expect(cluster.getByTestId('cost-reconciliation')).toBeVisible();
  await expect(cluster.getByTestId('cost-total').getByTestId('figure')).toHaveAttribute(
    'data-provenance',
    'measured',
  );
  await expect(page.getByTestId('container-cost-figure').first()).toBeVisible();
});

test('the cluster that cannot publish requests is named, with its reason, never a zero', async ({
  page,
}) => {
  await withSession(page);
  await page.goto('/analyze/kubernetes-rightsizing');

  await expect(page.getByTestId('containers-ratio')).toContainText('1 of 2');

  // A figure on the screen: the measurable cluster's request beside its use.
  await expect(page.getByTestId('cpu-requested').first()).toContainText('1000');

  // The unmeasurable cluster, by what it is rather than by its name.
  const unmeasured = page.locator('[data-testid="container-cluster"][data-measurable="false"]');
  await expect(unmeasured).toHaveCount(1);
  await expect(unmeasured.getByTestId('container-cluster-name')).toContainText('batch-eks');
  await expect(unmeasured.getByTestId('container-reason')).toContainText(
    'Enhanced observability',
  );
  await expect(unmeasured.getByTestId('cpu-requested')).toHaveCount(0);
  await expect(unmeasured.getByTestId('container-oom')).toHaveText('could not be observed');
});

test('every cluster is listed with its fleet, and the Fargate one says it has none', async ({
  page,
}) => {
  await withSession(page);
  await page.goto('/analyze/clusters');

  const eks = page.locator('[data-testid="cluster-row"][data-platform="EKS"]');
  await expect(eks.getByTestId('cluster-packing').getByTestId('percent-figure')).toContainText(
    '63.0',
  );

  const fargate = page.locator('[data-testid="cluster-row"][data-platform="ECS"]');
  await expect(fargate.getByTestId('cluster-packing')).toContainText('without nodes');
  await expect(fargate.getByTestId('percent-cell')).toHaveCount(0);
});
