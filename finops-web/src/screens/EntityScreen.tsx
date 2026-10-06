import { useParams } from 'react-router';
import { lifecycleName, wasteClassName } from '../components/displayNames';

import { useBlastRadius, useEntity } from '../api/queries';
import { DataTable } from '../components/DataTable';
import { Figure } from '../components/Figure';
import { FixtureBand } from '../components/FixtureBand';
import { SeverityBadge } from '../components/SeverityBadge';
import { StateBoundary } from '../components/StateBoundary';
import type { Column } from '../components/tableConfig';
import { riskLabel } from '../components/actionRisk';
import type { Freshness } from '../components/provenance';
import type {
  ApiBlastPart,
  ApiEntity,
  ApiRecommendation,
  ApiTopologyEdge,
  ApiTopologyNode,
} from '../api/types';
import { Link } from '../shell/links';
import { useReportMeta } from '../shell/metaRegistry';
import { severityLevel } from './querySeverity';
import { saidOf } from './sliceCoverage';
import { surfaceStateFor } from './surfaceStateFor';

/**
 * One resource: what it is, what it is attached to, what it costs, what is wrong with it.
 *
 * FEAT-053, adopted from the 2026-09-26 IBM Turbonomic review. Their Supply Chain drills
 * into an entity detail view, and every list in this product pointed nowhere: a reader who
 * found an instance on the waste screen, the map or an anomaly had no page to open.
 *
 * **Two of the five sections are admissions.** The coverage banner is above everything,
 * for the same reason the topology map's is: a reader who sees the neighbour list first has
 * already concluded that the list is complete. And the unmatched finding count sits with the
 * findings, because an empty finding list otherwise reads as a clean resource when the truth
 * may be that nothing could be joined to it.
 *
 * **It owns no numbers of its own.** The cost comes from the same repository `/cost` reads
 * and the findings from the same serialiser `/waste` uses, including FEAT-052's risk verdict,
 * so a reader moving between the three sees one answer rather than three.
 */

/** Where a resource lives, said in one line. Null region means global, never unknown. */
function placeOf(node: ApiTopologyNode): string {
  if (node.availability_zone !== null) return node.availability_zone;
  return node.region_id ?? 'global, not tied to a region';
}

/**
 * The relationship that connects this resource to one neighbour, with its direction.
 *
 * Direction is kept because it is most of the meaning. A subnet contained by a VPC and a VPC
 * contained by a subnet are not the same estate, and an undirected list of kinds would render
 * both identically.
 */
function relationOf(
  edges: readonly ApiTopologyEdge[],
  self: string,
  neighbour: string,
): string {
  const outward = edges.find(
    (edge) => edge.from_node_id === self && edge.to_node_id === neighbour,
  );
  if (outward !== undefined) return outward.edge_kind;
  const inward = edges.find(
    (edge) => edge.from_node_id === neighbour && edge.to_node_id === self,
  );
  if (inward !== undefined) return `${inward.edge_kind} (inward)`;
  // Reachable only if the repository returned a neighbour with no edge to it, which would be
  // a bug in the walk rather than a state of the estate. Said rather than rendered blank.
  return 'no recorded relationship';
}

/**
 * The findings that name this resource, TASK-P8-013 on `DataTable`. No total: two findings on
 * one resource are often alternatives, resize it or remove it, and adding their savings would
 * count one saving twice.
 */
function findingColumns(freshness: Freshness): readonly Column<ApiRecommendation>[] {
  return [
    {
      key: 'finding',
      header: 'Finding',
      rowHeader: true,
      render: (row) => <Link to="/optimize">{wasteClassName(row.waste_class)}</Link>,
      sortValue: (row) => wasteClassName(row.waste_class),
    },
    {
      key: 'saving',
      header: 'Estimated monthly savings',
      numeric: true,
      // Modelled, never measured, unlike the cost above. Figure carries the label so the two
      // cannot be confused on one page.
      render: (row) => (
        <Figure
          value={{ kind: 'modelled', amount: Number(row.estimated_monthly_saving) }}
          freshness={freshness}
          unit="usd"
        />
      ),
      sortValue: (row) => Number(row.estimated_monthly_saving),
    },
    {
      key: 'severity',
      header: 'Severity',
      render: (row) => <SeverityBadge level={severityLevel(row.severity)} />,
      sortValue: (row) => severityLevel(row.severity),
    },
    {
      key: 'state',
      header: 'State',
      render: (row) => lifecycleName(row.lifecycle),
      sortValue: (row) => lifecycleName(row.lifecycle),
    },
    {
      key: 'risk',
      header: 'If it is wrong',
      prose: true,
      // The same two words and the same sentence the home panel shows, from the same module,
      // so a reader cannot be told a change is reversible on one screen and permanent on
      // another.
      render: (row) => (
        <>
          <strong>{riskLabel(row)}</strong>
          <span> {row.risk_why}</span>
        </>
      ),
    },
  ];
}

