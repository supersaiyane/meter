import { useContainerCost } from '../api/queries';
import { Figure } from '../components';
import { FixtureBand } from '../components/FixtureBand';
import { StateBoundary } from '../components/StateBoundary';
import type { ApiClusterCost } from '../api/types';
import { useReportMeta } from '../shell/metaRegistry';
import { surfaceStateFor } from './surfaceStateFor';

/**
 * What each cluster costs, by namespace and workload. FEAT-035, under Cost per ADR-0020.
 *
 * **Measured, not apportioned.** Every figure is a split cost allocation column on the bill
 * already being read, so a pod's cost carries the same timestamps as any other charge and is
 * scoped by the same guard. Nothing here divides a cluster's cost itself.
 *
 * **The sum is shown, not asserted.** Each cluster states its workloads' share and the
 * capacity no pod requested, and the two make its total in plain sight. A breakdown that did
 * not reconcile would be a breakdown that invented or lost money, and a reader can only trust
 * that it does not if they can check it.
 *
 * **The remainder is a figure, not a rounding error.** Capacity a cluster paid for and no pod
 * asked for is real money, and the reason bin packing is worth its own screen.
 */

function Workloads({
  cluster,
  freshness,
}: {
  readonly cluster: ApiClusterCost;
  readonly freshness: { readonly asOf: Date; readonly collectedAt: Date };
}) {
  return (
    <table data-testid="container-cost-workloads">
      <caption>Each workload's measured share, the largest first</caption>
      <thead>
        <tr>
          <th scope="col">Namespace</th>
          <th scope="col">Workload</th>
          <th scope="col">Kind</th>
          <th scope="col">Cost</th>
        </tr>
      </thead>
      <tbody>
        {cluster.workloads.map((row) => (
          <tr key={`${row.namespace}/${row.workload_name}`} data-testid="container-cost-row">
            <td>{row.namespace}</td>
            <td>
              <strong>{row.workload_name}</strong>
            </td>
            <td>{row.workload_type === '' ? 'not reported' : row.workload_type}</td>
            <td data-testid="container-cost-figure">
              <Figure
                value={{ kind: 'measured', amount: Number(row.cost) }}
                freshness={freshness}
              />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Cluster({
  cluster,
  freshness,
}: {
  readonly cluster: ApiClusterCost;
  readonly freshness: { readonly asOf: Date; readonly collectedAt: Date };
}) {
  return (
    <section
      aria-label={`Cluster ${cluster.cluster_name}`}
      data-testid="container-cost-cluster"
      data-breakdown={String(cluster.breakdown_available)}
    >
      <h3 data-testid="container-cost-cluster-name">{cluster.cluster_name}</h3>
      <p data-testid="cost-reconciliation">
        Workloads{' '}
        <span data-testid="cost-allocated">
          <Figure
            value={{ kind: 'measured', amount: Number(cluster.allocated) }}
            freshness={freshness}
          />
        </span>{' '}
        and capacity no pod requested{' '}
        <span data-testid="cost-unallocated">
          <Figure
            value={{ kind: 'measured', amount: Number(cluster.unallocated) }}
            freshness={freshness}
          />
        </span>{' '}
        make the cluster's{' '}
        <span data-testid="cost-total">
          <Figure
            value={{ kind: 'measured', amount: Number(cluster.total) }}
            freshness={freshness}
          />
        </span>
        .
      </p>
      {cluster.breakdown_available ? (
        <Workloads cluster={cluster} freshness={freshness} />
      ) : (
        <p data-testid="container-cost-reason">{cluster.unmeasurable_reason}</p>
      )}
    </section>
  );
}

export function ContainerCostScreen() {
  const query = useContainerCost();
  const envelope = query.data?.data;
  useReportMeta('cost-containers', envelope?.meta);

  const found = envelope?.data;
  const clusters = found?.clusters ?? [];
  const freshness = {
    asOf: new Date(envelope?.meta.as_of ?? 0),
    collectedAt: new Date(envelope?.meta.collected_at ?? 0),
  };
  const state = surfaceStateFor(query, envelope?.meta, clusters.length, 'none', 'cost_focus');

  return (
    <section aria-label="Container cost">
      <FixtureBand source={query.data?.source} />
      <StateBoundary state={state}>
        <>
          <p data-testid="container-cost-ratio">
            {found?.measured_count ?? 0} of {found?.found_count ?? 0} clusters can be broken
            down by workload. Every figure is measured from the bill, none is divided out here.
          </p>
          {clusters.map((cluster) => (
            <Cluster key={cluster.cluster_name} cluster={cluster} freshness={freshness} />
          ))}
        </>
      </StateBoundary>
    </section>
  );
}
