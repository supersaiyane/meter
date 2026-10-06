import { useClusters } from '../api/queries';
import { DataTable } from '../components/DataTable';
import { FixtureBand } from '../components/FixtureBand';
import { PercentCell } from '../components/PercentCell';
import { StateBoundary } from '../components/StateBoundary';
import type { Column } from '../components/tableConfig';
import type { ApiClusterInventory } from '../api/types';
import { useReportMeta } from '../shell/metaRegistry';
import { surfaceStateFor } from './surfaceStateFor';

/**
 * What clusters there are, their node fleets, Spot ratio and bin packing. Under Inventory.
 *
 * **Every cluster is listed, and every missing figure says why.** A cluster whose requests
 * are unreadable cannot have its bin packing computed, because packing is requests over
 * allocatable and the numerator is the missing thing. A Fargate cluster has no fleet at all.
 * Those are different sentences, and showing both as an empty bar would say neither.
 *
 * **Both figures are better high, so neither ramp is inverted.** More on Spot is cheaper and
 * tighter packing is less paid for and idle, unlike a quota, where a high figure is the
 * finding.
 */

function noSpot(cluster: ApiClusterInventory): string {
  return cluster.platform === 'ECS'
    ? 'No nodes, so nothing runs on Spot.'
    : 'The node fleet could not be read.';
}

function fraction(value: string | null): number | null {
  return value === null ? null : Number(value);
}

/** A cluster's nodes for the total: none for ECS without nodes, unknown for an unread fleet. */
function nodesOf(cluster: ApiClusterInventory): number | null {
  return cluster.node_count ?? (cluster.platform === 'ECS' ? 0 : null);
}

const COLUMNS: readonly Column<ApiClusterInventory>[] = [
  {
    key: 'cluster',
    header: 'Cluster',
    render: (cluster) => <strong>{cluster.cluster_name}</strong>,
    sortValue: (cluster) => cluster.cluster_name,
  },
  {
    key: 'platform',
    header: 'Platform',
    render: (cluster) => cluster.platform,
    sortValue: (cluster) => cluster.platform,
  },
  {
    key: 'account',
    header: 'Account',
    render: (cluster) => cluster.account_id,
    sortValue: (cluster) => cluster.account_id,
  },
  {
    key: 'region',
    header: 'Region',
    render: (cluster) => cluster.region_id,
    sortValue: (cluster) => cluster.region_id,
  },
  {
    key: 'nodes',
    header: 'Nodes',
    numeric: true,
    cellTestId: 'cluster-nodes',
    render: (cluster) => (cluster.node_count === null ? 'no nodes' : cluster.node_count),
    sortValue: (cluster) => cluster.node_count,
    // Counted, so it adds up: an ECS cluster with no nodes adds nothing, and a fleet nobody
    // could read stops the total rather than being counted as empty.
    total: {
      value: nodesOf,
      unit: () => 'nodes',
      provenance: () => 'measured',
      render: (sum) => `${String(sum)} nodes`,
    },
  },
  {
    key: 'spot',
    header: 'On Spot',
    cellTestId: 'cluster-spot',
    render: (cluster) => (
      <PercentCell
        fraction={fraction(cluster.spot_ratio)}
        absent={noSpot(cluster)}
        provenance="measured"
      />
    ),
    sortValue: (cluster) => fraction(cluster.spot_ratio),
  },
  {
    key: 'packing',
    header: 'Cluster efficiency',
    cellTestId: 'cluster-packing',
    render: (cluster) => (
      <PercentCell
        fraction={fraction(cluster.packing_efficiency)}
        absent={cluster.unmeasurable_reason ?? 'Cluster efficiency could not be computed.'}
        provenance="measured"
      />
    ),
    sortValue: (cluster) => fraction(cluster.packing_efficiency),
  },
];

export function ClustersScreen() {
  const query = useClusters();
  const envelope = query.data?.data;
  useReportMeta('inventory-clusters', envelope?.meta);

  const found = envelope?.data;
  const clusters = found?.clusters ?? [];
  const state = surfaceStateFor(
    query,
    envelope?.meta,
    clusters.length,
    'none',
    'container_usage',
  );

  return (
    <section aria-label="Clusters">
      <FixtureBand source={query.data?.source} />
      <StateBoundary state={state}>
        <>
          <p data-testid="clusters-ratio">
            {found?.measured_count ?? 0} of {found?.found_count ?? 0} clusters with nodes have a
            measured bin packing. Fargate clusters are listed and not counted, because they run
            without nodes and have no fleet to pack.
          </p>
          <div data-testid="clusters">
            <DataTable
              rows={clusters}
              columns={COLUMNS}
              rowKey={(cluster) => `${cluster.account_id}:${cluster.cluster_name}`}
              caption="Every cluster, its fleet, how much of it runs on Spot, and how well it is packed"
              rowAttributes={(cluster) => ({
                'data-testid': 'cluster-row',
                'data-platform': cluster.platform,
              })}
            />
          </div>
        </>
      </StateBoundary>
    </section>
  );
}