/** What a change can reach, by kind. Counts of different things, so they do not add up. */
const PART_COLUMNS: readonly Column<ApiBlastPart>[] = [
  {
    key: 'name',
    header: 'Counted',
    rowHeader: true,
    render: (part) => part.name,
    sortValue: (part) => part.name,
  },
  {
    key: 'count',
    header: 'How many',
    numeric: true,
    render: (part) => part.count,
    sortValue: (part) => part.count,
  },
  // Prose, so it wraps. Without it the cell inherits the nowrap every data cell needs and the
  // table grows past its container: measured at 1456px inside 955px before this was here.
  { key: 'why', header: 'What it means', prose: true, render: (part) => part.why },
];

function neighbourColumns(entity: ApiEntity): readonly Column<ApiTopologyNode>[] {
  return [
    {
      key: 'resource',
      header: 'Resource',
      rowHeader: true,
      render: (one) => (
        <Link to={`/inventory/resources/${one.node_id}`}>{one.name ?? one.provider_id}</Link>
      ),
      sortValue: (one) => one.name ?? one.provider_id,
    },
    {
      key: 'kind',
      header: 'Kind',
      render: (one) => one.node_kind,
      sortValue: (one) => one.node_kind,
    },
    {
      key: 'relationship',
      header: 'Relationship',
      render: (one) => relationOf(entity.edges, entity.node.node_id, one.node_id),
      sortValue: (one) => relationOf(entity.edges, entity.node.node_id, one.node_id),
    },
    {
      key: 'account',
      header: 'Account',
      render: (one) => one.account_id,
      sortValue: (one) => one.account_id,
    },
  ];
}

