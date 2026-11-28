import cytoscape from 'cytoscape';
import { useEffect, useRef } from 'react';

import { MAX_GRAPH_NODES, withinGraphCap, type FlatNode } from './orgNodes';

/**
 * The graph view. Never the default, and never unbounded.
 *
 * At three hundred accounts a force directed graph is slower to read than a
 * tree, so the tree opens first. This exists for the question a tree answers
 * badly, which is what connects to what.
 *
 * Above the node cap it refuses to draw and says why. Rendering twenty thousand
 * nodes produces a picture nobody can read while making the tab unresponsive,
 * and the honest answer is to filter on the server rather than to try.
 *
 * The tree is the accessible equivalent, not the fallback. A force directed
 * layout cannot be navigated by a screen reader, which is one reason the tree
 * is the default rather than the consolation.
 */
export interface GraphCanvasProps {
  readonly nodes: readonly FlatNode[];
  readonly onSelect?: (nodeId: string) => void;
}

export function GraphCanvas({ nodes, onSelect }: GraphCanvasProps) {
  const container = useRef<HTMLDivElement>(null);
  const withinCap = withinGraphCap(nodes.length);

  useEffect(() => {
    if (!withinCap || container.current === null) {
      return undefined;
    }
    const instance = cytoscape({
      container: container.current,
      elements: [
        ...nodes.map((node) => ({
          data: { id: node.node_id, label: node.name, reachable: node.reachable },
        })),
        ...nodes
          .filter((node) => node.parent_node_id !== null)
          .map((node) => ({
            data: {
              id: `${String(node.parent_node_id)}->${node.node_id}`,
              source: String(node.parent_node_id),
              target: node.node_id,
            },
          })),
      ],
      style: [
        { selector: 'node', style: { label: 'data(label)' } },
        // Drawn, and visibly not the same as the rest. Removing it would leave a
        // hole a reader cannot account for.
        {
          selector: 'node[!reachable]',
          style: { 'background-opacity': 0.25, 'border-style': 'dashed', 'border-width': 1 },
        },
      ],
      layout: { name: 'breadthfirst' },
    });

    instance.on('tap', 'node', (event) => {
      const node = event.target as cytoscape.NodeSingular;
      // An unreachable node is not actionable, in the graph exactly as in the
      // tree. Two views of one organization must not disagree about that.
      if (node.data('reachable') !== true || onSelect === undefined) return;
      onSelect(node.id());
    });

    return () => {
      instance.destroy();
    };
  }, [nodes, onSelect, withinCap]);

  if (!withinCap) {
    return (
      <p data-testid="graph" data-state="too-large">
        This organization has {nodes.length} nodes, above the {MAX_GRAPH_NODES} the graph draws.
        Narrow the scope and try again. The tree view shows all of them.
      </p>
    );
  }
  return <div ref={container} data-testid="graph" data-state="drawn" style={{ height: 480 }} />;
}
