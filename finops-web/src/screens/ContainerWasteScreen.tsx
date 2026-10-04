import { useContainerCost, useContainerWaste } from '../api/queries';
import { Figure } from '../components';
import { FixtureBand } from '../components/FixtureBand';
import { StateBoundary } from '../components/StateBoundary';
import type { ApiClusterCost, ApiClusterUsage, ApiContainerUsageRow } from '../api/types';
import { useReportMeta } from '../shell/metaRegistry';
import { surfaceStateFor } from './surfaceStateFor';

/**
 * What each workload asked for, against what it used. FEAT-036, under Waste.
 *
 * **Two figures, never one percentage.** A namespace at twenty percent could be over
 * requesting by a factor of five or could be idle, and those are different conversations with
 * different people. So request and use sit in separate columns and nothing on this screen
 * divides one by the other. P6 spec section 9.
 *
 * **The cluster nobody can measure is listed, not dropped.** A cluster without enhanced
 * observability publishes use and no request, so requested against used cannot be stated for
 * it. It still appears, with its cost and its reason, and its rows carry no request columns at
 * all rather than empty ones: an empty cell in a column of numbers reads as a measurement that
 * came back zero, which is the one thing this must not say.
 *
 * **An unobserved kill is a third word, not a blank.** Container Insights does not reliably
 * report OOM events, so most rows say the status could not be observed, and that is shown as
 * such rather than as "no", which would claim somebody checked.
 *
 * The recommendations themselves are P3's and live on the main waste list, filtered to the
 * container class. This screen is the evidence they were drawn from.
 */

const OOM_WORDS: Readonly<Record<ApiContainerUsageRow['oom_status'], string>> = {
  KILLED: 'killed for running out of memory',
  NOT_KILLED: 'not killed',
  UNOBSERVED: 'could not be observed',
};

function Requested({ row }: { readonly row: ApiContainerUsageRow }) {
  return (
    <tr data-testid="container-row">
      <td>{row.namespace}</td>
      <td>
        <strong>{row.workload}</strong>
        <span data-testid="container-launch"> {row.launch_type.toLowerCase()}</span>
      </td>
      <td data-testid="cpu-requested">{row.cpu_requested_millicores} m</td>
      <td data-testid="cpu-used">{row.cpu_used_p99_millicores ?? 'not observed'} m</td>
      <td data-testid="memory-requested">{row.memory_requested_mib} MiB</td>
      <td data-testid="memory-used">{row.memory_used_peak_mib ?? 'not observed'} MiB</td>
      <td data-testid="container-oom" data-oom={row.oom_status}>
        {OOM_WORDS[row.oom_status]}
      </td>
    </tr>
  );
}

function UseOnly({ row }: { readonly row: ApiContainerUsageRow }) {
  return (
    <tr data-testid="container-row-unrequested">
      <td>{row.namespace}</td>
      <td>
        <strong>{row.workload}</strong>
      </td>
      {/* No request cell at all. See the screen comment. */}
      <td data-testid="cpu-used">{row.cpu_used_p99_millicores ?? 'not observed'} m</td>
      <td data-testid="memory-used">{row.memory_used_peak_mib ?? 'not observed'} MiB</td>
      <td data-testid="container-oom" data-oom={row.oom_status}>
        {OOM_WORDS[row.oom_status]}
      </td>
    </tr>
  );
}

function Cluster({
  cluster,
  cost,
  freshness,
}: {
  readonly cluster: ApiClusterUsage;
  readonly cost: ApiClusterCost | undefined;
  readonly freshness: { readonly asOf: Date; readonly collectedAt: Date };
}) {
  return (
    <section
      aria-label={`Cluster ${cluster.cluster_name}`}
      data-testid="container-cluster"
      data-measurable={String(cluster.enhanced_observability)}
    >
      <h3 data-testid="container-cluster-name">
        {cluster.cluster_name}
        <span>
          {' '}
          {cluster.platform} in {cluster.account_id}, {cluster.region_id}
        </span>
      </h3>
      <p data-testid="container-cluster-cost">
        {cost === undefined ? (
          'No cost is attributed to this cluster, so its share of the bill cannot be shown.'
        ) : (
          <>
            Costs{' '}
            <Figure
              value={{ kind: 'measured', amount: Number(cost.total) }}
              freshness={freshness}
            />{' '}
            this month, measured from the bill.
          </>
        )}
      </p>
      {cluster.enhanced_observability ? (
        <table data-testid="container-requests">
          <caption>Each workload's request beside its use. Two figures, never one ratio.</caption>
          <thead>
            <tr>
              <th scope="col">Namespace</th>
              <th scope="col">Workload</th>
              <th scope="col">CPU requested</th>
              <th scope="col">CPU used, 99th percentile</th>
              <th scope="col">Memory requested</th>
              <th scope="col">Memory used, peak</th>
              <th scope="col">Out of memory</th>
            </tr>
          </thead>
          <tbody>
            {cluster.workloads.map((row) => (
              <Requested key={`${row.namespace}/${row.workload}`} row={row} />
            ))}
          </tbody>
        </table>
      ) : (
        <>
          <p data-testid="container-reason">{cluster.request_unavailable_reason}</p>
          <table data-testid="container-use-only">
            <caption>
              What each workload used. There is no request to set it against, so nothing here
              says how much of a reservation is idle.
            </caption>
            <thead>
              <tr>
                <th scope="col">Namespace</th>
                <th scope="col">Workload</th>
                <th scope="col">CPU used, 99th percentile</th>
                <th scope="col">Memory used, peak</th>
                <th scope="col">Out of memory</th>
              </tr>
            </thead>
            <tbody>
              {cluster.workloads.map((row) => (
                <UseOnly key={`${row.namespace}/${row.workload}`} row={row} />
              ))}
            </tbody>
          </table>
        </>
      )}
    </section>
  );
}

export function ContainerWasteScreen() {
  const query = useContainerWaste();
  const envelope = query.data?.data;
  useReportMeta('waste-containers', envelope?.meta);

  // A second read for the cost, because a cluster can have a cost and no readable requests,
  // and folding one into the other would invite a join that drops exactly that cluster.
  const costQuery = useContainerCost();
  const costEnvelope = costQuery.data?.data;
  const costs = new Map(
    (costEnvelope?.data.clusters ?? []).map((cluster) => [cluster.cluster_name, cluster]),
  );
  const freshness = {
    asOf: new Date(costEnvelope?.meta.as_of ?? 0),
    collectedAt: new Date(costEnvelope?.meta.collected_at ?? 0),
  };

  const found = envelope?.data;
  const clusters = found?.clusters ?? [];
  const measured = found?.measured_count ?? 0;
  const total = found?.found_count ?? 0;
  const state = surfaceStateFor(query, envelope?.meta, clusters.length, 'none', 'container_usage');

  return (
    <section aria-label="Container requests">
      <FixtureBand source={query.data?.source} />
      <StateBoundary state={state}>
        <>
          <p data-testid="containers-ratio">
            {measured} of {total} clusters publish pod requests. The others are listed with their
            use and their cost, and with the reason their requests cannot be read.
          </p>
          {clusters.map((cluster) => (
            <Cluster
              key={`${cluster.account_id}:${cluster.region_id}:${cluster.cluster_name}`}
              cluster={cluster}
              cost={costs.get(cluster.cluster_name)}
              freshness={freshness}
            />
          ))}
        </>
      </StateBoundary>
    </section>
  );
}
