import type {
  ApiBlastRadius,
  ApiEntity,
  ApiEnvelope,
  ApiGeographies,
  ApiGraphCoverage,
  ApiInventoryRoots,
  ApiRecommendation,
  ApiResourceList,
  ApiSubgraph,
} from '../types';
import type { ApiMeta } from '../types';

/**
 * The P4 surfaces, offline.
 *
 * The routes exist, so nothing here is served in the application: `FIXTURE_SURFACES`
 * is empty of these paths and `tests/api/test_fixture_surfaces.py` fails the build if
 * that ever stops being true. They are here because a screen test that constructs its
 * own payload inline drifts from the schema, and because a developer with no database
 * can still open the screen.
 *
 * Every fixture carries the case the screen exists to render honestly rather than a
 * tidy row of successes:
 *
 * - one region with PARTIAL coverage and a typed cause, because the screen has to name
 *   it above the graph rather than leave the region drawing as sparse
 * - one edge that leaves the graph, because the far end of a cross account edge is the
 *   most interesting thing on the map and a line to nowhere is not how to draw it
 * - a truncated subgraph, because a map showing four of thirteen nodes has to say so
 */

const AS_OF = '2026-08-24T06:00:00Z';
const COLLECTED_AT = '2026-08-24T06:05:00Z';

/**
 * The envelope these fixtures carry, with the coverage spelled out.
 *
 * Its own rather than the cost fixtures' `meta`, because that one returns a complete
 * scope in accounts and the coverage is the whole point of these three surfaces: a
 * slice unit and a partial ratio are what the screen has to render.
 */
function metaWith(visible: number, total: number): ApiMeta {
  return {
    as_of: AS_OF,
    collected_at: COLLECTED_AT,
    scope_coverage: { visible, total, is_partial: visible < total, unit: 'slices' },
    degraded: visible < total,
    failures: [],
  };
}

const ROOT = '3f8c1a2b-4d5e-4f60-8a71-9b2c3d4e5f60';
const SUBNET = '4a9d2b3c-5e6f-4071-9b82-0c3d4e5f6071';
const FAR = '5bae3c4d-6f70-4182-8c93-1d4e5f607182';

export function inventoryRootsFixture(): ApiEnvelope<ApiInventoryRoots> {
  return {
    data: {
      roots: [
        {
          node_id: ROOT,
          provider_id: 'arn:aws:ec2:us-fake-1:fake-platform-a:vpc/vpc-platform',
          account_id: 'fake-platform-a',
          node_kind: 'VPC',
          resource_type: 'AWS::EC2::VPC',
          region_id: 'us-fake-1',
          name: 'platform',
        },
        {
          // OTHER, with its real type beside it. Ten of the estate's twenty four types
          // land here, so a screen showing only the kind is a field of blank boxes.
          node_id: '6cbf4d5e-7081-4293-9da4-2e5f60718293',
          provider_id: 'arn:aws:eks:us-fake-1:fake-platform-a:cluster/platform-eks',
          account_id: 'fake-platform-a',
          node_kind: 'OTHER',
          resource_type: 'AWS::EKS::Cluster',
          region_id: 'us-fake-1',
          name: 'platform-eks',
        },
      ],
    },
    meta: metaWith(20, 20),
  };
}

export function graphCoverageFixture(): ApiEnvelope<ApiGraphCoverage> {
  return {
    data: {
      incomplete: [
        {
          account_id: 'fake-platform-a',
          region_id: 'fake-region-c',
          state: 'PARTIAL',
          cause: 'NotOptedIn',
          node_count: 0,
          edge_count: 0,
          as_of: AS_OF,
          collected_at: COLLECTED_AT,
        },
        {
          account_id: 'fake-product-b',
          region_id: 'eu-fake-1',
          state: 'UNREAD',
          cause: 'NotYetAttempted',
          node_count: 0,
          edge_count: 0,
          as_of: AS_OF,
          collected_at: COLLECTED_AT,
        },
      ],
    },
    meta: metaWith(18, 20),
  };
}

