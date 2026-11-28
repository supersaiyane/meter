import { describe, expect, it } from 'vitest';

import { buildTree, MAX_GRAPH_NODES, unreachableKeys, withinGraphCap } from '../orgNodes';
import type { FlatNode } from '../orgNodes';

function node(id: string, parent: string | null, reachable = true): FlatNode {
  return {
    node_id: id,
    node_type: parent === null ? 'ROOT' : 'ACCOUNT',
    parent_node_id: parent,
    name: id,
    path: `/${id}`,
    depth: parent === null ? 0 : 1,
    reachable,
  };
}

describe('buildTree', () => {
  it('nests children under their parent', () => {
    const roots = buildTree([node('r', null), node('a', 'r'), node('b', 'r')]);
    expect(roots).toHaveLength(1);
    expect(roots[0]?.children.map((child) => child.node_id)).toEqual(['a', 'b']);
  });

  it('promotes an orphan rather than dropping it', () => {
    // A subtree silently dropped is exactly the gap this screen exists to avoid.
    const roots = buildTree([node('a', 'missing-parent')]);
    expect(roots.map((entry) => entry.node_id)).toEqual(['a']);
  });

  it('keeps unreachable nodes in the tree', () => {
    const roots = buildTree([node('r', null), node('a', 'r', false)]);
    expect(roots[0]?.children).toHaveLength(1);
  });
});

describe('unreachableKeys', () => {
  it('lists exactly the nodes outside the scope', () => {
    expect(unreachableKeys([node('a', null), node('b', null, false)])).toEqual(['b']);
  });
});

describe('withinGraphCap', () => {
  it('permits the cap and refuses above it', () => {
    expect(withinGraphCap(MAX_GRAPH_NODES)).toBe(true);
    expect(withinGraphCap(MAX_GRAPH_NODES + 1)).toBe(false);
  });
});
