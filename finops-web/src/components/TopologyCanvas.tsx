import cytoscape from 'cytoscape';
import { useEffect, useRef } from 'react';

import type { ApiTopologyEdge, ApiTopologyNode } from '../api/types';

/**
 * The topology map. Never the only way to read the graph, and never unbounded.
 *
 * A force directed layout cannot be navigated by a screen reader, which is why the
 * table beside it is the accessible path rather than the consolation, exactly as the
 * organization tree is for the organization graph. Both views draw from one payload, so
 * neither can be right about the estate while the other is wrong.
 *
 * The cap is the server's and is not re enforced here. The route refuses a request above
 * the ceiling and reports what it omitted, so a second cap in this file would be a
 * second number that could disagree with the one the screen is showing.
 *
 * **An edge that leaves the graph is drawn, dashed, and pointed at a marker rather than
 * at a node.** Dropping it would be the failure the whole sub project is about: the far
 * end of a cross account edge is the most interesting thing on the map, and a graph that
 * silently omits it shows an estate less connected than it is.
 */
export interface TopologyCanvasProps {
  readonly nodes: readonly ApiTopologyNode[];
  readonly edges: readonly ApiTopologyEdge[];
  readonly onSelect?: (nodeId: string) => void;
}

/** What a node is called on the map. The name if it has one, the kind if not. */
function labelFor(node: ApiTopologyNode): string {
  if (node.name !== null && node.name !== '') return node.name;
  // An OTHER node with no name would otherwise draw as an unlabelled box, and ten of
  // the estate's twenty four resource types are OTHER.
  return node.resource_type;
}

export function TopologyCanvas({ nodes, edges, onSelect }: TopologyCanvasProps) {
  const container = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (container.current === null) return undefined;
    const drawn = new Set(nodes.map((node) => node.node_id));
    const boundaries = edges.filter((edge) => edge.leaves_the_graph);
    const instance = cytoscape({
      container: container.current,
      elements: [
        ...nodes.map((node) => ({
          data: {
            id: node.node_id,
            label: labelFor(node),
            kind: node.node_kind,
            boundary: false,
          },
        })),
        // One marker per far end, so an edge leaving the graph has something to point
        // at. Drawn as a boundary rather than as a resource, because Meter holds no row
        // for it and drawing it as a node would claim it had read one.
        ...[...new Set(boundaries.map((edge) => edge.to_node_id))].map((id) => ({
          data: { id, label: 'outside this view', kind: 'BOUNDARY', boundary: true },
        })),
        ...edges
          .filter((edge) => drawn.has(edge.from_node_id))
          .map((edge) => ({
            data: {
              id: `${edge.from_node_id}->${edge.to_node_id}:${edge.edge_kind}`,
              source: edge.from_node_id,
              target: edge.to_node_id,
              label: edge.edge_kind,
              crosses: edge.is_cross_account,
              leaves: edge.leaves_the_graph,
            },
          })),
      ],
      style: [
        { selector: 'node', style: { label: 'data(label)' } },
        {
          selector: 'node[?boundary]',
          style: { 'background-opacity': 0.2, 'border-style': 'dashed', 'border-width': 1 },
        },
        { selector: 'edge', style: { label: 'data(label)', 'font-size': 8 } },
        // Cross account edges are the ones anybody asks for by name, so they are the one
        // thing on this map drawn differently from everything else.
        { selector: 'edge[?crosses]', style: { width: 3 } },
        { selector: 'edge[?leaves]', style: { 'line-style': 'dashed' } },
      ],
      layout: { name: 'breadthfirst' },
    });

    instance.on('tap', 'node', (event) => {
      const node = event.target as cytoscape.NodeSingular;
      // A boundary is not a resource Meter holds, so it cannot be opened. The map and
      // the table must not disagree about that.
      if (node.data('boundary') === true || onSelect === undefined) return;
      onSelect(node.id());
    });

    return () => {
      instance.destroy();
    };
  }, [nodes, edges, onSelect]);

  return (
    <div
      ref={container}
      data-testid="topology-canvas"
      // Focusable and named, so a keyboard reaches it and a screen reader announces what
      // it is before announcing that it cannot be navigated. The table beside it is what
      // a screen reader user reads instead, and the label says so.
      tabIndex={0}
      role="img"
      aria-label={
        `Topology map of ${String(nodes.length)} resources. ` +
        'The table below carries the same nodes and edges in a readable order.'
      }
      style={{ height: '28rem', width: '100%' }}
    />
  );
}