export function subgraphFixture(rootId: string): ApiEnvelope<ApiSubgraph> {
  return {
    data: {
      root_id: rootId || ROOT,
      nodes: [
        {
          node_id: rootId || ROOT,
          provider_id: 'arn:aws:ec2:us-fake-1:fake-platform-a:vpc/vpc-platform',
          account_id: 'fake-platform-a',
          node_kind: 'VPC',
          resource_type: 'AWS::EC2::VPC',
          region_id: 'us-fake-1',
          availability_zone: null,
          name: 'platform',
          as_of: AS_OF,
          collected_at: COLLECTED_AT,
        },
        {
          node_id: SUBNET,
          provider_id: 'arn:aws:ec2:us-fake-1:fake-platform-a:subnet/subnet-a',
          account_id: 'fake-platform-a',
          node_kind: 'SUBNET',
          resource_type: 'AWS::EC2::Subnet',
          region_id: 'us-fake-1',
          availability_zone: 'us-fake-1-a',
          name: 'private-a',
          as_of: AS_OF,
          collected_at: COLLECTED_AT,
        },
      ],
      edges: [
        {
          from_node_id: rootId || ROOT,
          to_node_id: SUBNET,
          edge_kind: 'CONTAINS',
          is_cross_account: false,
          source: 'CONFIG_RELATIONSHIP',
          leaves_the_graph: false,
        },
        {
          // The boundary. Its far end is in an account this read could not see, and the
          // coverage list above says why.
          from_node_id: rootId || ROOT,
          to_node_id: FAR,
          edge_kind: 'PEERS_WITH',
          is_cross_account: true,
          source: 'ec2:DescribeVpcPeeringConnections',
          leaves_the_graph: true,
        },
      ],
      coverage: [
        {
          account_id: 'fake-platform-a',
          region_id: 'us-fake-1',
          state: 'COMPLETE',
          cause: null,
          node_count: 27,
          edge_count: 40,
          as_of: AS_OF,
          collected_at: COLLECTED_AT,
        },
        {
          account_id: 'fake-product-denied',
          region_id: 'us-fake-1',
          state: 'PARTIAL',
          cause: 'AccessDenied',
          node_count: 0,
          edge_count: 0,
          as_of: AS_OF,
          collected_at: COLLECTED_AT,
        },
      ],
      depth_reached: 1,
      max_depth: 4,
      // Truncated on purpose. A map showing part of a neighbourhood has to say so.
      omitted_nodes: 11,
      omitted_is_exact: true,
      max_nodes: 2,
    },
    meta: metaWith(1, 2),
  };
}

/**
 * One resource, offline. FEAT-053.
 *
 * Deliberately not a clean resource. It carries one finding that joined, one that could
 * not be joined to anything, a PARTIAL slice, and a cost, because those four together are
 * what the screen exists to render honestly. A fixture with a complete slice, a matched
 * finding and no unmatched count would let the three hardest parts of the page go
 * unexercised by anything a developer opens locally.
 */
