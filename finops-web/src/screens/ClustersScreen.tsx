import { useClusters } from '../api/queries';
import { FixtureBand } from '../components/FixtureBand';
import { PercentCell } from '../components/PercentCell';
import { StateBoundary } from '../components/StateBoundary';
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

function Row({ cluster }: { readonly cluster: ApiClusterInventory }) {
  return (
    <tr data-testid="cluster-row" data-platform={cluster.platform}>
      <td>
        <strong>{cluster.cluster_name}</strong>
      </td>
      <td>{cluster.platform}</td>
      <td>{cluster.account_id}</td>
      <td>{cluster.region_id}</td>
      <td data-testid="cluster-nodes">
        {cluster.node_count === null ? 'no nodes' : cluster.node_count}
      </td>
      <td data-testid="cluster-spot">
        <PercentCell
          fraction={fraction(cluster.spot_ratio)}
          absent={noSpot(cluster)}
          provenance="measured"
        />
      </td>
      <td data-testid="cluster-packing">
        <PercentCell
          fraction={fraction(cluster.packing_efficiency)}
          absent={cluster.unmeasurable_reason ?? 'Bin packing could not be computed.'}
          provenance="measured"
        />
      </td>
    </tr>
  );
}

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
          <table data-testid="clusters">
            <caption>
              Every cluster, its fleet, how much of it runs on Spot, and how well it is packed
            </caption>
            <thead>
              <tr>
                <th scope="col">Cluster</th>
                <th scope="col">Platform</th>
                <th scope="col">Account</th>
                <th scope="col">Region</th>
                <th scope="col">Nodes</th>
                <th scope="col">On Spot</th>
                <th scope="col">Bin packing</th>
              </tr>
            </thead>
            <tbody>
              {clusters.map((cluster) => (
                <Row key={`${cluster.account_id}:${cluster.cluster_name}`} cluster={cluster} />
              ))}
            </tbody>
          </table>
        </>
      </StateBoundary>
    </section>
  );
}
