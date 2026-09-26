import { Link, useParams } from 'react-router';

import { useEntity } from '../api/queries';
import { Figure } from '../components/Figure';
import { FixtureBand } from '../components/FixtureBand';
import { SeverityBadge } from '../components/SeverityBadge';
import { StateBoundary } from '../components/StateBoundary';
import { riskLabel } from '../components/actionRisk';
import type { Freshness } from '../components/provenance';
import type { ApiEntity, ApiTopologyEdge, ApiTopologyNode } from '../api/types';
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

export function EntityScreen() {
  const { nodeId = '' } = useParams();
  const query = useEntity(nodeId === '' ? null : nodeId);
  const envelope = query.data?.data;
  const entity: ApiEntity | null = envelope?.data ?? null;
  useReportMeta('inventory-entity', envelope?.meta);

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
              <table data-testid="entity-findings">
                <caption>
                  {entity.findings.length === 1
                    ? 'One finding names this resource, open or already decided.'
                    : `${String(entity.findings.length)} findings name this resource, open ` +
                      'or already decided.'}
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Finding</th>
                    <th scope="col">Saving a month</th>
                    <th scope="col">Severity</th>
                    <th scope="col">State</th>
                    <th scope="col">If it is wrong</th>
                  </tr>
                </thead>
                <tbody>
                  {entity.findings.map((row) => (
                    <tr key={row.recommendation_id}>
                      <th scope="row">
                        <Link to="/waste">{row.waste_class}</Link>
                      </th>
                      <td>
                        {/* Modelled, never measured, unlike the cost above. Figure carries
                            the label so the two cannot be confused on one page. */}
                        <Figure
                          value={{
                            kind: 'modelled',
                            amount: Number(row.estimated_monthly_saving),
                          }}
                          freshness={freshness}
                          unit="usd"
                        />
                      </td>
                      <td>
                        <SeverityBadge level={severityLevel(row.severity)} />
                      </td>
                      <td>{row.lifecycle}</td>
                      <td>
                        {/* The same two words and the same sentence the home panel shows,
                            from the same module, so a reader cannot be told a change is
                            reversible on one screen and permanent on another. */}
                        <strong>{riskLabel(row)}</strong>
                        <span> {row.risk_why}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
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

            <h3>What it is attached to</h3>
            {entity.neighbours.length === 0 ? (
              <p data-testid="entity-neighbours-empty">
                Nothing is recorded as attached to this resource.
              </p>
            ) : (
              <table data-testid="entity-neighbours">
                <caption>
                  One hop. {String(entity.neighbours.length)} resources, through the same
                  traversal the map uses, so the two cannot disagree about what this is attached
                  to.
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Resource</th>
                    <th scope="col">Kind</th>
                    <th scope="col">Relationship</th>
                    <th scope="col">Account</th>
                  </tr>
                </thead>
                <tbody>
                  {entity.neighbours.map((one) => (
                    <tr key={one.node_id}>
                      <th scope="row">
                        <Link to={`/inventory/resources/${one.node_id}`}>
                          {one.name ?? one.provider_id}
                        </Link>
                      </th>
                      <td>{one.node_kind}</td>
                      <td>{relationOf(entity.edges, entity.node.node_id, one.node_id)}</td>
                      <td>{one.account_id}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
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