export function entityFixture(nodeId: string): ApiEnvelope<ApiEntity> {
  const finding: ApiRecommendation = {
    recommendation_id: '7c9e6f80-1a2b-4c3d-8e4f-5a6b7c8d9e01',
    account_id: 'fake-platform-a',
    source: 'METER',
    waste_class: 'EBS_GP2_TO_GP3',
    resource_id: 'arn:aws:ec2:us-fake-1:fake-platform-a:vpc/vpc-platform',
    region_id: 'us-fake-1',
    estimated_monthly_saving: '18.4000',
    confidence: 'HIGH',
    severity: 'LOW',
    observation_days: 30,
    lifecycle: 'OPEN',
    // Unowned, which is the state ISS-021 says a finding dies in, and the state the
    // recommendations screen counts. A fixture where everything had an owner would never
    // show the screen what it looks like.
    owner: null,
    ticket_reference: null,
    rationale: 'The volume is gp2 and gp3 delivers the same baseline for less.',
    reversible: true,
    disturbs_running_work: false,
    is_no_regret: true,
    risk_why:
      'A volume type change is applied online and can be changed back. Nothing detaches ' +
      'and nothing restarts.',
  };
  return {
    data: {
      node: {
        node_id: nodeId || ROOT,
        provider_id: 'arn:aws:ec2:us-fake-1:fake-platform-a:vpc/vpc-platform',
        account_id: 'fake-platform-a',
        node_kind: 'VPC',
        resource_type: 'AWS::EC2::VPC',
        region_id: 'us-fake-1',
        availability_zone: null,
        name: 'platform',
        as_of: AS_OF,
        collected_at: COLLECTED_AT,
      },
      // PARTIAL, so the page has to say the neighbour list may be short.
      coverage: {
        account_id: 'fake-platform-a',
        region_id: 'us-fake-1',
        state: 'PARTIAL',
        cause: 'Throttled',
        node_count: 27,
        edge_count: 40,
        as_of: AS_OF,
        collected_at: COLLECTED_AT,
      },
      neighbours: [
        {
          node_id: SUBNET,
          provider_id: 'arn:aws:ec2:us-fake-1:fake-platform-a:subnet/subnet-a',
          account_id: 'fake-platform-a',
          node_kind: 'SUBNET',
          resource_type: 'AWS::EC2::Subnet',
          region_id: 'us-fake-1',
          availability_zone: 'us-fake-1-a',
          name: 'private-a',
          as_of: AS_OF,
          collected_at: COLLECTED_AT,
        },
      ],
      edges: [
        {
          from_node_id: nodeId || ROOT,
          to_node_id: SUBNET,
          edge_kind: 'CONTAINS',
          is_cross_account: false,
          source: 'CONFIG_RELATIONSHIP',
          leaves_the_graph: false,
        },
        {
          from_node_id: nodeId || ROOT,
          to_node_id: FAR,
          edge_kind: 'PEERS_WITH',
          is_cross_account: true,
          source: 'ec2:DescribeVpcPeeringConnections',
          leaves_the_graph: true,
        },
      ],
      findings: [finding],
      // Two findings in this account joined to nothing, so the single finding above is not
      // the whole story and the screen is not allowed to imply that it is.
      unmatched_findings: 2,
      monthly_cost: '214.8800',
      cost_period: '2026-08-01',
      // Managed, with the address, because that is the case the page has something to show
      // for. The not determined case is exercised by the screen test, which is where a fixture
      // would otherwise have to choose one of three and leave two unrendered locally.
      management_state: 'MANAGED',
      iac_address: 'module.network.aws_vpc.main',
      iac_state_reference: 's3://fake-state/network.tfstate',
    },
    meta: metaWith(0, 1),
  };
}

/**
 * A page of resources, offline. FEAT-056.
 *
 * Deliberately a partial page of a larger estate, and drawn from fewer slices than exist. A
 * fixture whose page held everything and whose coverage was complete would let the two things
 * this screen has to say honestly go unexercised by anything a developer opens locally: that
 * the list is a page, and that it was drawn from an estate part of which was never read.
 */
