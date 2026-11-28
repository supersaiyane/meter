/**
 * Turning the flat node list the API returns into the tree the screen draws.
 *
 * The API sends every node the tenant has, with out of scope accounts marked
 * unreachable rather than removed. That is deliberate on both sides: a tree
 * with gaps a user cannot explain reads as broken data and destroys trust in
 * the parts that are correct.
 */

export interface FlatNode {
  readonly node_id: string;
  readonly node_type: string;
  readonly parent_node_id: string | null;
  readonly name: string;
  readonly path: string;
  readonly depth: number;
  readonly reachable: boolean;
}

export interface TreeNode extends FlatNode {
  readonly children: readonly TreeNode[];
}

export const MAX_GRAPH_NODES = 2000;

/**
 * Build the tree. A node whose parent is missing becomes a root rather than
 * disappearing, because a subtree silently dropped is exactly the gap this
 * screen exists to avoid.
 */
export function buildTree(nodes: readonly FlatNode[]): TreeNode[] {
  const children = new Map<string, TreeNode[]>();
  const built = new Map<string, TreeNode>();

  for (const node of nodes) {
    const entry: TreeNode = { ...node, children: [] };
    built.set(node.node_id, entry);
    children.set(node.node_id, entry.children as TreeNode[]);
  }

  const roots: TreeNode[] = [];
  for (const node of nodes) {
    const entry = built.get(node.node_id);
    if (entry === undefined) continue;
    const parentBucket =
      node.parent_node_id === null ? undefined : children.get(node.parent_node_id);
    if (parentBucket === undefined) {
      roots.push(entry);
    } else {
      parentBucket.push(entry);
    }
  }
  return roots;
}

/** The identifiers a keyboard user may reach but must not act on. */
export function unreachableKeys(nodes: readonly FlatNode[]): string[] {
  return nodes.filter((node) => !node.reachable).map((node) => node.node_id);
}

export function withinGraphCap(count: number): boolean {
  return count <= MAX_GRAPH_NODES;
}
