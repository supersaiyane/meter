import { expect, test, type Page } from '@playwright/test';

/**
 * The topology surface, end to end. TASK-P4-011.
 *
 * The arc a person actually walks: open the map, be told before seeing anything that two
 * slices of the estate could not be read, pick a resource, and find that the picture they
 * are now looking at is both truncated and drawn over a refused account. Both notices are
 * above the graph, and this journey asserts they are above it by position rather than by
 * presence, because a notice under the drawing is a footnote and the reader has already
 * concluded.
 *
 * The routes are stubbed, because a failed route deliberately does not fall back to a
 * fixture: it raises, the screen renders the typed cause, and no numeral appears. That is
 * the right behaviour and it means a journey against a dead API would be testing the
 * failure state. The backend has its own suite and is called there.
 */

const AS_OF = '2026-08-24T06:00:00Z';
const COLLECTED_AT = '2026-08-24T06:05:00Z';

/** Eighteen of twenty slices, in slices rather than accounts. The unit is the point. */
const META = {
  as_of: AS_OF,
  collected_at: COLLECTED_AT,
  scope_coverage: { visible: 18, total: 20, is_partial: true, unit: 'slices' },
  degraded: true,
  failures: [],
};

const ROOT = '3f8c1a2b-4d5e-4f60-8a71-9b2c3d4e5f60';
const SUBNET = '4a9d2b3c-5e6f-4071-9b82-0c3d4e5f6071';
const FAR = '5bae3c4d-6f70-4182-8c93-1d4e5f607182';

function slice(
  account: string,
  region: string | null,
  state: string,
  cause: string | null,
): Record<string, unknown> {
  return {
    account_id: account,
    region_id: region,
    state,
    cause,
    node_count: 0,
    edge_count: 0,
    as_of: AS_OF,
    collected_at: COLLECTED_AT,
  };
}

