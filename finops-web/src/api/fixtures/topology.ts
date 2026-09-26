import type {
  ApiEnvelope,
  ApiGraphCoverage,
  ApiInventoryRoots,
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
          provider_id: 'arn:aws:ec2:fake-region-a:fake-platform-a:vpc/vpc-platform',
          account_id: 'fake-platform-a',
          node_kind: 'VPC',
          resource_type: 'AWS::EC2::VPC',
          region_id: 'fake-region-a',
          name: 'platform',
        },
        {
          // OTHER, with its real type beside it. Ten of the estate's twenty four types
          // land here, so a screen showing only the kind is a field of blank boxes.
          node_id: '6cbf4d5e-7081-4293-9da4-2e5f60718293',
          provider_id: 'arn:aws:eks:fake-region-a:fake-platform-a:cluster/platform-eks',
          account_id: 'fake-platform-a',
          node_kind: 'OTHER',
          resource_type: 'AWS::EKS::Cluster',
          region_id: 'fake-region-a',
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
          region_id: 'fake-region-b',
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
          region_id: 'fake-region-a',
          state: 'COMPLETE',
          cause: null,
          node_count: 27,
          edge_count: 40,
          as_of: AS_OF,
          collected_at: COLLECTED_AT,
        },
        {
          account_id: 'fake-product-denied',
          region_id: 'fake-region-a',
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
