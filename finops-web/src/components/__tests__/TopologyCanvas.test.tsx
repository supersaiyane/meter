import { render } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { ApiTopologyEdge, ApiTopologyNode } from '../../api/types';

/**
 * Cytoscape draws to a canvas, and jsdom has none. As with the organization graph, what is
 * asserted here is the part this project owns: what each node is called, what is drawn as a
 * boundary, and which nodes a tap may open.
 */
const created = vi.hoisted(() => ({
  elements: [] as { data: Record<string, unknown> }[],
  taps: [] as ((event: unknown) => void)[],
}));

vi.mock('cytoscape', () => ({
  default: (options: { elements: { data: Record<string, unknown> }[] }) => {
    created.elements = options.elements;
    return {
      on: (_event: string, _selector: string, handler: (event: unknown) => void) => {
        created.taps.push(handler);
      },
      destroy: () => undefined,
    };
  },
}));

const { TopologyCanvas } = await import('../TopologyCanvas');

function node(id: string, name: string | null): ApiTopologyNode {
  return {
    node_id: id,
    provider_id: `provider-${id}`,
    account_id: 'account-a',
    node_kind: 'OTHER',
    resource_type: 'AWS::Example::Thing',
    region_id: null,
    availability_zone: null,
    name,
    as_of: '2026-10-05T06:00:00Z',
    collected_at: '2026-10-05T06:05:00Z',
  };
}

const LEAVING: ApiTopologyEdge = {
  from_node_id: 'a',
  to_node_id: 'far',
  edge_kind: 'ROUTES_TO',
  is_cross_account: true,
  source: 'config',
  leaves_the_graph: true,
};

/** A tap on one node, as cytoscape hands it to the handler. */
function tapOn(id: string, data: Record<string, unknown>): unknown {
  return { target: { id: () => id, data: (key: string) => data[key] } };
}

describe('TopologyCanvas', () => {
  beforeEach(() => {
    created.elements = [];
    created.taps = [];
  });

  it('names a node by its name, and by its resource type when it has none', () => {
    render(
      <TopologyCanvas nodes={[node('a', 'web'), node('b', null), node('c', '')]} edges={[]} />,
    );
    expect(created.elements.map((element) => element.data['label'])).toEqual([
      'web',
      'AWS::Example::Thing',
      'AWS::Example::Thing',
    ]);
  });

  it('draws the far end of an edge that leaves the view as a boundary, not a resource', () => {
    render(<TopologyCanvas nodes={[node('a', 'web')]} edges={[LEAVING]} />);
    const far = created.elements.find((element) => element.data['id'] === 'far');
    expect(far?.data).toMatchObject({ boundary: true, kind: 'BOUNDARY' });
  });

  it('opens a resource it is tapped on, and never a boundary', () => {
    const opened: string[] = [];
    render(
      <TopologyCanvas
        nodes={[node('a', 'web')]}
        edges={[LEAVING]}
        onSelect={(id) => {
          opened.push(id);
        }}
      />,
    );
    const tap = created.taps[0];
    tap?.(tapOn('far', { boundary: true }));
    tap?.(tapOn('a', { boundary: false }));
    expect(opened).toEqual(['a']);
  });

  it('does nothing on a tap when nothing listens for one', () => {
    render(<TopologyCanvas nodes={[node('a', 'web')]} edges={[]} />);
    expect(() => created.taps[0]?.(tapOn('a', { boundary: false }))).not.toThrow();
  });
});
