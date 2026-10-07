import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { MAX_GRAPH_NODES, type FlatNode } from '../orgNodes';

/**
 * Cytoscape draws to a canvas, and jsdom has none.
 *
 * What is asserted here is the part this project owns: the cap, and the graph
 * handed to the library. Whether the library then draws three hundred nodes
 * legibly is a question about a browser, and it belongs to the Playwright
 * journey in TASK-P0-028 rather than to a test that cannot see pixels.
 */
const created = vi.hoisted(() => ({
  calls: [] as { elements: unknown[] }[],
  taps: [] as ((event: unknown) => void)[],
}));

vi.mock('cytoscape', () => ({
  default: (options: { elements: unknown[] }) => {
    created.calls.push({ elements: options.elements });
    return {
      on: (_event: string, _selector: string, handler: (event: unknown) => void) => {
        created.taps.push(handler);
      },
      destroy: () => undefined,
    };
  },
}));

const { GraphCanvas } = await import('../GraphCanvas');

/** A tap on one node, as cytoscape hands it to the handler. */
function tapOn(id: string, data: Record<string, unknown>): unknown {
  return { target: { id: () => id, data: (key: string) => data[key] } };
}

function nodes(count: number): FlatNode[] {
  return Array.from({ length: count }, (_, index) => ({
    node_id: String(index),
    node_type: index === 0 ? 'ROOT' : 'ACCOUNT',
    parent_node_id: index === 0 ? null : '0',
    name: `node-${String(index)}`,
    path: `/${String(index)}`,
    depth: index === 0 ? 0 : 1,
    reachable: index !== 1,
  }));
}

describe('GraphCanvas', () => {
  beforeEach(() => {
    created.calls = [];
    created.taps = [];
  });

  it('draws an organization within the cap', () => {
    render(<GraphCanvas nodes={nodes(50)} />);
    expect(screen.getByTestId('graph').dataset['state']).toBe('drawn');
    expect(created.calls).toHaveLength(1);
  });

  it('hands every node and every edge to the graph at three hundred accounts', () => {
    render(<GraphCanvas nodes={nodes(300)} />);
    // 300 nodes, and 299 edges because the root has no parent.
    expect(created.calls[0]?.elements).toHaveLength(599);
  });

  it('carries reachability through, so the graph and the tree agree', () => {
    render(<GraphCanvas nodes={nodes(3)} />);
    const elements = created.calls[0]?.elements as { data: Record<string, unknown> }[];
    const unreachable = elements.filter((element) => element.data['reachable'] === false);
    expect(unreachable).toHaveLength(1);
  });

  it('refuses above the cap and says what to do instead', () => {
    // Rendering twenty thousand nodes gives a picture nobody can read while
    // making the tab unresponsive. The honest answer is to filter server side.
    render(<GraphCanvas nodes={nodes(MAX_GRAPH_NODES + 1)} />);
    const graph = screen.getByTestId('graph');
    expect(graph.dataset['state']).toBe('too-large');
    expect(graph.textContent).toContain('tree view shows all of them');
    expect(created.calls).toHaveLength(0);
  });

  it('opens a reachable node it is tapped on, and never an unreachable one', () => {
    const opened: string[] = [];
    render(
      <GraphCanvas
        nodes={nodes(3)}
        onSelect={(id) => {
          opened.push(id);
        }}
      />,
    );
    const tap = created.taps[0];
    tap?.(tapOn('1', { reachable: false }));
    tap?.(tapOn('2', { reachable: true }));
    expect(opened).toEqual(['2']);
  });

  it('does nothing on a tap when nothing listens for one', () => {
    render(<GraphCanvas nodes={nodes(3)} />);
    expect(() => created.taps[0]?.(tapOn('2', { reachable: true }))).not.toThrow();
  });
});
