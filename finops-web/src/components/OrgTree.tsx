import { Button, Collection, Tree, TreeItem, TreeItemContent } from 'react-aria-components';

import { buildTree, unreachableKeys, type FlatNode, type TreeNode } from './orgNodes';

/**
 * The organization tree, keyboard navigable, with unreachable branches drawn.
 *
 * Behaviour comes from React Aria rather than being hand written. ADR-0019
 * disqualifies writing it here as rung seven: accessible tree navigation,
 * expansion state and roving focus are a large amount of subtle work that is
 * not this product's problem.
 *
 * An unreachable branch stays focusable and stops being actionable, which is
 * why `disabledBehavior` is selection rather than the default. A branch a
 * keyboard user cannot reach at all is a branch they cannot discover, and the
 * point of drawing it is that they discover it.
 */
export interface OrgTreeProps {
  readonly nodes: readonly FlatNode[];
  readonly onSelect?: (nodeId: string) => void;
}

function renderNode(node: TreeNode) {
  return (
    <TreeItem
      key={node.node_id}
      id={node.node_id}
      textValue={node.name}
      data-reachable={node.reachable ? 'true' : 'false'}
    >
      <TreeItemContent>
        {({ hasChildItems }) => (
          <>
            {hasChildItems ? (
              // Without this a screen reader user cannot expand or collapse a
              // branch at all. React Aria says so out loud, and it is right.
              // React Aria supplies the accessible name for this slot and
              // localises it, which is better than a hand written one. The
              // glyph is hidden so it does not read out as punctuation.
              <Button slot="chevron">
                <span aria-hidden="true">+</span>
              </Button>
            ) : null}
            <span>{node.name}</span>
            {/* The kind, muted and after the name. It reads as a label rather
                than as part of the name, which `platform ou` did not. */}
            <span className="meter-kind">{node.node_type.toLowerCase()}</span>
            {node.reachable ? null : (
              // Marked in words, not only by styling. A reader who cannot see
              // the treatment still learns why the numbers stop here.
              <span className="meter-failure"> unreachable, outside your scope</span>
            )}
          </>
        )}
      </TreeItemContent>
      <Collection items={node.children}>{renderNode}</Collection>
    </TreeItem>
  );
}

export function OrgTree({ nodes, onSelect }: OrgTreeProps) {
  const roots = buildTree(nodes);
  // Expanded by default. An organization map that opens collapsed answers no
  // question, and the one thing a reader wants from it is the shape.
  const expandable = nodes
    .filter((node) => nodes.some((child) => child.parent_node_id === node.node_id))
    .map((node) => node.node_id);
  return (
    <Tree
      aria-label="Organization"
      items={roots}
      defaultExpandedKeys={expandable}
      selectionMode="single"
      disabledKeys={unreachableKeys(nodes)}
      disabledBehavior="selection"
      data-testid="org-tree"
      onSelectionChange={(keys) => {
        if (onSelect === undefined || keys === 'all') return;
        const first = [...keys][0];
        if (first !== undefined) onSelect(String(first));
      }}
    >
      {renderNode}
    </Tree>
  );
}