export function EntityScreen() {
  const { nodeId = '' } = useParams();
  const query = useEntity(nodeId === '' ? null : nodeId);
  const blast = useBlastRadius(nodeId === '' ? null : nodeId);
  const envelope = query.data?.data;
  const entity: ApiEntity | null = envelope?.data ?? null;
  useReportMeta('inventory-entity', envelope?.meta);
  const radius = blast.data?.data.data ?? null;

  const settled = !query.isPending && !query.isError && envelope !== undefined;
  if (settled && entity === null) {
    // A resource that does not exist is not an empty page and not a failure. The API answers
    // 404 for one outside scope as well, deliberately, so this wording cannot claim the
    // resource is absent from the estate, only that this reader has no resource by that id.
    return (
      <section aria-label="Resource">
        <FixtureBand source={query.data.source} />
        <p data-testid="entity-not-found">
          No resource with id {nodeId} in your scope. It may not exist, or it may be in an
          account you were not granted.
        </p>
      </section>
    );
  }

  const freshness: Freshness = {
    asOf: new Date(envelope?.meta.as_of ?? 0),
    collectedAt: new Date(envelope?.meta.collected_at ?? 0),
  };
  const state = surfaceStateFor(query, envelope?.meta, entity ? 1 : 0, 'none', 'inventory');
  const partial = entity?.coverage ?? null;
  const boundary = (entity?.edges ?? []).filter((edge) => edge.leaves_the_graph);

  return (
    <section aria-label="Resource">
      <FixtureBand source={query.data?.source} />

      {/* Above everything, never in a footnote. This resource came out of a slice, and if
          that slice was not read whole then the neighbour list below is short for a reason
          that has nothing to do with the resource. */}
      {partial !== null && partial.state !== 'COMPLETE' ? (
        <div role="status" data-testid="entity-coverage" className="meter-stale">
          <p>
            The slice this resource came from was not read whole, so it may be attached to
            things that are not listed below. {saidOf(partial)}.
          </p>
        </div>
      ) : null}
      {settled && entity !== null && entity.coverage === null ? (
        // Should be impossible: the collector writes a coverage row for every enrolled slice
        // on every run. Reported rather than treated as complete, because treating a missing
        // row as a healthy one is the exact failure the coverage table exists to prevent.
        <div role="status" data-testid="entity-coverage-missing" className="meter-stale">
          <p>
            No coverage was recorded for this resource&apos;s slice, so nothing here can say
            whether the estate around it was read.
          </p>
        </div>
      ) : null}

      <StateBoundary state={state}>
        {entity ? (
          <article>
            <h2>{entity.node.name ?? entity.node.provider_id}</h2>
            <p>
              {entity.node.node_kind}, {entity.node.resource_type}
            </p>

            <h3>Where it is</h3>
            <dl data-testid="entity-identity">
              <dt>Account</dt>
              <dd>{entity.node.account_id}</dd>
              <dt>Location</dt>
              <dd>{placeOf(entity.node)}</dd>
              <dt>Identifier</dt>
              {/* The ARN, whole. A reader has to be able to find the thing in their own
                  console, and a truncated identifier is not an identifier. */}
              <dd data-testid="entity-arn">{entity.node.provider_id}</dd>
            </dl>

            <h3>What manages it</h3>
            {/* FEAT-057. Three answers, rendered as three different things, because the
                difference between them is what somebody would act on. Not determined is the
                default and is not a synonym for unmanaged: telling somebody to import a
                resource already inside a module produces a duplicate or a state conflict. */}
            {entity.management_state === 'MANAGED' ? (
              <p data-testid="entity-managed">
                <code>{entity.iac_address}</code>
                <span>
                  {' '}
                  in {entity.iac_state_reference ?? 'a state location that was not recorded'}
                </span>
              </p>
            ) : entity.management_state === 'UNMANAGED' ? (
              <p data-testid="entity-unmanaged">
                No infrastructure as code manages this resource. Your configuration declares
                this account fully described by the state Meter reads, and every location was
                read, so this is a claim rather than an absence of one.
              </p>
            ) : (
              // The default, and the honest one. It says what is missing and what would make
              // the answer possible, because "not determined" alone reads as a defect.
              <p data-testid="entity-not-determined" data-state="never-collected">
                Not determined. This resource is not in any state Meter read, which is not the
                same as nothing managing it: Meter only reads the state locations it is
                configured with, and says unmanaged only for accounts an operator has declared
                fully described by them.
              </p>
            )}

            <h3>What it cost</h3>
            {entity.monthly_cost === null ? (
              // Null is not zero, and the difference is the whole reason this branch exists.
              // A resource created after the period closed and one whose charges land under a
              // parent both land here, and a zero would tell a reader it is free.
              <p data-testid="entity-cost-absent" data-state="never-collected">
                The bill does not mention this resource
                {entity.cost_period === null
                  ? ', and no billing period has been collected yet'
                  : ` in ${entity.cost_period}`}
                . That is not the same as costing nothing: charges for it may be recorded
                against a parent resource, or it may be newer than the period.
              </p>
            ) : (
              <p data-testid="entity-cost">
                <Figure
                  value={{ kind: 'measured', amount: Number(entity.monthly_cost) }}
                  freshness={freshness}
                  unit="usd"
                  label={`Effective cost in ${entity.cost_period ?? 'the latest period'}`}
                />
              </p>
            )}

            <h3>What is wrong with it</h3>
            {entity.findings.length === 0 ? (
              <p data-testid="entity-findings-empty">No finding names this resource.</p>
            ) : (
              <div data-testid="entity-findings">
                <DataTable
                  rows={entity.findings}
                  columns={findingColumns(freshness)}
                  rowKey={(row) => row.recommendation_id}
                  caption={
                    entity.findings.length === 1
                      ? 'One finding names this resource, open or already decided.'
                      : `${String(entity.findings.length)} findings name this resource, open ` +
                        'or already decided.'
                  }
                  initialSort={{ key: 'saving', direction: 'descending' }}
                />
              </div>
            )}
            {entity.unmatched_findings > 0 ? (
              // The honest half. A finding joins to a resource on the provider's identifier,
              // and the first party sources report identifiers that do not always match what
              // Config recorded, so the list above can be short for a reason that is nothing
              // to do with this resource.
              <p data-testid="entity-unmatched" className="meter-stale">
                {entity.unmatched_findings === 1
                  ? 'One finding in this account could not be matched to any resource, so ' +
                    'the list above may be missing one that belongs here.'
                  : `${String(entity.unmatched_findings)} findings in this account could ` +
                    'not be matched to any resource, so the list above may be missing some ' +
                    'that belong here.'}
              </p>
            ) : null}

            {/* FEAT-044. The gate, not the thing it gates: nothing here applies anything,
                constraint 6. Its own request, because this walks four hops and the neighbour
                list above walks one. */}
            <h3>What a change here can reach</h3>
            {radius === null ? (
              <p data-testid="blast-loading">Working out what this is connected to.</p>
            ) : !radius.band ? (
              // Truthiness rather than a null check, so a body arriving without a band
              // renders the refusal instead of reaching `parts.map` on nothing. A stubbed
              // route in the journey did exactly that and crashed the page.
              // A refusal is an answer, so it is rendered as one rather than as an error. The
              // slices are named because "the graph is incomplete" sends nobody anywhere, and
              // the reason we refuse at all is that a low score over a graph missing a region
              // reads as "this change is safe".
              <div data-testid="blast-refused" className="meter-stale">
                <p>
                  No score. Part of the graph this answer would rest on was not read, and a
                  radius computed from it would look more contained than it is.
                </p>
                <ul>
                  {radius.refused_because.map((one) => (
                    <li key={one}>{one}</li>
                  ))}
                </ul>
              </div>
            ) : (
              <div data-testid="blast-radius">
                <p>
                  <strong data-testid="blast-band">{radius.band}</strong>
                </p>
                {/* Not optional, and not a footnote. An infrastructure graph cannot see that
                    one service reads another's queue, or that a report somebody runs every
                    Monday is built on this table, so every figure below is a floor. */}
                <DataTable
                  rows={radius.parts}
                  columns={PART_COLUMNS}
                  rowKey={(part) => part.name}
                  caption={
                    'At least this wide. An infrastructure graph holds what a resource is ' +
                    'attached to and not what reads it, so application level dependencies are ' +
                    'invisible here and the real radius can only be larger.' +
                    (radius.depth_bound_reached
                      ? ` The walk also stopped at its ${String(radius.max_depth)} hop bound, ` +
                        'so anything beyond that was never looked at.'
                      : '')
                  }
                />
              </div>
            )}

            <h3>What it is attached to</h3>
            {entity.neighbours.length === 0 ? (
              <p data-testid="entity-neighbours-empty">
                Nothing is recorded as attached to this resource.
              </p>
            ) : (
              <div data-testid="entity-neighbours">
                <DataTable
                  rows={entity.neighbours}
                  columns={neighbourColumns(entity)}
                  rowKey={(one) => one.node_id}
                  caption={`One hop. ${String(entity.neighbours.length)} resources, through the same traversal the map uses, so the two cannot disagree about what this is attached to.`}
                />
              </div>
            )}
            {boundary.length > 0 ? (
              // The most interesting relationship on the page, and the one a neighbour list
              // cannot show: the far end is outside what this read could see, usually an
              // account nobody granted. A line to nowhere is not how to draw that.
              <p data-testid="entity-boundary">
                {boundary.length === 1
                  ? 'One relationship leaves what could be read: '
                  : `${String(boundary.length)} relationships leave what could be read: `}
                {boundary.map((edge) => `${edge.edge_kind} via ${edge.source}`).join(', ')}. The
                far end is in an account or region this read did not cover.
              </p>
            ) : null}

            <p>
              <Link to="/inventory/topology" data-testid="entity-to-map">
                See this on the map
              </Link>
            </p>
          </article>
        ) : null}
      </StateBoundary>
    </section>
  );
}
