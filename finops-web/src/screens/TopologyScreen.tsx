import { lazy, Suspense, useState } from 'react';
import { Link } from 'react-router';

import { useGraphCoverage, useInventoryRoots, useTopologySubgraph } from '../api/queries';
import type { ApiSliceCoverage } from '../api/types';
import { StateBoundary } from '../components/StateBoundary';
import { useReportMeta } from '../shell/metaRegistry';
import { saidOf } from './sliceCoverage';
import { surfaceStateFor } from './surfaceStateFor';

/**
 * What is connected to what, and what could not be read.
 *
 * Three things are above the graph rather than under it, and that placement is the
 * feature. A region with PARTIAL coverage, a subgraph the cap truncated, and a slice
 * nobody has read yet all change what the picture means, and a reader who sees the
 * picture first has already drawn a conclusion by the time they reach a footnote.
 *
 * **The table is the accessible path, not the fallback.** A force directed layout cannot
 * be navigated by a screen reader, so the same nodes and edges are listed in a table
 * beside it, which is the arrangement the organization screen already proves works. Both
 * read from one payload, so neither can be right about the estate while the other is
 * wrong.
 *
 * **The graph library loads only when a root is chosen.** It is most of the bundle, and
 * the first thing this screen shows is a list of roots.
 */

const DEPTHS = [1, 2, 3, 4] as const;

/** The cap a reader can pick from. The route's ceiling is far higher and refuses above it. */
const CAPS = [50, 200, 2000] as const;

const TopologyCanvas = lazy(async () => {
  const canvas = await import('../components/TopologyCanvas');
  return { default: canvas.TopologyCanvas };
});