async function withSession(page: Page): Promise<void> {
  // The session is the token. There is no login screen in P0 and none is faked.
  await page.addInitScript(() => {
    window.localStorage.setItem('meter.token', 'a-session-token');
  });

  await page.route('**/api/v1/inventory/roots*', async (route) => {
    await route.fulfill({
      json: {
        data: {
          roots: [
            {
              node_id: ROOT,
              provider_id: 'arn:aws:ec2:fake-region-a:fake-platform-a:vpc/vpc-platform',
              account_id: 'fake-platform-a',
              node_kind: 'VPC',
              resource_type: 'AWS::EC2::VPC',
              region_id: 'fake-region-a',
              name: 'platform',
            },
          ],
        },
        meta: {
          ...META,
          scope_coverage: { visible: 5, total: 5, is_partial: false, unit: 'accounts' },
        },
      },
    });
  });

  await page.route('**/api/v1/inventory/coverage*', async (route) => {
    await route.fulfill({
      json: {
        data: {
          incomplete: [
            // A read happened and fell short.
            slice('fake-platform-a', 'fake-region-c', 'PARTIAL', 'NotOptedIn'),
            // No read has been attempted. A different state, and the screen says which.
            slice('fake-product-b', 'fake-region-b', 'UNREAD', 'NotYetAttempted'),
          ],
        },
        meta: META,
      },
    });
  });

  // FEAT-056. The resource list, stubbed with a narrowed answer as well as the full one, so
  // the journey can prove the filter reaches the server rather than the browser.
  await page.route('**/api/v1/inventory/resources?*', async (route) => {
    const narrowed = new URL(route.request().url()).searchParams.get('node_kind') !== null;
    const every = [
      {
        node_id: ROOT,
        provider_id: 'arn:aws:ec2:fake-region-a:fake-platform-a:vpc/vpc-platform',
        account_id: 'fake-platform-a',
        node_kind: 'VPC',
        resource_type: 'AWS::EC2::VPC',
        region_id: 'fake-region-a',
        availability_zone: null,
        name: 'platform',
        as_of: AS_OF,
        collected_at: COLLECTED_AT,
      },
      {
        node_id: SUBNET,
        provider_id: 'arn:aws:ec2:fake-region-a:fake-platform-a:subnet/subnet-a',
        account_id: 'fake-platform-a',
        node_kind: 'SUBNET',
        resource_type: 'AWS::EC2::Subnet',
        region_id: 'fake-region-a',
        availability_zone: 'fake-region-a-a',
        name: 'private-a',
        as_of: AS_OF,
        collected_at: COLLECTED_AT,
      },
    ];
    const resources = narrowed ? [every[1]] : every;
    await route.fulfill({
      json: {
        data: {
          resources,
          // Two of twenty seven, so the caption has to say it is a page.
          total: narrowed ? 1 : 27,
          limit: 50,
          offset: 0,
          filters: {
            account_id: ['fake-platform-a'],
            region_id: ['fake-region-a'],
            node_kind: ['SUBNET', 'VPC'],
            resource_type: ['AWS::EC2::Subnet', 'AWS::EC2::VPC'],
          },
        },
        meta: {
          ...META,
          scope_coverage: { visible: 18, total: 20, is_partial: true, unit: 'slices' },
        },
      },
    });
  });

  // FEAT-053. The drill down destination, stubbed for the same reason the others are: a
  // failed route raises rather than falling back to a fixture, so a journey against a dead
  // API would be asserting the failure state.
  await page.route('**/api/v1/inventory/nodes/**', async (route) => {
    await route.fulfill({
      json: {
        data: {
          node: {
            node_id: ROOT,
            provider_id: 'arn:aws:ec2:fake-region-a:fake-platform-a:vpc/vpc-platform',
            account_id: 'fake-platform-a',
            node_kind: 'VPC',
            resource_type: 'AWS::EC2::VPC',
            region_id: 'fake-region-a',
            availability_zone: null,
            name: 'platform',
            as_of: AS_OF,
            collected_at: COLLECTED_AT,
          },
          // PARTIAL, so the page has to warn before it lists a single neighbour.
          coverage: slice('fake-platform-a', 'fake-region-a', 'PARTIAL', 'Throttled'),
          neighbours: [
            {
              node_id: SUBNET,
              provider_id: 'arn:aws:ec2:fake-region-a:fake-platform-a:subnet/subnet-a',
              account_id: 'fake-platform-a',
              node_kind: 'SUBNET',
              resource_type: 'AWS::EC2::Subnet',
              region_id: 'fake-region-a',
              availability_zone: 'fake-region-a-a',
              name: 'private-a',
              as_of: AS_OF,
              collected_at: COLLECTED_AT,
            },
          ],
          edges: [
            {
              from_node_id: ROOT,
              to_node_id: SUBNET,
              edge_kind: 'CONTAINS',
              is_cross_account: false,
              source: 'CONFIG_RELATIONSHIP',
              leaves_the_graph: false,
            },
            {
              from_node_id: ROOT,
              to_node_id: FAR,
              edge_kind: 'PEERS_WITH',
              is_cross_account: true,
              source: 'ec2:DescribeVpcPeeringConnections',
              leaves_the_graph: true,
            },
          ],
          findings: [],
          // No findings listed and three that joined to nothing, which is the combination
          // that would otherwise read as a clean resource.
          unmatched_findings: 3,
          monthly_cost: null,
          cost_period: '2026-08-01',
        },
        meta: {
          ...META,
          scope_coverage: { visible: 0, total: 1, is_partial: true, unit: 'slices' },
        },
      },
    });
  });

  await page.route('**/api/v1/inventory/topology/**', async (route) => {
    await route.fulfill({
      json: {
        data: {
          root_id: ROOT,
          nodes: [
            {
              node_id: ROOT,
              provider_id: 'arn:aws:ec2:fake-region-a:fake-platform-a:vpc/vpc-platform',
              account_id: 'fake-platform-a',
              node_kind: 'VPC',
              resource_type: 'AWS::EC2::VPC',
              region_id: 'fake-region-a',
              availability_zone: null,
              name: 'platform',
              as_of: AS_OF,
              collected_at: COLLECTED_AT,
            },
            {
              node_id: SUBNET,
              provider_id: 'arn:aws:ec2:fake-region-a:fake-platform-a:subnet/subnet-a',
              account_id: 'fake-platform-a',
              node_kind: 'SUBNET',
              resource_type: 'AWS::EC2::Subnet',
              region_id: 'fake-region-a',
              availability_zone: 'fake-region-a-a',
              name: 'private-a',
              as_of: AS_OF,
              collected_at: COLLECTED_AT,
            },
          ],
          edges: [
            {
              from_node_id: ROOT,
              to_node_id: SUBNET,
              edge_kind: 'CONTAINS',
              is_cross_account: false,
              source: 'CONFIG_RELATIONSHIP',
              leaves_the_graph: false,
            },
            {
              from_node_id: ROOT,
              to_node_id: FAR,
              edge_kind: 'PEERS_WITH',
              is_cross_account: true,
              source: 'ec2:DescribeVpcPeeringConnections',
              leaves_the_graph: true,
            },
          ],
          coverage: [
            slice('fake-platform-a', 'fake-region-a', 'COMPLETE', null),
            slice('fake-product-denied', 'fake-region-a', 'PARTIAL', 'AccessDenied'),
          ],
          depth_reached: 1,
          max_depth: 4,
          omitted_nodes: 11,
          omitted_is_exact: true,
          max_nodes: 2,
        },
        meta: {
          ...META,
          scope_coverage: { visible: 1, total: 2, is_partial: true, unit: 'slices' },
        },
      },
    });
  });
}

