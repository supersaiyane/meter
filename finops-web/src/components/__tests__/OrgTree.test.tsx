import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { OrgTree } from '../OrgTree';
import type { FlatNode } from '../orgNodes';
import { violationsIn } from './axe';

const NODES: FlatNode[] = [
  {
    node_id: 'r-root',
    node_type: 'ROOT',
    parent_node_id: null,
    name: 'root',
    path: '/r-root',
    depth: 0,
    reachable: true,
  },
  {
    node_id: '111122223333',
    node_type: 'ACCOUNT',
    parent_node_id: 'r-root',
    name: 'production',
    path: '/r-root/111122223333',
    depth: 1,
    reachable: true,
  },
  {
    node_id: '444455556666',
    node_type: 'ACCOUNT',
    parent_node_id: 'r-root',
    name: 'finance',
    path: '/r-root/444455556666',
    depth: 1,
    reachable: false,
  },
];

describe('OrgTree', () => {
  it('draws unreachable branches rather than pruning them', () => {
    // A tree with gaps a user cannot explain reads as broken data, and destroys
    // trust in the parts that are correct.
    render(<OrgTree nodes={NODES} />);
    expect(screen.getByText('finance')).toBeInTheDocument();
    expect(screen.getByText('production')).toBeInTheDocument();
  });

  it('marks an unreachable branch in words, not only by styling', () => {
    render(<OrgTree nodes={NODES} />);
    expect(screen.getByText(/unreachable, outside your scope/)).toBeInTheDocument();
  });

  it('makes an unreachable branch not actionable', async () => {
    // Asserted as behaviour rather than as an attribute. Not clickable is a
    // statement about what happens when somebody clicks it.
    const chosen: string[] = [];
    const user = userEvent.setup();
    const { container } = render(
      <OrgTree
        nodes={NODES}
        onSelect={(id) => {
          chosen.push(id);
        }}
      />,
    );

    const unreachable = container.querySelector('[data-reachable="false"]');
    expect(unreachable).not.toBeNull();
    await user.click(unreachable as HTMLElement);
    expect(chosen).toEqual([]);

    const reachable = container.querySelector('[data-key="111122223333"]');
    await user.click(reachable as HTMLElement);
    expect(chosen).toEqual(['111122223333']);
  });

  it('keeps an unreachable branch reachable by keyboard', () => {
    // A branch a keyboard user cannot get to is a branch they cannot discover,
    // and discovering it is the whole point of drawing it.
    const { container } = render(<OrgTree nodes={NODES} />);
    const unreachable = container.querySelector('[data-reachable="false"]');
    expect(unreachable?.getAttribute('tabindex')).not.toBeNull();
  });

  it('gives every branch with children an expand control', async () => {
    // Without one a screen reader user cannot expand or collapse a branch at
    // all. React Aria says so out loud, and it is right. The name comes from
    // the library, which localises it, so this asserts the control exists and
    // lets axe assert that it has a name.
    const { container } = render(<OrgTree nodes={NODES} />);
    const branches = NODES.filter((node) =>
      NODES.some((child) => child.parent_node_id === node.node_id),
    );
    expect(container.querySelectorAll('button')).toHaveLength(branches.length);
    expect(await violationsIn(container)).toEqual([]);
  });

  it('exposes the tree roles assistive technology expects', () => {
    render(<OrgTree nodes={NODES} />);
    expect(screen.getByRole('treegrid', { name: 'Organization' })).toBeInTheDocument();
    expect(screen.getAllByRole('row').length).toBeGreaterThan(0);
  });

  it('reports no accessibility violations', async () => {
    const { container } = render(<OrgTree nodes={NODES} />);
    expect(await violationsIn(container)).toEqual([]);
  });
});