/** One incomplete slice, as a sentence a reader can act on. */
export function TopologyScreen() {
  const [rootId, setRootId] = useState<string | null>(null);
  const [depth, setDepth] = useState<number>(2);
  const [cap, setCap] = useState<number>(200);

  const roots = useInventoryRoots();
  const estate = useGraphCoverage();
  const graph = useTopologySubgraph(rootId, { depth, nodes: cap });

  // Two unwrappings, because `resolveSurface` wraps the envelope in the source it came
  // from. The same shape every screen built after the fixture seam uses.
  const rootsEnvelope = roots.data?.data;
  const estateEnvelope = estate.data?.data;
  const graphEnvelope = graph.data?.data;

  useReportMeta('inventory-roots', rootsEnvelope?.meta);
  useReportMeta('inventory-coverage', estateEnvelope?.meta);
  useReportMeta('inventory-topology', graphEnvelope?.meta);

  const available = rootsEnvelope?.data.roots ?? [];
  const subgraph = graphEnvelope?.data;
  const unreadable = estateEnvelope?.data.incomplete ?? [];
  const crossed = (subgraph?.coverage ?? []).filter(
    (slice: ApiSliceCoverage) => slice.state !== 'COMPLETE',
  );

  const state = surfaceStateFor(
    roots,
    rootsEnvelope?.meta,
    available.length,
    'none',
    'inventory',
  );

  return (
    <section aria-label="Topology">
      {/* Above the graph, never in a footnote. A reader who sees the picture first has
          already drawn a conclusion. */}
      {unreadable.length > 0 ? (
        <div role="status" data-testid="estate-coverage" className="meter-stale">
          <p>
            {unreadable.length === 1
              ? 'One slice of the estate could not be read, so anything drawn here may be ' +
                'missing edges into it.'
              : `${String(unreadable.length)} slices of the estate could not be read, so ` +
                'anything drawn here may be missing edges into them.'}
          </p>
          {/* Collapsed, like the resource list's. Nine lines of slice identifiers above a graph
              is the honesty machinery being the first thing a reader sees instead of the
              picture they came for. The count and the typed causes stay visible, nothing is
              fetched to open it, and the slices are still in the document. */}
          <details data-testid="estate-coverage-detail">
            <summary data-testid="estate-coverage-causes">
              {[...new Set(unreadable.map((slice) => slice.state))].join(', ')}
            </summary>
            <ul>
              {unreadable.map((slice) => (
                <li key={`${slice.account_id}:${slice.region_id ?? 'global'}`}>
                  {saidOf(slice)}
                </li>
              ))}
            </ul>
          </details>
        </div>
      ) : null}

      <StateBoundary state={state}>
        <div role="group" aria-label="Root resource" data-testid="roots">
          <h2>Start the map from</h2>
          <ul>
            {available.map((root) => (
              <li key={root.node_id}>
                <button
                  type="button"
                  aria-pressed={rootId === root.node_id}
                  onClick={() => {
                    setRootId(root.node_id);
                  }}
                >
                  {root.name ?? root.provider_id}
                  {/* The provider's own type, because ten of the estate's types draw as
                      OTHER and the kind alone leaves a reader guessing. */}
                  <span> ({root.resource_type})</span>
                </button>
              </li>
            ))}
          </ul>
        </div>

        <div role="group" aria-label="Bounds">
          <label htmlFor="topology-depth">Hops</label>
          <select
            id="topology-depth"
            value={depth}
            onChange={(event) => {
              setDepth(Number(event.target.value));
            }}
          >
            {DEPTHS.map((one) => (
              <option key={one} value={one}>
                {one}
              </option>
            ))}
          </select>
          <label htmlFor="topology-cap">Most nodes</label>
          <select
            id="topology-cap"
            value={cap}
            onChange={(event) => {
              setCap(Number(event.target.value));
            }}
          >
            {CAPS.map((one) => (
              <option key={one} value={one}>
                {one}
              </option>
            ))}
          </select>
        </div>

        {rootId === null ? (
          <p>Choose a resource to map what it connects to.</p>
        ) : subgraph === undefined ? (
          <p>Loading the map</p>
        ) : (
          <>
            {/* Both notices, both above the graph. */}
            {subgraph.omitted_nodes > 0 ? (
              <p role="status" data-testid="truncation" className="meter-stale">
                {subgraph.omitted_is_exact
                  ? `Showing ${String(subgraph.nodes.length)} of ` +
                    `${String(subgraph.nodes.length + subgraph.omitted_nodes)} resources within ` +
                    `${String(subgraph.max_depth)} hops. ` +
                    `${String(subgraph.omitted_nodes)} were omitted by the ` +
                    `${String(subgraph.max_nodes)} node limit.`
                  : `Showing ${String(subgraph.nodes.length)} resources. At least ` +
                    `${String(subgraph.omitted_nodes)} more are within ` +
                    `${String(subgraph.max_depth)} hops and were omitted.`}
              </p>
            ) : null}
            {crossed.length > 0 ? (
              <div role="status" data-testid="subgraph-coverage" className="meter-stale">
                <p>
                  This map crosses a slice that was not read whole, so edges into it may be
                  missing.
                </p>
                <ul>
                  {crossed.map((slice) => (
                    <li key={`${slice.account_id}:${slice.region_id ?? 'global'}`}>
                      {saidOf(slice)}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            <Suspense fallback={<p>Loading the map</p>}>
              <TopologyCanvas nodes={subgraph.nodes} edges={subgraph.edges} />
            </Suspense>

            <table>
              <caption>
                The same {String(subgraph.nodes.length)} resources and{' '}
                {String(subgraph.edges.length)} relationships, in a readable order. This is the
                accessible equivalent of the map above rather than a summary of it.
              </caption>
              <thead>
                <tr>
                  <th scope="col">Resource</th>
                  <th scope="col">Type</th>
                  <th scope="col">Account</th>
                  <th scope="col">Region</th>
                  <th scope="col">Zone</th>
                </tr>
              </thead>
              <tbody>
                {subgraph.nodes.map((node) => (
                  <tr key={node.node_id}>
                    <th scope="row">
                      {/* FEAT-053. The map answers what is connected to what and nothing
                          else, so every resource on it leads to the page that answers what
                          it costs and what is wrong with it. */}
                      <Link to={`/inventory/resources/${node.node_id}`}>
                        {node.name ?? node.provider_id}
                      </Link>
                    </th>
                    <td>{node.resource_type}</td>
                    <td>{node.account_id}</td>
                    {/* A null region is global, never a region nobody could read. */}
                    <td>{node.region_id ?? 'global'}</td>
                    {/* A null zone is regional, never an unknown zone. */}
                    <td>{node.availability_zone ?? 'regional'}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            <table>
              <caption>Relationships, with the API that supplied each one.</caption>
              <thead>
                <tr>
                  <th scope="col">From</th>
                  <th scope="col">Relationship</th>
                  <th scope="col">To</th>
                  <th scope="col">Read from</th>
                </tr>
              </thead>
              <tbody>
                {subgraph.edges.map((edge) => (
                  <tr key={`${edge.from_node_id}->${edge.to_node_id}:${edge.edge_kind}`}>
                    <th scope="row">{edge.from_node_id}</th>
                    <td>{edge.edge_kind}</td>
                    <td>
                      {edge.to_node_id}
                      {/* Said rather than drawn only, because the table is the path a
                          screen reader takes and a dashed line means nothing to it. */}
                      {edge.leaves_the_graph ? <span> (outside this view)</span> : null}
                      {edge.is_cross_account ? <span> (another account)</span> : null}
                    </td>
                    <td>{edge.source}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </StateBoundary>
    </section>
  );
}
