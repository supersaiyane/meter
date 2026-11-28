import { lazy, Suspense, useState } from 'react';

import { useOrgTree } from '../api/queries';
import { OrgTree } from '../components/OrgTree';
import { StateBoundary } from '../components/StateBoundary';
import { useReportMeta } from '../shell/metaRegistry';
import { surfaceStateFor } from './surfaceStateFor';

/**
 * The organization, as a tree by default and a graph on request.
 *
 * The tree opens first for two reasons that point the same way. At three
 * hundred accounts a force directed graph is slower to read than a tree, and it
 * is the first thing a user opens. And a graph cannot be navigated by a screen
 * reader, so the tree is the accessible path and must not be the secondary one.
 */

const VIEWS = ['Tree', 'Graph'] as const;
type View = (typeof VIEWS)[number];

/**
 * The graph library is loaded only when somebody asks for the graph.
 *
 * It is most of the bundle and the tree is the default, so paying for it on
 * first load would slow the view everybody opens in order to speed up the one
 * they mostly do not.
 */
const GraphCanvas = lazy(async () => {
  const graph = await import('../components/GraphCanvas');
  return { default: graph.GraphCanvas };
});

export function OrganizationScreen() {
  const query = useOrgTree();
  // Tree, always, on first render.
  const [view, setView] = useState<View>('Tree');
  useReportMeta('org-tree', query.data?.meta);

  const nodes = query.data?.data ?? [];
  const state = surfaceStateFor(query, query.data?.meta, nodes.length, 'none', 'org_tree');

  return (
    <section aria-label="Organization">
      <div role="group" aria-label="View">
        {VIEWS.map((name) => (
          <button
            key={name}
            type="button"
            aria-pressed={view === name}
            onClick={() => {
              setView(name);
            }}
          >
            {name}
          </button>
        ))}
      </div>
      <StateBoundary state={state}>
        {view === 'Tree' ? (
          <OrgTree nodes={nodes} />
        ) : (
          <Suspense fallback={<p>Loading the graph view</p>}>
            <GraphCanvas nodes={nodes} />
          </Suspense>
        )}
      </StateBoundary>
    </section>
  );
}