test.describe('the topology map', () => {
  test.beforeEach(async ({ page }) => {
    await withSession(page);
  });

  test('says what could not be read before it draws anything', async ({ page }) => {
    await page.goto('/inventory/topology');
    const estate = page.getByTestId('estate-coverage');
    await expect(estate).toBeVisible();
    await expect(estate).toContainText('2 slices of the estate could not be read');
    // Partial and unread are different states and the screen keeps them apart.
    await expect(estate).toContainText('fake-region-c is PARTIAL (NotOptedIn)');
    await expect(estate).toContainText('fake-region-b is UNREAD (NotYetAttempted)');
    // And no canvas yet, because nothing has been chosen.
    await expect(page.getByTestId('topology-canvas')).toHaveCount(0);
  });

  test('walks the map and reports both the truncation and the partial slice', async ({
    page,
  }) => {
    await page.goto('/inventory/topology');
    await page.getByRole('button', { name: /AWS::EC2::VPC/ }).click();

    // The truncation, with a number rather than an adjective.
    const truncation = page.getByTestId('truncation');
    await expect(truncation).toBeVisible();
    await expect(truncation).toContainText('Showing 2 of 13 resources');
    await expect(truncation).toContainText('11 were omitted by the 2 node limit');

    // The partial slice this particular map crossed, which is a different account from the
    // two in the estate wide banner.
    const crossed = page.getByTestId('subgraph-coverage');
    await expect(crossed).toBeVisible();
    await expect(crossed).toContainText('fake-product-denied');
    await expect(crossed).toContainText('PARTIAL (AccessDenied)');

    // Both above the drawing, asserted by position. A notice under the graph is a footnote.
    const canvasBox = await page.getByTestId('topology-canvas').boundingBox();
    const truncationBox = await truncation.boundingBox();
    const crossedBox = await crossed.boundingBox();
    expect(canvasBox).not.toBeNull();
    expect(truncationBox).not.toBeNull();
    expect(crossedBox).not.toBeNull();
    expect(truncationBox?.y ?? 0).toBeLessThan(canvasBox?.y ?? 0);
    expect(crossedBox?.y ?? 0).toBeLessThan(canvasBox?.y ?? 0);
  });

  test('carries the same graph in a table a keyboard and a reader can use', async ({
    page,
  }) => {
    await page.goto('/inventory/topology');
    await page.getByRole('button', { name: /AWS::EC2::VPC/ }).click();
    await expect(page.getByTestId('topology-canvas')).toBeVisible();

    // The accessible equivalent, with the facts the drawing encodes visually.
    await expect(page.getByRole('rowheader', { name: 'platform' })).toBeVisible();
    await expect(page.getByRole('cell', { name: 'AWS::EC2::Subnet' })).toBeVisible();
    await expect(page.getByText(/outside this view/)).toBeVisible();
    await expect(
      page.getByRole('cell', { name: 'ec2:DescribeVpcPeeringConnections' }),
    ).toBeVisible();

    // A keyboard reaches the canvas, which the organization map already proves is possible.
    await expect(page.getByTestId('topology-canvas')).toHaveAttribute('tabindex', '0');
  });

  test('says slices rather than accounts in the trust strip', async ({ page }) => {
    // A map drawn from one of two slices is partial in a way counting accounts cannot
    // express, and a plausible number in that slot has been the defect three times.
    await page.goto('/inventory/topology');
    await page.getByRole('button', { name: /AWS::EC2::VPC/ }).click();
    await expect(page.getByTestId('coverage')).toContainText('slices');
  });

  test('walks from the map into one resource, and is told what the page cannot say', async ({
    page,
  }) => {
    // FEAT-053. The arc the map existed without: a reader finds a resource on the picture and
    // has somewhere to go. The three assertions after the navigation are the ones worth
    // having, because each is a place the page could read as reassuring and does not.
    await page.goto('/inventory/topology');
    await page.getByRole('button', { name: /AWS::EC2::VPC/ }).click();
    await expect(page.getByTestId('topology-canvas')).toBeVisible();

    await page.getByRole('link', { name: 'platform' }).click();
    await expect(page).toHaveURL(new RegExp(`/inventory/resources/${ROOT}$`));
    await expect(page.getByTestId('entity-arn')).toContainText('vpc/vpc-platform');

    // One, the neighbour list may be short, said above the list rather than under it.
    const warning = page.getByTestId('entity-coverage');
    await expect(warning).toContainText(
      'fake-platform-a in fake-region-a is PARTIAL (Throttled)',
    );
    const neighbours = page.getByTestId('entity-neighbours');
    const warningBox = await warning.boundingBox();
    const neighbourBox = await neighbours.boundingBox();
    expect(warningBox?.y ?? 0).toBeLessThan(neighbourBox?.y ?? 0);

    // Two, the bill does not mention it, which is not the same as costing nothing.
    await expect(page.getByTestId('entity-cost-absent')).toContainText(
      'not the same as costing nothing',
    );
    await expect(page.getByTestId('entity-cost')).toHaveCount(0);

    // Three, an empty finding list with findings that joined to nothing is not a clean
    // resource, and the page says both halves rather than the flattering one.
    await expect(page.getByTestId('entity-findings-empty')).toBeVisible();
    await expect(page.getByTestId('entity-unmatched')).toContainText(
      '3 findings in this account could not be matched',
    );
  });

  test('narrows the resource list on the server, then opens one resource', async ({ page }) => {
    // FEAT-056, closing ISS-204. The arc the navigation promised and did not have: a reader
    // who wants a list rather than a map, narrows it, and lands on one thing.
    await page.goto('/inventory/resources');

    // The denominator first, because a page without one reads as the whole estate.
    await expect(page.getByTestId('resources-count')).toContainText('1 to 2 of 27');
    // And the estate notice above the table, not under it.
    const notice = page.getByTestId('estate-coverage');
    await expect(notice).toContainText('could not be read');
    const noticeBox = await notice.boundingBox();
    const tableBox = await page.getByTestId('resources').boundingBox();
    expect(noticeBox?.y ?? 0).toBeLessThan(tableBox?.y ?? 0);

    // The filter goes to the server. The stub answers a narrowed request differently, so a
    // client side filter would leave the total at twenty seven.
    await page.getByTestId('filter-kind').selectOption('SUBNET');
    await expect(page.getByTestId('resources-count')).toContainText('All 1');

    // And onward to the resource itself, which is what the list is for.
    await page.getByRole('link', { name: 'private-a' }).click();
    await expect(page).toHaveURL(new RegExp(`/inventory/resources/${SUBNET}$`));
  });
});