export function resourceListFixture(): ApiEnvelope<ApiResourceList> {
  return {
    data: {
      resources: [
        {
          node_id: ROOT,
          provider_id: 'arn:aws:ec2:us-fake-1:fake-platform-a:vpc/vpc-platform',
          account_id: 'fake-platform-a',
          node_kind: 'VPC',
          resource_type: 'AWS::EC2::VPC',
          region_id: 'us-fake-1',
          availability_zone: null,
          name: 'platform',
          as_of: AS_OF,
          collected_at: COLLECTED_AT,
        },
        {
          node_id: SUBNET,
          provider_id: 'arn:aws:ec2:us-fake-1:fake-platform-a:subnet/subnet-a',
          account_id: 'fake-platform-a',
          node_kind: 'SUBNET',
          resource_type: 'AWS::EC2::Subnet',
          region_id: 'us-fake-1',
          availability_zone: 'us-fake-1-a',
          name: 'private-a',
          as_of: AS_OF,
          collected_at: COLLECTED_AT,
        },
        {
          // A global resource. Null region means global, never a region nobody could read,
          // and the screen has to render it as such rather than as an empty cell.
          node_id: FAR,
          provider_id: 'arn:aws:iam::fake-platform-a:role/deploy',
          account_id: 'fake-platform-a',
          node_kind: 'IAM_ROLE',
          resource_type: 'AWS::IAM::Role',
          region_id: null,
          availability_zone: null,
          name: 'deploy',
          as_of: AS_OF,
          collected_at: COLLECTED_AT,
        },
      ],
      // Three of twenty seven, so the screen has to say it is showing a page.
      total: 27,
      limit: 3,
      offset: 0,
      filters: {
        account_id: ['fake-platform-a', 'fake-product-denied'],
        region_id: ['us-fake-1', 'eu-fake-1'],
        node_kind: ['IAM_ROLE', 'SUBNET', 'VPC'],
        resource_type: ['AWS::EC2::Subnet', 'AWS::EC2::VPC', 'AWS::IAM::Role'],
      },
    },
    meta: metaWith(18, 20),
  };
}

/**
 * A blast radius, offline. FEAT-044.
 *
 * Refused, deliberately. The refusal is the half of this feature that is easy to leave
 * unexercised: a fixture carrying a band would render the panel a developer wants to look at and
 * would never render the sentence the whole task exists for. The screen test carries the scored
 * case, where it can assert the band and the lower bound together.
 */
export function blastRadiusFixture(): ApiEnvelope<ApiBlastRadius> {
  return {
    data: {
      band: null,
      parts: [],
      reach: null,
      accounts: null,
      boundary_edges: null,
      depth_bound_reached: false,
      is_lower_bound: true,
      refused_because: ['fake-product-denied in us-fake-1 is PARTIAL because of AccessDenied'],
      max_depth: 4,
    },
    meta: metaWith(18, 20),
  };
}

/**
 * The estate by continent, with all three leftovers present. FEAT-061.
 *
 * Built to exercise the parts of the screen that a tidy estate never reaches. Two geographies
 * with different region counts, a region whose prefix no table knows, resources belonging to no
 * region at all, and a region a collection refused. A fixture where everything places is a
 * fixture that only ever draws the easy half of this screen.
 */
export function geographyFixture(): ApiEnvelope<ApiGeographies> {
  return {
    data: {
      geographies: [
        {
          key: 'us',
          name: 'United States',
          // Two regions, one of them with a compass word and one without, so the drawing has
          // to handle both: a placed offset and a fall back to the continent's own anchor.
          regions: [
            { region_id: 'us-east-1', resources: 29, direction: 'east' },
            { region_id: 'us-fake-1', resources: 12, direction: null },
          ],
          resources: 41,
          // Four, and deliberately fewer than the sum of any per region count would give.
          accounts: 4,
        },
        {
          key: 'eu',
          name: 'Europe',
          regions: [{ region_id: 'eu-fake-1', resources: 12, direction: null }],
          resources: 12,
          accounts: 2,
        },
      ],
      global_resources: 6,
      unplaceable: ['fake-region-c'],
      unplaceable_resources: 2,
      refused: ['fake-region-c'],
      links: [
        {
          one_region: 'eu-fake-1',
          other_region: 'us-east-1',
          one_geography: 'eu',
          other_geography: 'us',
          links: 3,
          kinds: ['PEERS_WITH'],
        },
        {
          // Inside one geography, so the table says it and the drawing cannot.
          one_region: 'us-east-1',
          other_region: 'us-fake-1',
          one_geography: 'us',
          other_geography: 'us',
          links: 1,
          kinds: ['ROUTES_TO'],
        },
      ],
    },
    meta: {
      as_of: '2026-09-26T06:00:00Z',
      collected_at: '2026-09-26T06:05:00Z',
      scope_coverage: { visible: 4, total: 5, is_partial: true, unit: 'slices' },
      degraded: false,
      failures: [],
    },
  };
}
