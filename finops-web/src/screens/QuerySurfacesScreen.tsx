import { useQuerySurfaces } from '../api/queries';
import type { ApiSurfaceInstance } from '../api/types';
import { DataTable } from '../components/DataTable';
import { Figure } from '../components/Figure';
import { FixtureBand } from '../components/FixtureBand';
import { StateBoundary } from '../components/StateBoundary';
import type { Cause, Freshness } from '../components/provenance';
import type { Column } from '../components/tableConfig';
import { useReportMeta } from '../shell/metaRegistry';
import { surfaceStateFor } from './surfaceStateFor';

/**
 * Every place queries live, per P2 spec section 9.3.
 *
 * This is the screen that stops silent under counting. An instance Meter could
 * not read is listed with its cause, never omitted, because a findings list
 * drawn from two of three workspaces looks complete and is not.
 *
 * Its query count is null, and null renders as the cause rather than as zero.
 * The distinction between "we could not read this" and "we read this and it
 * holds nothing" is the entire product, and both rows appear here so neither
 * can be mistaken for the other.
 */

const KNOWN_CAUSES = new Set<string>([
  'AccessDenied',
  'Throttled',
  'NotOptedIn',
  'Unreachable',
  'SchemaDrift',
]);

const KIND_LABEL: Readonly<Record<string, string>> = {
  AMG: 'Amazon Managed Grafana',
  SELF_HOSTED: 'Self hosted Grafana',
  CLOUD: 'Grafana Cloud',
};

/**
 * Where the instance is. An account and a region for a managed workspace, and
 * the endpoint for one that belongs to no cloud account, because "not stated"
 * in a location column tells the reader nothing they can act on.
 */
function locationOf(row: ApiSurfaceInstance): string {
  const placed = [row.account_id, row.region_id].filter(Boolean).join(' ');
  return placed || row.endpoint;
}

function countFigure(row: ApiSurfaceInstance, freshness: Freshness) {
  if (row.query_count === null) {
    const cause = row.unreachable_reason ?? 'SchemaDrift';
    return (
      <Figure
        value={{
          kind: 'failed',
          // A cause the frontend does not recognise is drift, which is loud,
          // rather than something softer that would read as ordinary.
          cause: (KNOWN_CAUSES.has(cause) ? cause : 'SchemaDrift') as Cause,
          remediation: `${row.name} could not be read. ${locationOf(row)}`,
        }}
        freshness={freshness}
      />
    );
  }
  return (
    <Figure
      value={{ kind: 'measured', amount: row.query_count }}
      freshness={freshness}
      unit="count"
    />
  );
}

function columnsFor(freshness: Freshness): readonly Column<ApiSurfaceInstance>[] {
  return [
    { key: 'name', header: 'Instance', render: (row) => row.name },
    { key: 'kind', header: 'Kind', render: (row) => KIND_LABEL[row.kind] ?? row.kind },
    { key: 'location', header: 'Location', render: (row) => locationOf(row) },
    {
      key: 'reachable',
      header: 'Reachable',
      render: (row) => (row.reachable ? 'yes' : 'no'),
    },
    {
      key: 'queries',
      header: 'Queries found',
      numeric: true,
      render: (row) => countFigure(row, freshness),
    },
  ];
}

export function QuerySurfacesScreen() {
  const query = useQuerySurfaces();
  const envelope = query.data?.data;
  const rows = envelope?.data ?? [];
  useReportMeta('query-instances', envelope?.meta);

  const freshness: Freshness = {
    asOf: new Date(envelope?.meta.as_of ?? 0),
    collectedAt: new Date(envelope?.meta.collected_at ?? 0),
  };
  const state = surfaceStateFor(query, envelope?.meta, rows.length, 'none', 'query_audit');

  return (
    <section aria-label="Query surfaces">
      <FixtureBand source={query.data?.source} />
      <StateBoundary state={state}>
        <DataTable
          rows={rows}
          columns={columnsFor(freshness)}
          rowKey={(row) => row.instance_id}
          caption="Where queries live, including the instances Meter could not read"
        />
      </StateBoundary>
    </section>
  );
}
